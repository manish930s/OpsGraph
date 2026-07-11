import pytest
from evals.schemas import (
    GoldenScenario,
    GoldenRCALabels,
    EvaluationTrace,
    EvaluationMode,
    MetricStatus,
    DatasetSplit,
    ScenarioAmbiguity,
    ExpectedTerminalOutcome,
    ToolCallTraceRecord,
    NodeTimingRecord
)
from evals.runner import (
    evaluate_scenario,
    evaluate_mock_graph,
    evaluate_offline_component
)

# Mock Golden Scenario Helper
def make_mock_scenario(
    scenario_id="SCN-001",
    incident_id="INC-001",
    required_evidence_ids=None,
    required_tools=None,
    acceptable_tools=None,
    forbidden_tools=None,
    acceptable_terminal_outcomes=None
) -> GoldenScenario:
    labels = GoldenRCALabels(
        affected_service="checkout-service",
        fault_category="database_connection_pool",
        root_cause_code="DB_POOL_MAX_CONNECTIONS_REGRESSION",
        root_cause_summary="Invalid connection pool configuration"
    )
    return GoldenScenario(
        schema_version="1.0",
        scenario_id=scenario_id,
        incident_id=incident_id,
        split=DatasetSplit.DEV,
        ambiguity=ScenarioAmbiguity.UNAMBIGUOUS,
        expected_terminal_outcome=ExpectedTerminalOutcome.FINALIZE_RCA,
        acceptable_terminal_outcomes=acceptable_terminal_outcomes or [ExpectedTerminalOutcome.FINALIZE_RCA],
        labels=labels,
        required_evidence_ids=required_evidence_ids or ["EV-1"],
        required_tools=required_tools or ["log_pattern_search"],
        acceptable_tools=acceptable_tools or ["metric_window_analysis"],
        forbidden_tools=forbidden_tools or ["forbidden_tool_a"]
    )


# --- 1. SUCCESSFUL EVALUATION ---

def test_successful_evaluation_mock_graph():
    scenario = make_mock_scenario()
    
    # Valid timing record timezone-aware
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    
    trace = EvaluationTrace(
        scenario_id="SCN-001",
        investigation_id="INV-001",
        node_sequence=["initialize", "build_context"],
        node_timings=[NodeTimingRecord(node_name="initialize", started_at=now, finished_at=now)],
        iteration_count=1,
        tool_call_count=1,
        tool_calls=[ToolCallTraceRecord(tool_name="log_pattern_search", success=True)],
        evidence_ids=["EV-1"],
        context_rebuild_count=1,
        final_terminal_type="finalize_rca"
    )
    
    predicted_rca = {
        "supporting_evidence_references": ["EV-1"],
        "contradicting_evidence_references": [],
        "affected_service": "checkout-service",
        "fault_category": "database_connection_pool",
        "root_cause_code": "DB_POOL_MAX_CONNECTIONS_REGRESSION"
    }

    result = evaluate_mock_graph(scenario, trace, predicted_rca)
    
    assert result.scenario_id == "SCN-001"
    assert result.terminal_outcome == "finalize_rca"
    assert len(result.errors) == 0
    assert len(result.warnings) == 0
    assert len(result.metrics) > 0

    # Verify metric outputs
    metric_map = {m.metric_name: m for m in result.metrics}
    
    assert metric_map["Citation ID Validity"].status == MetricStatus.SUCCESS
    assert metric_map["Citation ID Validity"].value == 1.0
    
    assert metric_map["Required Evidence Recall"].status == MetricStatus.SUCCESS
    assert metric_map["Required Evidence Recall"].value == 1.0

    assert metric_map["Terminal Outcome Correctness"].status == MetricStatus.SUCCESS
    assert metric_map["Terminal Outcome Correctness"].value == 1.0

    assert metric_map["Iteration Budget Utilization"].status == MetricStatus.SUCCESS
    assert metric_map["Iteration Budget Utilization"].value == 1.0 / 3.0

    assert metric_map["Affected Service Correctness"].status == MetricStatus.SUCCESS
    assert metric_map["Affected Service Correctness"].value == 1.0

    assert metric_map["Required Tool Recall"].status == MetricStatus.SUCCESS
    assert metric_map["Required Tool Recall"].value == 1.0


