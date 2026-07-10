import pytest
from datetime import datetime, timezone
from pydantic import ValidationError
from evals.schemas import (
    DatasetSplit,
    ScenarioAmbiguity,
    ExpectedTerminalOutcome,
    EvaluationMode,
    MetricStatus,
    GoldenRCALabels,
    GoldenScenario,
    NodeTimingRecord,
    ToolCallTraceRecord,
    CriticTraceRecord,
    EvaluationTrace,
    EvaluationRunManifest,
    MetricResult,
    ScenarioEvaluationResult,
)

# --- 1. GOLDEN SCENARIO TESTS ---

def test_golden_scenario_valid_minimal():
    labels = GoldenRCALabels(
        affected_service="checkout-service",
        fault_category="database_connection_pool",
        root_cause_code="DB_POOL_MAX_CONNECTIONS_REGRESSION",
        root_cause_summary="Invalid configuration"
    )
    
    scenario = GoldenScenario(
        scenario_id="SCN-001",
        incident_id="INC-001",
        split=DatasetSplit.DEV,
        ambiguity=ScenarioAmbiguity.UNAMBIGUOUS,
        expected_terminal_outcome=ExpectedTerminalOutcome.FINALIZE_RCA,
        acceptable_terminal_outcomes=[ExpectedTerminalOutcome.FINALIZE_RCA],
        labels=labels
    )
    
    assert scenario.scenario_id == "SCN-001"
    assert scenario.split == "dev"
    assert scenario.expected_terminal_outcome == "finalize_rca"


def test_golden_scenario_valid_full():
    labels = GoldenRCALabels(
        affected_service="checkout-service",
        fault_category="database_connection_pool",
        root_cause_code="DB_POOL_MAX_CONNECTIONS_REGRESSION",
        root_cause_summary="Invalid configuration",
        acceptable_equivalent_root_cause_codes=["DB_POOL_ERROR"],
        forbidden_unsupported_cause_codes=["REDIS_OUTAGE"]
    )
    
    scenario = GoldenScenario(
        scenario_id="SCN-001",
        incident_id="INC-001",
        split=DatasetSplit.DEV,
        ambiguity=ScenarioAmbiguity.UNAMBIGUOUS,
        expected_terminal_outcome=ExpectedTerminalOutcome.FINALIZE_RCA,
        acceptable_terminal_outcomes=[ExpectedTerminalOutcome.FINALIZE_RCA, ExpectedTerminalOutcome.HUMAN_REVIEW],
        labels=labels,
        required_evidence_ids=["EVID-1", "EVID-2"],
        required_tools=["tool_a"],
        acceptable_tools=["tool_b"],
        forbidden_tools=["tool_c"],
        acceptable_root_cause_codes=["DB_POOL_ERROR"],
        forbidden_unsupported_causes=["REDIS_OUTAGE"],
        acceptable_remediation_codes=["REMEDY_1"],
        difficulty="medium",
        tags=["tag1", "tag2"]
    )
    
    assert scenario.required_evidence_ids == ["EVID-1", "EVID-2"]
    assert scenario.required_tools == ["tool_a"]


def test_golden_scenario_invalid_split():
    labels = GoldenRCALabels(
        affected_service="checkout-service",
        fault_category="database_connection_pool",
        root_cause_code="DB_POOL_MAX_CONNECTIONS_REGRESSION",
        root_cause_summary="Invalid configuration"
    )
    with pytest.raises(ValidationError):
        GoldenScenario(
            scenario_id="SCN-001",
            incident_id="INC-001",
            split="invalid-split",  # type: ignore
            ambiguity=ScenarioAmbiguity.UNAMBIGUOUS,
            expected_terminal_outcome=ExpectedTerminalOutcome.FINALIZE_RCA,
            acceptable_terminal_outcomes=[ExpectedTerminalOutcome.FINALIZE_RCA],
            labels=labels
        )


