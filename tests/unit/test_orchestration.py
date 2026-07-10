import pytest
from unittest.mock import MagicMock
from pathlib import Path
from app.config import settings
from app.schemas.incident import IncidentRecord
from app.schemas.evidence import Evidence
from app.schemas.model_response import (
    ValidatedModelResponse,
    RCADecisionResponse,
    CriticDecisionResponse,
    LLMExecutionMetadata
)
from app.schemas.orchestration import ToolSelectionDecision
from app.services.telemetry import (
    ScenarioRepository,
    LogRepository,
    MetricRepository,
    TraceRepository,
    DeploymentRepository,
    ServiceTopologyRepository
)
from app.services.knowledge.base_embedding import MockEmbeddingProvider
from app.services.knowledge.vector_store_base import BaseVectorStore
from app.services.knowledge.qdrant_adapter import QdrantVectorStoreAdapter
from app.services.knowledge.reranker import FlashRankReranker
from app.services.knowledge.cache import KnowledgeCache
from app.services.knowledge.retriever import HybridRetriever
from app.services.prompting.assembler import PromptAssembler
from app.services.gateway.gateway import LLMGateway
from app.tools import create_default_registry
from app.services.orchestration import (
    InvestigationState,
    WorkflowNodes,
    create_investigation_graph
)

@pytest.fixture
def repo_bundle():
    scenario_path = settings.GENERATED_DATA_DIR / "SCN-DB-POOL-001"
    scenario_repo = ScenarioRepository(scenario_path)
    return {
        "scenario_repo": scenario_repo,
        "log_repo": LogRepository(scenario_repo),
        "metric_repo": MetricRepository(scenario_repo),
        "trace_repo": TraceRepository(scenario_repo),
        "deploy_repo": DeploymentRepository(scenario_repo),
        "topo_repo": ServiceTopologyRepository(scenario_repo),
    }

@pytest.fixture
def tool_registry(repo_bundle):
    return create_default_registry(
        repo_bundle["scenario_repo"],
        repo_bundle["log_repo"],
        repo_bundle["metric_repo"],
        repo_bundle["trace_repo"],
        repo_bundle["deploy_repo"],
        repo_bundle["topo_repo"],
    )

@pytest.fixture
def topology(repo_bundle):
    return repo_bundle["topo_repo"].get_topology()

@pytest.fixture
def mock_retriever():
    retriever = MagicMock(spec=HybridRetriever)
    from app.schemas.knowledge import KnowledgeBundle, RetrievalExecutionMetadata
    meta = RetrievalExecutionMetadata(
        vector_store_mode="memory",
        embedding_mode="mock",
        reranker_mode="flashrank",
        degraded_mode=False
    )
    retriever.retrieve.return_value = KnowledgeBundle(
        chunks=tuple(),
        applied_filters={},
        evidence_references=tuple(),
        search_summary="none",
        execution_metadata=meta
    )
    return retriever

@pytest.fixture
def incident(repo_bundle):
    return repo_bundle["scenario_repo"].load_incident()

@pytest.fixture
def mock_gateway():
    gateway = MagicMock(spec=LLMGateway)
    return gateway

# Helper to build mock metadata
def make_metadata(task_type: str) -> LLMExecutionMetadata:
    return LLMExecutionMetadata(
        request_id="REQ-1",
        task_type=task_type,
        prompt_template_id="t1",
        prompt_version="v1",
        initial_provider="groq",
        final_provider="groq",
        model_id="m1",
        retry_count=0,
        fallback_attempted=False,
        latency_ms=10.0,
        input_guardrail_status="passed",
        output_guardrail_status="passed",
        schema_validation_status="passed",
        citation_validation_status="passed"
    )

# --- Orchestration Tests ---

def test_graph_compilation(mock_gateway, mock_retriever, tool_registry, topology):
    nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
    graph = create_investigation_graph(nodes).compile()
    assert graph is not None

def test_happy_path(mock_gateway, mock_retriever, tool_registry, topology, incident):
    # Set up mock gateway responses: hypothesis generated, critic accepts immediately
    rca_res = RCADecisionResponse(
        response_id="R-1",
        task_type="rca",
        summary="Database Connection Pool Exhaustion on checkout-service.",
        observations=("Obs 1",),
        hypotheses=("Hyp 1",),
        recommended_next_steps=()
    )
    critic_res = CriticDecisionResponse(
        response_id="C-1",
        task_type="critic",
        is_valid=True,
        findings=(),
        suggestions=(),
        decision="ACCEPT",
        confidence_score=0.9
    )

    def side_effect(request):
        if request.task_type == "rca":
            return ValidatedModelResponse(
                response_id="R-1",
                task_type="rca",
                raw_content="{}",
                parsed_response=rca_res,
                execution_metadata=make_metadata("rca")
            )
        elif request.task_type == "critic":
            return ValidatedModelResponse(
                response_id="C-1",
                task_type="critic",
                raw_content="{}",
                parsed_response=critic_res,
                execution_metadata=make_metadata("critic")
            )
        raise ValueError(f"Unexpected task type: {request.task_type}")

    mock_gateway.generate.side_effect = side_effect

    nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
    graph = create_investigation_graph(nodes).compile()

    state = {"incident": incident, "investigation_id": "INV-001"}
    result = graph.invoke(state)

    assert result["termination_reason"] == "RCA accepted by critic"
    assert result["iteration_count"] == 1
    assert result["tool_call_count"] == 0
    assert result["current_rca"].summary == rca_res.summary
    assert result["critic_decision"].decision == "ACCEPT"