# --- 2. MISSING OPTIONAL TRACE & GRADUAL DEGRADATION ---

def test_missing_optional_trace():
    scenario = make_mock_scenario()
    predicted_rca = {
        "supporting_evidence_references": ["EV-1"],
        "contradicting_evidence_references": [],
        "affected_service": "checkout-service",
        "fault_category": "database_connection_pool",
        "root_cause_code": "DB_POOL_MAX_CONNECTIONS_REGRESSION"
    }

    # Trace is None
    result = evaluate_mock_graph(scenario, None, predicted_rca)
    
    assert result.scenario_id == "SCN-001"
    assert result.terminal_outcome is None
    assert len(result.errors) == 0
    assert "EvaluationTrace is missing." in result.warnings

    # Validate that trace-requiring metrics are NOT_APPLICABLE
    metric_map = {m.metric_name: m for m in result.metrics}
    
    assert metric_map["Required Evidence Recall"].status == MetricStatus.NOT_APPLICABLE
    assert metric_map["Terminal Outcome Correctness"].status == MetricStatus.NOT_APPLICABLE
    assert metric_map["Iteration Budget Utilization"].status == MetricStatus.NOT_APPLICABLE
    assert metric_map["Required Tool Recall"].status == MetricStatus.NOT_APPLICABLE


# --- 3. MISSING RCA LABELS & WARNINGS ---

def test_missing_rca_and_labels():
    scenario = make_mock_scenario()
    
    # Missing predicted RCA
    result = evaluate_mock_graph(scenario, None, None)
    assert "Predicted RCA is missing." in result.warnings

    metric_map = {m.metric_name: m for m in result.metrics}
    assert metric_map["Citation ID Validity"].status == MetricStatus.NOT_APPLICABLE
    assert metric_map["Affected Service Correctness"].status == MetricStatus.NOT_APPLICABLE


# --- 4. EXCEPTION HANDLING ---

def test_unexpected_metric_exception_handling():
    # Pass a GoldenScenario subclass that raises during model_dump
    class BrokenLabelsRCALabels(GoldenRCALabels):
        def model_dump(self, *args, **kwargs) -> dict[str, Any]:
            raise RuntimeError("Simulated database label crash")

    labels = BrokenLabelsRCALabels(
        affected_service="checkout-service",
        fault_category="database_connection_pool",
        root_cause_code="DB_POOL_MAX_CONNECTIONS_REGRESSION",
        root_cause_summary="Invalid configuration"
    )

    scenario = GoldenScenario(
        schema_version="1.0",
        scenario_id="SCN-001",
        incident_id="INC-001",
        split=DatasetSplit.DEV,
        ambiguity=ScenarioAmbiguity.UNAMBIGUOUS,
        expected_terminal_outcome=ExpectedTerminalOutcome.FINALIZE_RCA,
        acceptable_terminal_outcomes=[ExpectedTerminalOutcome.FINALIZE_RCA],
        labels=labels,
        required_evidence_ids=["EV-1"],
        required_tools=["log_pattern_search"],
        acceptable_tools=["metric_window_analysis"],
        forbidden_tools=["forbidden_tool_a"]
    )

    result = evaluate_mock_graph(scenario, None, {})

    assert len(result.errors) > 0
    assert any("Unexpected error during metric evaluation" in e for e in result.errors)


# --- 5. INVALID INPUTS REJECTION ---

def test_invalid_scenario_and_trace_rejection():
    # Invalid scenario
    result_invalid_scn = evaluate_mock_graph("Not A Scenario Object", None, None)
    assert len(result_invalid_scn.errors) > 0
    assert "Invalid scenario object" in result_invalid_scn.errors[0]

    # Invalid trace
    scenario = make_mock_scenario()
    result_invalid_trace = evaluate_mock_graph(scenario, "Not A Trace Object", None)
    assert len(result_invalid_trace.errors) > 0
    assert "Invalid trace object" in result_invalid_trace.errors[0]


# --- 6. MANIFEST & PLATFORM METADATA ---

def test_manifest_creation():
    scenario = make_mock_scenario()
    result = evaluate_offline_component(scenario, None, None)
    
    # Check that manifest can be structured and populated, run_id matches
    assert result.run_id is not None
    assert result.scenario_id == "SCN-001"