def test_golden_scenario_invalid_ambiguity():
    labels = GoldenRCALabels(
        affected_service="checkout-service",
        fault_category="database_connection_pool",
        root_cause_code="DB_POOL_MAX_CONNECTIONS_REGRESSION",
        root_cause_summary="Invalid configuration"
    )
    with pytest.raises(ValidationError):
        GoldenScenario(
            scenario_id="SCN-001",
            incident_id="INC-001",
            split=DatasetSplit.DEV,
            ambiguity="highly-ambiguous",  # type: ignore
            expected_terminal_outcome=ExpectedTerminalOutcome.FINALIZE_RCA,
            acceptable_terminal_outcomes=[ExpectedTerminalOutcome.FINALIZE_RCA],
            labels=labels
        )


def test_expected_outcome_missing_from_acceptable():
    labels = GoldenRCALabels(
        affected_service="checkout-service",
        fault_category="database_connection_pool",
        root_cause_code="DB_POOL_MAX_CONNECTIONS_REGRESSION",
        root_cause_summary="Invalid configuration"
    )
    with pytest.raises(ValidationError) as exc:
        GoldenScenario(
            scenario_id="SCN-001",
            incident_id="INC-001",
            split=DatasetSplit.DEV,
            ambiguity=ScenarioAmbiguity.UNAMBIGUOUS,
            expected_terminal_outcome=ExpectedTerminalOutcome.FINALIZE_RCA,
            acceptable_terminal_outcomes=[ExpectedTerminalOutcome.HUMAN_REVIEW],  # missing finalize_rca
            labels=labels
        )
    assert "expected_terminal_outcome" in str(exc.value)


def test_conflicting_tool_categories():
    labels = GoldenRCALabels(
        affected_service="checkout-service",
        fault_category="database_connection_pool",
        root_cause_code="DB_POOL_MAX_CONNECTIONS_REGRESSION",
        root_cause_summary="Invalid configuration"
    )
    
    # Conflict between required_tools and forbidden_tools
    with pytest.raises(ValidationError) as exc1:
        GoldenScenario(
            scenario_id="SCN-001",
            incident_id="INC-001",
            split=DatasetSplit.DEV,
            ambiguity=ScenarioAmbiguity.UNAMBIGUOUS,
            expected_terminal_outcome=ExpectedTerminalOutcome.FINALIZE_RCA,
            acceptable_terminal_outcomes=[ExpectedTerminalOutcome.FINALIZE_RCA],
            labels=labels,
            required_tools=["tool_a"],
            forbidden_tools=["tool_a"]
        )
    assert "required_tools and forbidden_tools overlap" in str(exc1.value)

    # Conflict between acceptable_tools and forbidden_tools
    with pytest.raises(ValidationError) as exc2:
        GoldenScenario(
            scenario_id="SCN-001",
            incident_id="INC-001",
            split=DatasetSplit.DEV,
            ambiguity=ScenarioAmbiguity.UNAMBIGUOUS,
            expected_terminal_outcome=ExpectedTerminalOutcome.FINALIZE_RCA,
            acceptable_terminal_outcomes=[ExpectedTerminalOutcome.FINALIZE_RCA],
            labels=labels,
            acceptable_tools=["tool_b"],
            forbidden_tools=["tool_b"]
        )
    assert "acceptable_tools and forbidden_tools overlap" in str(exc2.value)


def test_duplicate_policy_rejection():
    labels = GoldenRCALabels(
        affected_service="checkout-service",
        fault_category="database_connection_pool",
        root_cause_code="DB_POOL_MAX_CONNECTIONS_REGRESSION",
        root_cause_summary="Invalid configuration"
    )
    with pytest.raises(ValidationError) as exc:
        GoldenScenario(
            scenario_id="SCN-001",
            incident_id="INC-001",
            split=DatasetSplit.DEV,
            ambiguity=ScenarioAmbiguity.UNAMBIGUOUS,
            expected_terminal_outcome=ExpectedTerminalOutcome.FINALIZE_RCA,
            acceptable_terminal_outcomes=[ExpectedTerminalOutcome.FINALIZE_RCA],
            labels=labels,
            required_evidence_ids=["EVID-1", "EVID-1"]  # duplicate
        )
    assert "Duplicate values not allowed" in str(exc.value)


# --- 2. EVALUATION TRACE TESTS ---