def test_multi_iteration_path(mock_gateway, mock_retriever, tool_registry, topology, incident):
    # Iteration 1: Critic CONTINUE_INVESTIGATION -> selects log tool -> Execute tool
    # Iteration 2: Critic ACCEPT -> finalize
    rca_res = RCADecisionResponse(
        response_id="R-1",
        task_type="rca",
        summary="Initial draft",
        observations=(),
        hypotheses=(),
        recommended_next_steps=()
    )
    
    critic_res_continue = CriticDecisionResponse(
        response_id="C-1",
        task_type="critic",
        is_valid=False,
        findings=("Missing log details",),
        suggestions=("Run log search",),
        decision="CONTINUE_INVESTIGATION",
        confidence_score=0.4,
        evidence_gaps=("log",)
    )

    tool_selection_res = ToolSelectionDecision(
        response_id="S-1",
        task_type="tool_selection",
        tool_name="log_pattern_search",
        reason="Query logs for checkout-service pool capacity.",
        parameters={},
        expected_evidence_type="log"
    )

    critic_res_accept = CriticDecisionResponse(
        response_id="C-2",
        task_type="critic",
        is_valid=True,
        findings=(),
        suggestions=(),
        decision="ACCEPT",
        confidence_score=0.9
    )

    critic_call_count = 0

    def side_effect(request):
        nonlocal critic_call_count
        if request.task_type == "rca":
            return ValidatedModelResponse(
                response_id="R-1",
                task_type="rca",
                raw_content="{}",
                parsed_response=rca_res,
                execution_metadata=make_metadata("rca")
            )
        elif request.task_type == "critic":
            critic_call_count += 1
            res = critic_res_continue if critic_call_count == 1 else critic_res_accept
            return ValidatedModelResponse(
                response_id=res.response_id,
                task_type="critic",
                raw_content="{}",
                parsed_response=res,
                execution_metadata=make_metadata("critic")
            )
        elif request.task_type == "tool_selection":
            return ValidatedModelResponse(
                response_id="S-1",
                task_type="tool_selection",
                raw_content="{}",
                parsed_response=tool_selection_res,
                execution_metadata=make_metadata("tool_selection")
            )
        raise ValueError(f"Unexpected task type: {request.task_type}")

    mock_gateway.generate.side_effect = side_effect

    nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
    graph = create_investigation_graph(nodes).compile()

    state = {"incident": incident, "investigation_id": "INV-002"}
    result = graph.invoke(state)

    assert result["termination_reason"] == "RCA accepted by critic"
    assert result["iteration_count"] == 2
    assert result["tool_call_count"] == 1
    assert len(result["evidence_list"]) > 1

def test_max_iterations_exceeded(mock_gateway, mock_retriever, tool_registry, topology, incident):
    # Always request to continue investigation, until max iterations budget is reached
    rca_res = RCADecisionResponse(
        response_id="R-1",
        task_type="rca",
        summary="Draft summary",
        observations=(),
        hypotheses=(),
        recommended_next_steps=()
    )
    
    critic_res = CriticDecisionResponse(
        response_id="C-1",
        task_type="critic",
        is_valid=False,
        findings=("Gaps",),
        suggestions=("Run log search",),
        decision="CONTINUE_INVESTIGATION",
        confidence_score=0.4,
        evidence_gaps=("log",)
    )

    tool_selection_res = ToolSelectionDecision(
        response_id="S-1",
        task_type="tool_selection",
        tool_name="log_pattern_search",
        reason="Query logs",
        parameters={"service": "checkout-service", "pattern": "pool"},
        expected_evidence_type="log"
    )

    mock_gateway.generate.side_effect = lambda request: ValidatedModelResponse(
        response_id="1",
        task_type=request.task_type,
        raw_content="{}",
        parsed_response=(rca_res if request.task_type == "rca" else (critic_res if request.task_type == "critic" else tool_selection_res)),
        execution_metadata=make_metadata(request.task_type)
    )

    # Force max iterations limit to 2
    original_max_iters = settings.INVESTIGATION_MAX_ITERATIONS
    settings.INVESTIGATION_MAX_ITERATIONS = 2

    try:
        nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
        graph = create_investigation_graph(nodes).compile()

        state = {"incident": incident, "investigation_id": "INV-003"}
        result = graph.invoke(state)

        assert result["termination_reason"] == "Escalated to human review"
        assert result["iteration_count"] == 2
        assert result["human_review"] is not None
        assert "Max investigation iteration limit reached." in result["human_review"].reason
    finally:
        settings.INVESTIGATION_MAX_ITERATIONS = original_max_iters

