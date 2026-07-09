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