def test_evaluation_trace_minimal():
    trace = EvaluationTrace(
        scenario_id="SCN-001",
        investigation_id="INV-1234"
    )
    assert trace.scenario_id == "SCN-001"
    assert trace.iteration_count is None
    assert trace.total_latency_ms is None


def test_evaluation_trace_full():
    timing = NodeTimingRecord(
        node_name="initialize",
        started_at=datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 7, 10, 12, 0, 1, tzinfo=timezone.utc),
        duration_ms=1000.0
    )
    tool_call = ToolCallTraceRecord(
        tool_name="log_pattern_search",
        parameters={"pattern": "error"},
        iteration=0,
        success=True,
        evidence_ids_returned=["EVID-1"],
        duration_ms=250.0
    )
    critic = CriticTraceRecord(
        iteration=0,
        decision="CONTINUE_INVESTIGATION",
        confidence=0.5,
        is_valid=True,
        reason="Missing evidence",
        evidence_count_at_decision=0
    )
    trace = EvaluationTrace(
        scenario_id="SCN-001",
        investigation_id="INV-1234",
        node_sequence=["initialize", "build_context"],
        node_timings=[timing],
        iteration_count=1,
        tool_call_count=1,
        tool_calls=[tool_call],
        evidence_ids=["EVID-1"],
        critic_records=[critic],
        context_rebuild_count=1,
        provider_used="groq",
        fallback_occurrence=False,
        termination_reason="Success",
        final_terminal_type="finalize_rca",
        total_latency_ms=1250.0
    )
    assert trace.iteration_count == 1
    assert trace.fallback_occurrence is False
    assert len(trace.node_timings) == 1
    assert len(trace.tool_calls) == 1
    assert len(trace.critic_records) == 1


def test_trace_negative_bounds():
    with pytest.raises(ValidationError):
        EvaluationTrace(
            scenario_id="SCN-001",
            investigation_id="INV-1234",
            iteration_count=-1
        )
    with pytest.raises(ValidationError):
        EvaluationTrace(
            scenario_id="SCN-001",
            investigation_id="INV-1234",
            tool_call_count=-5
        )
    with pytest.raises(ValidationError):
        EvaluationTrace(
            scenario_id="SCN-001",
            investigation_id="INV-1234",
            total_latency_ms=-100.0
        )


# --- 3. NODE TIMING TESTS ---

def test_node_timing_valid():
    start = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 7, 10, 12, 0, 5, tzinfo=timezone.utc)
    t = NodeTimingRecord(
        node_name="select_tool",
        started_at=start,
        finished_at=end,
        duration_ms=5000.0
    )
    assert t.duration_ms == 5000.0


def test_node_timing_impossible_order():
    start = datetime(2026, 7, 10, 12, 0, 5, tzinfo=timezone.utc)
    end = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        NodeTimingRecord(
            node_name="select_tool",
            started_at=start,
            finished_at=end,
            duration_ms=0.0
        )


# --- 4. TOOL CALL TRACE TESTS ---

def test_tool_call_trace():
    t = ToolCallTraceRecord(
        tool_name="metric_window_analysis",
        parameters={"window": "5m"},
        iteration=0,
        success=True,
        duration_ms=20.0
    )
    assert t.parameters == {"window": "5m"}


def test_tool_call_negative_bounds():
    with pytest.raises(ValidationError):
        ToolCallTraceRecord(
            tool_name="metric_window_analysis",
            iteration=-2
        )
    with pytest.raises(ValidationError):
        ToolCallTraceRecord(
            tool_name="metric_window_analysis",
            duration_ms=-1.0
        )


# --- 5. CRITIC TRACE TESTS ---

def test_critic_trace_record():
    c = CriticTraceRecord(
        iteration=1,
        decision="ACCEPT",
        confidence=0.85,
        is_valid=True,
        evidence_count_at_decision=3
    )
    assert c.confidence == 0.85


def test_critic_trace_confidence_bounds():
    with pytest.raises(ValidationError):
        CriticTraceRecord(
            iteration=1,
            decision="ACCEPT",
            confidence=-0.1,  # below 0
            is_valid=True
        )
    with pytest.raises(ValidationError):
        CriticTraceRecord(
            iteration=1,
            decision="ACCEPT",
            confidence=1.1,  # above 1
            is_valid=True
        )