def test_max_tool_calls_exceeded(mock_gateway, mock_retriever, tool_registry, topology, incident):
    rca_res = RCADecisionResponse(
        response_id="R-1",
        task_type="rca",
        summary="Draft",
        observations=(),
        hypotheses=(),
        recommended_next_steps=()
    )
    
    critic_res = CriticDecisionResponse(
        response_id="C-1",
        task_type="critic",
        is_valid=False,
        decision="CONTINUE_INVESTIGATION",
        confidence_score=0.4,
        evidence_gaps=("log",)
    )

    tool_selection_res = ToolSelectionDecision(
        response_id="S-1",
        task_type="tool_selection",
        tool_name="log_pattern_search",
        reason="Query logs",
        parameters={"service": "checkout-service", "pattern": "pool"},
        expected_evidence_type="log"
    )

    mock_gateway.generate.side_effect = lambda request: ValidatedModelResponse(
        response_id="1",
        task_type=request.task_type,
        raw_content="{}",
        parsed_response=(rca_res if request.task_type == "rca" else (critic_res if request.task_type == "critic" else tool_selection_res)),
        execution_metadata=make_metadata(request.task_type)
    )

    original_max_tools = settings.INVESTIGATION_MAX_TOOL_CALLS
    settings.INVESTIGATION_MAX_TOOL_CALLS = 1

    try:
        nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
        graph = create_investigation_graph(nodes).compile()

        state = {"incident": incident, "investigation_id": "INV-004"}
        result = graph.invoke(state)

        assert result["termination_reason"] == "Escalated to human review"
        assert result["tool_call_count"] == 1
        assert "Max tool call budget exhausted." in result["human_review"].reason
    finally:
        settings.INVESTIGATION_MAX_TOOL_CALLS = original_max_tools

def test_max_context_rebuilds_exceeded(mock_gateway, mock_retriever, tool_registry, topology, incident):
    rca_res = RCADecisionResponse(
        response_id="R-1",
        task_type="rca",
        summary="Draft",
        observations=(),
        hypotheses=(),
        recommended_next_steps=()
    )
    
    critic_res = CriticDecisionResponse(
        response_id="C-1",
        task_type="critic",
        is_valid=False,
        decision="CONTINUE_INVESTIGATION",
        confidence_score=0.4,
        evidence_gaps=("log",)
    )

    tool_selection_res = ToolSelectionDecision(
        response_id="S-1",
        task_type="tool_selection",
        tool_name="log_pattern_search",
        reason="Query logs",
        parameters={"service": "checkout-service", "pattern": "pool"},
        expected_evidence_type="log"
    )

    mock_gateway.generate.side_effect = lambda request: ValidatedModelResponse(
        response_id="1",
        task_type=request.task_type,
        raw_content="{}",
        parsed_response=(rca_res if request.task_type == "rca" else (critic_res if request.task_type == "critic" else tool_selection_res)),
        execution_metadata=make_metadata(request.task_type)
    )

    original_max_rebuilds = settings.INVESTIGATION_MAX_CONTEXT_REBUILDS
    settings.INVESTIGATION_MAX_CONTEXT_REBUILDS = 1

    try:
        nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
        graph = create_investigation_graph(nodes).compile()

        state = {"incident": incident, "investigation_id": "INV-005"}
        result = graph.invoke(state)

        assert result["termination_reason"] == "Escalated to human review"
        assert result["context_rebuild_count"] == 1
        assert "Max context rebuild budget reached." in result["human_review"].reason
    finally:
        settings.INVESTIGATION_MAX_CONTEXT_REBUILDS = original_max_rebuilds

def test_unknown_tool_rejection(mock_gateway, mock_retriever, tool_registry, topology, incident):
    rca_res = RCADecisionResponse(
        response_id="R-1",
        task_type="rca",
        summary="Draft",
        observations=(),
        hypotheses=(),
        recommended_next_steps=()
    )
    
    critic_res = CriticDecisionResponse(
        response_id="C-1",
        task_type="critic",
        is_valid=False,
        decision="CONTINUE_INVESTIGATION",
        confidence_score=0.4,
        evidence_gaps=("log",)
    )

    tool_selection_res = ToolSelectionDecision(
        response_id="S-1",
        task_type="tool_selection",
        tool_name="unknown_tool_name",
        reason="Malicious or incorrect tool selection",
        parameters={},
        expected_evidence_type="log"
    )

    mock_gateway.generate.side_effect = lambda request: ValidatedModelResponse(
        response_id="1",
        task_type=request.task_type,
        raw_content="{}",
        parsed_response=(rca_res if request.task_type == "rca" else (critic_res if request.task_type == "critic" else tool_selection_res)),
        execution_metadata=make_metadata(request.task_type)
    )

    nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
    graph = create_investigation_graph(nodes).compile()

    state = {"incident": incident, "investigation_id": "INV-006"}
    result = graph.invoke(state)

    assert result["termination_reason"] == "Investigation failure"
    assert result["failure"].failure_type == "TOOL_NOT_FOUND"

def test_invalid_parameters_rejection(mock_gateway, mock_retriever, tool_registry, topology, incident):
    rca_res = RCADecisionResponse(
        response_id="R-1",
        task_type="rca",
        summary="Draft",
        observations=(),
        hypotheses=(),
        recommended_next_steps=()
    )
    
    critic_res = CriticDecisionResponse(
        response_id="C-1",
        task_type="critic",
        is_valid=False,
        decision="CONTINUE_INVESTIGATION",
        confidence_score=0.4,
        evidence_gaps=("log",)
    )

    tool_selection_res = ToolSelectionDecision(
        response_id="S-1",
        task_type="tool_selection",
        tool_name="log_pattern_search",
        reason="Query logs with invalid parameters",
        parameters={"service": {"invalid_nested_type": "dict"}},
        expected_evidence_type="log"
    )

    mock_gateway.generate.side_effect = lambda request: ValidatedModelResponse(
        response_id="1",
        task_type=request.task_type,
        raw_content="{}",
        parsed_response=(rca_res if request.task_type == "rca" else (critic_res if request.task_type == "critic" else tool_selection_res)),
        execution_metadata=make_metadata(request.task_type)
    )

    nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
    graph = create_investigation_graph(nodes).compile()

    state = {"incident": incident, "investigation_id": "INV-007"}
    result = graph.invoke(state)

    assert result["termination_reason"] == "Investigation failure"
    assert result["failure"].failure_type == "TOOL_PARAMETER_INVALID"

def test_critic_human_review_routing(mock_gateway, mock_retriever, tool_registry, topology, incident):
    rca_res = RCADecisionResponse(
        response_id="R-1",
        task_type="rca",
        summary="Draft",
        observations=(),
        hypotheses=(),
        recommended_next_steps=()
    )
    
    critic_res = CriticDecisionResponse(
        response_id="C-1",
        task_type="critic",
        is_valid=False,
        decision="HUMAN_REVIEW",
        confidence_score=0.2,
        evidence_gaps=("topology",)
    )

    mock_gateway.generate.side_effect = lambda request: ValidatedModelResponse(
        response_id="1",
        task_type=request.task_type,
        raw_content="{}",
        parsed_response=(rca_res if request.task_type == "rca" else critic_res),
        execution_metadata=make_metadata(request.task_type)
    )

    nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
    graph = create_investigation_graph(nodes).compile()

    state = {"incident": incident, "investigation_id": "INV-008"}
    result = graph.invoke(state)

    assert result["termination_reason"] == "Escalated to human review"
    assert "Critic requested human review" in result["human_review"].reason

def test_critic_accept_low_confidence_demotion(mock_gateway, mock_retriever, tool_registry, topology, incident):
    rca_res = RCADecisionResponse(
        response_id="R-1",
        task_type="rca",
        summary="Draft",
        observations=(),
        hypotheses=(),
        recommended_next_steps=()
    )
    # ACCEPT but low confidence (0.5 < 0.8)
    critic_res = CriticDecisionResponse(
        response_id="C-1",
        task_type="critic",
        is_valid=True,
        findings=(),
        suggestions=(),
        decision="ACCEPT",
        confidence_score=0.5
    )
    tool_selection_res = ToolSelectionDecision(
        response_id="S-1",
        task_type="tool_selection",
        tool_name="log_pattern_search",
        reason="Query logs",
        parameters={},
        expected_evidence_type="log"
    )

    mock_gateway.generate.side_effect = lambda request: ValidatedModelResponse(
        response_id="1",
        task_type=request.task_type,
        raw_content="{}",
        parsed_response=(
            rca_res if request.task_type == "rca" else (
                critic_res if request.task_type == "critic" else tool_selection_res
            )
        ),
        execution_metadata=make_metadata(request.task_type)
    )

    original_max_iters = settings.INVESTIGATION_MAX_ITERATIONS
    settings.INVESTIGATION_MAX_ITERATIONS = 2

    try:
        nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
        graph = create_investigation_graph(nodes).compile()

        state = {"incident": incident, "investigation_id": "INV-009"}
        result = graph.invoke(state)

        # Should be demoted to CONTINUE_INVESTIGATION and then hit max iteration limit
        assert result["termination_reason"] == "Escalated to human review"
        assert "Max investigation iteration limit reached." in result["human_review"].reason
    finally:
        settings.INVESTIGATION_MAX_ITERATIONS = original_max_iters

def test_critic_accept_invalid_demotion(mock_gateway, mock_retriever, tool_registry, topology, incident):
    rca_res = RCADecisionResponse(
        response_id="R-1",
        task_type="rca",
        summary="Draft",
        observations=(),
        hypotheses=(),
        recommended_next_steps=()
    )
    # ACCEPT but invalid (is_valid=False)
    critic_res = CriticDecisionResponse(
        response_id="C-1",
        task_type="critic",
        is_valid=False,
        findings=("hallucinated",),
        suggestions=(),
        decision="ACCEPT",
        confidence_score=0.9
    )
    tool_selection_res = ToolSelectionDecision(
        response_id="S-1",
        task_type="tool_selection",
        tool_name="log_pattern_search",
        reason="Query logs",
        parameters={},
        expected_evidence_type="log"
    )

    mock_gateway.generate.side_effect = lambda request: ValidatedModelResponse(
        response_id="1",
        task_type=request.task_type,
        raw_content="{}",
        parsed_response=(
            rca_res if request.task_type == "rca" else (
                critic_res if request.task_type == "critic" else tool_selection_res
            )
        ),
        execution_metadata=make_metadata(request.task_type)
    )

    original_max_iters = settings.INVESTIGATION_MAX_ITERATIONS
    settings.INVESTIGATION_MAX_ITERATIONS = 2

    try:
        nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
        graph = create_investigation_graph(nodes).compile()

        state = {"incident": incident, "investigation_id": "INV-010"}
        result = graph.invoke(state)

        # Should be demoted and hit max iterations
        assert result["termination_reason"] == "Escalated to human review"
        assert "Max investigation iteration limit reached." in result["human_review"].reason
    finally:
        settings.INVESTIGATION_MAX_ITERATIONS = original_max_iters