# --- 6. RUN MANIFEST TESTS ---

def test_run_manifest_offline():
    manifest = EvaluationRunManifest(
        run_id="run_1",
        evaluation_version="1.0",
        evaluation_mode=EvaluationMode.METRIC_ONLY,
        started_at=datetime.now(timezone.utc)
    )
    assert manifest.evaluation_mode == "metric_only"
    assert manifest.provider is None
    assert manifest.generation_model is None


def test_run_manifest_live():
    manifest = EvaluationRunManifest(
        run_id="run_1",
        evaluation_version="1.0",
        evaluation_mode=EvaluationMode.LIVE,
        started_at=datetime.now(timezone.utc),
        provider="groq",
        generation_model="llama-3.3-70b-versatile",
        embedding_model="gemini-embedding-2-preview",
        embedding_dimension=3072,
        graph_budgets={"max_iters": 3}
    )
    assert manifest.provider == "groq"
    assert manifest.embedding_dimension == 3072
    assert manifest.graph_budgets == {"max_iters": 3}


def test_run_manifest_no_secrets():
    # Make sure manifest class has no API key or token fields
    fields = EvaluationRunManifest.model_fields.keys()
    secret_keywords = ["key", "token", "auth", "secret", "credentials"]
    for field in fields:
        for kw in secret_keywords:
            assert kw not in field.lower(), f"Manifest contains field: {field}"


# --- 7. METRIC RESULT ENVELOPE TESTS ---

def test_metric_result_success():
    m = MetricResult(
        metric_name="Evidence Recall",
        status=MetricStatus.SUCCESS,
        value=1.0
    )
    assert m.value == 1.0
    assert m.status == "success"


def test_metric_result_success_zero():
    m = MetricResult(
        metric_name="Evidence Recall",
        status=MetricStatus.SUCCESS,
        value=0.0
    )
    assert m.value == 0.0


def test_metric_result_na():
    m = MetricResult(
        metric_name="Evidence Recall",
        status=MetricStatus.NOT_APPLICABLE,
        reason="Scenario does not have required evidence"
    )
    assert m.value is None
    assert m.reason == "Scenario does not have required evidence"


def test_metric_result_failed():
    m = MetricResult(
        metric_name="Evidence Recall",
        status=MetricStatus.FAILED,
        error_type="GatewayError",
        reason="Gateway connection timed out"
    )
    assert m.value is None
    assert m.error_type == "GatewayError"


def test_metric_result_invalid_combinations():
    # Success without value
    with pytest.raises(ValidationError):
        MetricResult(
            metric_name="Recall",
            status=MetricStatus.SUCCESS
        )

    # Success with error_type
    with pytest.raises(ValidationError):
        MetricResult(
            metric_name="Recall",
            status=MetricStatus.SUCCESS,
            value=0.8,
            error_type="Error"
        )

    # NA with value
    with pytest.raises(ValidationError):
        MetricResult(
            metric_name="Recall",
            status=MetricStatus.NOT_APPLICABLE,
            value=0.5,
            reason="not applicable"
        )

    # Failed with value
    with pytest.raises(ValidationError):
        MetricResult(
            metric_name="Recall",
            status=MetricStatus.FAILED,
            value=0.5,
            error_type="Error"
        )


# --- 8. SCENARIO RESULT TESTS ---

def test_scenario_result():
    m1 = MetricResult(
        metric_name="Evidence Recall",
        status=MetricStatus.SUCCESS,
        value=1.0
    )
    m2 = MetricResult(
        metric_name="Citation Validity",
        status=MetricStatus.SUCCESS,
        value=1.0
    )
    result = ScenarioEvaluationResult(
        run_id="run_1",
        scenario_id="SCN-001",
        terminal_outcome="finalize_rca",
        metrics=[m1, m2],
        warnings=["Some latency warning"]
    )
    assert result.scenario_id == "SCN-001"
    assert len(result.metrics) == 2
    assert result.warnings == ["Some latency warning"]