def test_tool_execution_exception_failure(mock_gateway, mock_retriever, tool_registry, topology, incident):
    rca_res = RCADecisionResponse(
        response_id="R-1",
        task_type="rca",
        summary="Draft",
        observations=(),
        hypotheses=(),
        recommended_next_steps=()
    )
    critic_res = CriticDecisionResponse(
        response_id="C-1",
        task_type="critic",
        is_valid=False,
        decision="CONTINUE_INVESTIGATION",
        confidence_score=0.4,
        evidence_gaps=("log",)
    )
    tool_selection_res = ToolSelectionDecision(
        response_id="S-1",
        task_type="tool_selection",
        tool_name="log_pattern_search",
        reason="Query logs",
        parameters={},
        expected_evidence_type="log"
    )

    mock_gateway.generate.side_effect = lambda request: ValidatedModelResponse(
        response_id="1",
        task_type=request.task_type,
        raw_content="{}",
        parsed_response=(rca_res if request.task_type == "rca" else (critic_res if request.task_type == "critic" else tool_selection_res)),
        execution_metadata=make_metadata(request.task_type)
    )

    # Force tool.run to raise exception
    tool = tool_registry.get_tool("log_pattern_search")
    original_run = tool.run
    tool.run = MagicMock(side_effect=RuntimeError("Simulated tool crash"))

    try:
        nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
        graph = create_investigation_graph(nodes).compile()

        state = {"incident": incident, "investigation_id": "INV-011"}
        result = graph.invoke(state)

        assert result["termination_reason"] == "Investigation failure"
        assert result["failure"].failure_type == "TOOL_EXECUTION_FAILURE"
        assert "Simulated tool crash" in result["failure"].error_message
    finally:
        tool.run = original_run

def test_initialization_exception_failure(mock_gateway, mock_retriever, tool_registry, topology):
    nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
    graph = create_investigation_graph(nodes).compile()

    # Pass state with missing "incident" to force initialization failure
    state = {"investigation_id": "INV-012"}
    result = graph.invoke(state)

    assert result["termination_reason"] == "Investigation failure"
    assert result["failure"].failure_type == "INITIALIZATION_FAILURE"

def test_evidence_cap_enforcement(mock_gateway, mock_retriever, tool_registry, topology, incident):
    rca_res = RCADecisionResponse(
        response_id="R-1",
        task_type="rca",
        summary="Draft",
        observations=(),
        hypotheses=(),
        recommended_next_steps=()
    )
    critic_res_continue = CriticDecisionResponse(
        response_id="C-1",
        task_type="critic",
        is_valid=False,
        findings=(),
        suggestions=(),
        decision="CONTINUE_INVESTIGATION",
        confidence_score=0.4,
        evidence_gaps=("log",)
    )
    tool_selection_res = ToolSelectionDecision(
        response_id="S-1",
        task_type="tool_selection",
        tool_name="log_pattern_search",
        reason="Query logs",
        parameters={},
        expected_evidence_type="log"
    )
    critic_res_accept = CriticDecisionResponse(
        response_id="C-2",
        task_type="critic",
        is_valid=True,
        findings=(),
        suggestions=(),
        decision="ACCEPT",
        confidence_score=0.9
    )

    critic_call_count = 0
    mock_gateway.generate.side_effect = lambda request: ValidatedModelResponse(
        response_id="1",
        task_type=request.task_type,
        raw_content="{}",
        parsed_response=(
            rca_res if request.task_type == "rca" else (
                critic_res_continue if request.task_type == "critic" and critic_call_count == 0 else (
                    critic_res_accept if request.task_type == "critic" else tool_selection_res
                )
            )
        ),
        execution_metadata=make_metadata(request.task_type)
    )

    original_cap = settings.INVESTIGATION_MAX_EVIDENCE_ITEMS
    # Set cap to 2 (1 base incident + at most 1 more from tool)
    settings.INVESTIGATION_MAX_EVIDENCE_ITEMS = 2

    try:
        nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
        
        # We hook into nodes.evaluate_hypothesis to increment critic_call_count
        original_eval = nodes.evaluate_hypothesis
        def mock_eval(state):
            nonlocal critic_call_count
            res = original_eval(state)
            critic_call_count += 1
            return res
        nodes.evaluate_hypothesis = mock_eval

        graph = create_investigation_graph(nodes).compile()

        state = {"incident": incident, "investigation_id": "INV-013"}
        result = graph.invoke(state)

        assert result["termination_reason"] == "Investigation failure"
        assert result["failure"].failure_type == "TOOL_EXECUTION_FAILURE"
        assert "exceed max evidence items limit" in result["failure"].error_message
    finally:
        settings.INVESTIGATION_MAX_EVIDENCE_ITEMS = original_cap

def test_boundary_iteration_calls(mock_gateway, mock_retriever, tool_registry, topology, incident):
    rca_res = RCADecisionResponse(
        response_id="R-1",
        task_type="rca",
        summary="Draft",
        observations=(),
        hypotheses=(),
        recommended_next_steps=()
    )
    critic_res = CriticDecisionResponse(
        response_id="C-1",
        task_type="critic",
        is_valid=False,
        decision="CONTINUE_INVESTIGATION",
        confidence_score=0.4,
        evidence_gaps=("log",)
    )
    tool_selection_res = ToolSelectionDecision(
        response_id="S-1",
        task_type="tool_selection",
        tool_name="log_pattern_search",
        reason="Query logs",
        parameters={},
        expected_evidence_type="log"
    )

    mock_gateway.generate.side_effect = lambda request: ValidatedModelResponse(
        response_id="1",
        task_type=request.task_type,
        raw_content="{}",
        parsed_response=(rca_res if request.task_type == "rca" else (critic_res if request.task_type == "critic" else tool_selection_res)),
        execution_metadata=make_metadata(request.task_type)
    )

    original_max_iters = settings.INVESTIGATION_MAX_ITERATIONS
    settings.INVESTIGATION_MAX_ITERATIONS = 3

    try:
        nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
        graph = create_investigation_graph(nodes).compile()

        state = {"incident": incident, "investigation_id": "INV-LIMIT-ITER"}
        result = graph.invoke(state)

        assert result["termination_reason"] == "Escalated to human review"
        assert result["iteration_count"] == 3
        
        # Count actual calls to generate for task_type == "rca"
        rca_calls = [c for c in mock_gateway.generate.call_args_list if c[0][0].task_type == "rca"]
        assert len(rca_calls) == 3
    finally:
        settings.INVESTIGATION_MAX_ITERATIONS = original_max_iters

def test_boundary_tool_calls(mock_gateway, mock_retriever, tool_registry, topology, incident):
    rca_res = RCADecisionResponse(
        response_id="R-1",
        task_type="rca",
        summary="Draft",
        observations=(),
        hypotheses=(),
        recommended_next_steps=()
    )
    critic_res = CriticDecisionResponse(
        response_id="C-1",
        task_type="critic",
        is_valid=False,
        decision="CONTINUE_INVESTIGATION",
        confidence_score=0.4,
        evidence_gaps=("log",)
    )
    tool_selection_res = ToolSelectionDecision(
        response_id="S-1",
        task_type="tool_selection",
        tool_name="log_pattern_search",
        reason="Query logs",
        parameters={},
        expected_evidence_type="log"
    )

    mock_gateway.generate.side_effect = lambda request: ValidatedModelResponse(
        response_id="1",
        task_type=request.task_type,
        raw_content="{}",
        parsed_response=(rca_res if request.task_type == "rca" else (critic_res if request.task_type == "critic" else tool_selection_res)),
        execution_metadata=make_metadata(request.task_type)
    )

    tool = tool_registry.get_tool("log_pattern_search")
    original_run = tool.run
    tool_run_mock = MagicMock(side_effect=original_run)
    tool.run = tool_run_mock

    original_max_tools = settings.INVESTIGATION_MAX_TOOL_CALLS
    settings.INVESTIGATION_MAX_TOOL_CALLS = 2

    try:
        nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
        graph = create_investigation_graph(nodes).compile()

        state = {"incident": incident, "investigation_id": "INV-LIMIT-TOOL"}
        result = graph.invoke(state)

        assert result["termination_reason"] == "Escalated to human review"
        assert result["tool_call_count"] == 2
        assert tool_run_mock.call_count == 2
    finally:
        settings.INVESTIGATION_MAX_TOOL_CALLS = original_max_tools
        tool.run = original_run

def test_boundary_context_rebuild_calls(mock_gateway, mock_retriever, tool_registry, topology, incident):
    rca_res = RCADecisionResponse(
        response_id="R-1",
        task_type="rca",
        summary="Draft",
        observations=(),
        hypotheses=(),
        recommended_next_steps=()
    )
    critic_res = CriticDecisionResponse(
        response_id="C-1",
        task_type="critic",
        is_valid=False,
        decision="CONTINUE_INVESTIGATION",
        confidence_score=0.4,
        evidence_gaps=("log",)
    )
    tool_selection_res = ToolSelectionDecision(
        response_id="S-1",
        task_type="tool_selection",
        tool_name="log_pattern_search",
        reason="Query logs",
        parameters={},
        expected_evidence_type="log"
    )

    mock_gateway.generate.side_effect = lambda request: ValidatedModelResponse(
        response_id="1",
        task_type=request.task_type,
        raw_content="{}",
        parsed_response=(rca_res if request.task_type == "rca" else (critic_res if request.task_type == "critic" else tool_selection_res)),
        execution_metadata=make_metadata(request.task_type)
    )

    original_max_rebuilds = settings.INVESTIGATION_MAX_CONTEXT_REBUILDS
    settings.INVESTIGATION_MAX_CONTEXT_REBUILDS = 2

    try:
        nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
        original_rebuild = nodes.rebuild_context
        rebuild_mock = MagicMock(side_effect=original_rebuild)
        nodes.rebuild_context = rebuild_mock

        graph = create_investigation_graph(nodes).compile()

        state = {"incident": incident, "investigation_id": "INV-LIMIT-REBUILD"}
        result = graph.invoke(state)

        assert result["termination_reason"] == "Escalated to human review"
        assert result["context_rebuild_count"] == 2
        assert rebuild_mock.call_count == 2
    finally:
        settings.INVESTIGATION_MAX_CONTEXT_REBUILDS = original_max_rebuilds

def test_failure_routing_all_nodes(mock_gateway, mock_retriever, tool_registry, topology, incident):
    # 1. Context build failure
    mock_retriever.retrieve.side_effect = RuntimeError("Retrieval database offline")
    nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
    graph = create_investigation_graph(nodes).compile()
    
    state = {"incident": incident, "investigation_id": "INV-FAIL-1"}
    result = graph.invoke(state)
    assert result["termination_reason"] == "Investigation failure"
    assert result["failure"].failure_type == "CONTEXT_BUILD_FAILURE"
    assert "Retrieval database offline" in result["failure"].error_message

    # Reset retrieve mock
    mock_retriever.retrieve.side_effect = None

    # 2. Gateway failure during hypothesis generation
    mock_gateway.generate.side_effect = RuntimeError("Gateway timeout")
    nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
    graph = create_investigation_graph(nodes).compile()

    state = {"incident": incident, "investigation_id": "INV-FAIL-2"}
    result = graph.invoke(state)
    assert result["termination_reason"] == "Investigation failure"
    assert result["failure"].failure_type == "GATEWAY_FAILURE"
    
    # 3. Gateway failure during critic evaluation
    rca_res = RCADecisionResponse(
        response_id="R-1",
        task_type="rca",
        summary="Draft",
        observations=(),
        hypotheses=(),
        recommended_next_steps=()
    )
    def gateway_critic_fail_side_effect(request):
        if request.task_type == "critic":
            raise RuntimeError("Critic model overloaded")
        return ValidatedModelResponse(
            response_id="1",
            task_type=request.task_type,
            raw_content="{}",
            parsed_response=rca_res,
            execution_metadata=make_metadata(request.task_type)
        )
    mock_gateway.generate.side_effect = gateway_critic_fail_side_effect
    nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
    graph = create_investigation_graph(nodes).compile()

    state = {"incident": incident, "investigation_id": "INV-FAIL-3"}
    result = graph.invoke(state)
    assert result["termination_reason"] == "Investigation failure"
    assert result["failure"].failure_type == "GATEWAY_FAILURE"

    # 4. Context rebuild failure
    critic_res = CriticDecisionResponse(
        response_id="C-1",
        task_type="critic",
        is_valid=False,
        decision="CONTINUE_INVESTIGATION",
        confidence_score=0.4,
        evidence_gaps=("log",)
    )
    tool_selection_res = ToolSelectionDecision(
        response_id="S-1",
        task_type="tool_selection",
        tool_name="log_pattern_search",
        reason="Query logs",
        parameters={},
        expected_evidence_type="log"
    )
    def gateway_rebuild_fail_side_effect(request):
        return ValidatedModelResponse(
            response_id="1",
            task_type=request.task_type,
            raw_content="{}",
            parsed_response=(rca_res if request.task_type == "rca" else (critic_res if request.task_type == "critic" else tool_selection_res)),
            execution_metadata=make_metadata(request.task_type)
        )
    mock_gateway.generate.side_effect = gateway_rebuild_fail_side_effect
    
    retrievals = 0
    def retrieve_fail_on_rebuild(*args, **kwargs):
        nonlocal retrievals
        retrievals += 1
        if retrievals > 1:
            raise RuntimeError("Retriever offline on rebuild")
        from app.schemas.knowledge import KnowledgeBundle, RetrievalExecutionMetadata
        meta = RetrievalExecutionMetadata(
            vector_store_mode="memory",
            embedding_mode="mock",
            reranker_mode="flashrank",
            degraded_mode=False
        )
        return KnowledgeBundle(
            chunks=tuple(),
            applied_filters={},
            evidence_references=tuple(),
            search_summary="none",
            execution_metadata=meta
        )
    mock_retriever.retrieve.side_effect = retrieve_fail_on_rebuild
    nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
    graph = create_investigation_graph(nodes).compile()

    state = {"incident": incident, "investigation_id": "INV-FAIL-4"}
    result = graph.invoke(state)
    assert result["termination_reason"] == "Investigation failure"
    assert result["failure"].failure_type == "CONTEXT_REBUILD_FAILURE"

    # Reset retrieve mock
    mock_retriever.retrieve.side_effect = None

    # 5. Finalization failure
    from app.services.orchestration.nodes import logger as nodes_logger
    original_info = nodes_logger.info
    def mock_logging(msg, *args, **kwargs):
        if "Finalizing successful RCA" in msg:
            raise RuntimeError("Logging crash")
        original_info(msg, *args, **kwargs)
    nodes_logger.info = mock_logging

    mock_gateway.generate.side_effect = lambda request: ValidatedModelResponse(
        response_id="1",
        task_type=request.task_type,
        raw_content="{}",
        parsed_response=(rca_res if request.task_type == "rca" else CriticDecisionResponse(
            response_id="C-2",
            task_type="critic",
            is_valid=True,
            decision="ACCEPT",
            confidence_score=0.9
        )),
        execution_metadata=make_metadata(request.task_type)
    )
    nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
    graph = create_investigation_graph(nodes).compile()

    try:
        state = {"incident": incident, "investigation_id": "INV-FAIL-5"}
        result = graph.invoke(state)
        assert result.get("termination_reason") == "Finalization failure"
        assert result["failure"].failure_type == "FINALIZE_RCA_FAILURE"
    finally:
        nodes_logger.info = original_info

    # 6. Evidence validation failure (invalid service not in topology)
    from app.tools.log_tool import LogSearchResponse
    from app.schemas.telemetry import LogRecord, EnvironmentName
    tool = tool_registry.get_tool("log_pattern_search")
    original_run = tool.run
    fake_log = LogRecord(
        timestamp="2026-01-15T14:00:00Z",
        log_id="L-1",
        service="nonexistent-service",
        environment=EnvironmentName.PRODUCTION_SIM,
        instance_id="inst-1",
        level="ERROR",
        logger="syslog",
        message="Database connection timeout",
        template_id="temp-1",
        scenario_id="SCN-DB-POOL-001"
    )
    tool.run = MagicMock(return_value=LogSearchResponse(
        logs=[fake_log]
    ))
    mock_gateway.generate.side_effect = gateway_rebuild_fail_side_effect
    nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
    graph = create_investigation_graph(nodes).compile()

    try:
        state = {"incident": incident, "investigation_id": "INV-FAIL-6"}
        result = graph.invoke(state)
        assert result["termination_reason"] == "Investigation failure"
        assert result["failure"].failure_type == "TOOL_EXECUTION_FAILURE"
        assert "not present in the service topology" in result["failure"].error_message
    finally:
        tool.run = original_run

    # 7. Human review escalation failure
    def mock_logging_human(msg, *args, **kwargs):
        if "Investigation escalated to human review" in msg:
            raise RuntimeError("Logging crash in human review")
        original_info(msg, *args, **kwargs)
    nodes_logger.info = mock_logging_human

    mock_gateway.generate.side_effect = lambda request: ValidatedModelResponse(
        response_id="1",
        task_type=request.task_type,
        raw_content="{}",
        parsed_response=(rca_res if request.task_type == "rca" else CriticDecisionResponse(
            response_id="C-2",
            task_type="critic",
            is_valid=True,
            decision="HUMAN_REVIEW",
            confidence_score=0.9
        )),
        execution_metadata=make_metadata(request.task_type)
    )
    nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
    graph = create_investigation_graph(nodes).compile()

    try:
        state = {"incident": incident, "investigation_id": "INV-FAIL-7"}
        result = graph.invoke(state)
        assert result["termination_reason"] == "Human review escalation failure"
        assert result["failure"].failure_type == "HUMAN_REVIEW_FAILURE"
    finally:
        nodes_logger.info = original_info

def test_terminal_nodes_reacheability(mock_gateway, mock_retriever, tool_registry, topology, incident):
    rca_res = RCADecisionResponse(
        response_id="R-1",
        task_type="rca",
        summary="Draft",
        observations=(),
        hypotheses=(),
        recommended_next_steps=()
    )
    critic_res_accept = CriticDecisionResponse(
        response_id="C-1",
        task_type="critic",
        is_valid=True,
        findings=(),
        suggestions=(),
        decision="ACCEPT",
        confidence_score=0.9
    )
    mock_gateway.generate.side_effect = lambda request: ValidatedModelResponse(
        response_id="1",
        task_type=request.task_type,
        raw_content="{}",
        parsed_response=(rca_res if request.task_type == "rca" else critic_res_accept),
        execution_metadata=make_metadata(request.task_type)
    )

    nodes = WorkflowNodes(mock_gateway, mock_retriever, tool_registry, topology)
    nodes.select_tool = MagicMock(side_effect=nodes.select_tool)
    nodes.execute_tool = MagicMock(side_effect=nodes.execute_tool)
    nodes.human_review = MagicMock(side_effect=nodes.human_review)
    nodes.failure = MagicMock(side_effect=nodes.failure)

    graph = create_investigation_graph(nodes).compile()
    state = {"incident": incident, "investigation_id": "INV-TERM-1"}
    result = graph.invoke(state)

    assert result["termination_reason"] == "RCA accepted by critic"
    assert nodes.select_tool.call_count == 0
    assert nodes.execute_tool.call_count == 0
    assert nodes.human_review.call_count == 0
    assert nodes.failure.call_count == 0

def test_no_arbitrary_routing(incident):
    from pydantic import ValidationError
    # Assert that an unsupported critic decision cannot even be instantiated
    with pytest.raises(ValidationError):
        CriticDecisionResponse(
            response_id="C-1",
            task_type="critic",
            is_valid=True,
            findings=(),
            suggestions=(),
            decision="GOTO_FINAL_NODE_DIRECTLY",
            confidence_score=0.9
        )
