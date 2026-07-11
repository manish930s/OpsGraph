import json
import pytest
from evals.schemas import MetricStatus, ToolCallTraceRecord
from evals.tool_metrics import (
    normalize_tool_name,
    extract_tool_names_from_trace,
    evaluate_required_tool_recall,
    evaluate_allowed_tool_precision,
    evaluate_forbidden_tool_invocation_count,
    evaluate_forbidden_tool_compliance,
    evaluate_unnecessary_tool_call_count,
    evaluate_duplicate_tool_call_count,
    evaluate_tool_call_efficiency,
    evaluate_tool_selection
)

# --- 1. NORMALIZATION POLICY TESTS ---

def test_normalization_policy():
    # Trim leading/trailing whitespace & lowercase
    assert normalize_tool_name("  Log_Pattern_Search  ") == "log_pattern_search"
    # Preserve internal characters and separators
    assert normalize_tool_name("metric-window-analysis") == "metric-window-analysis"
    assert normalize_tool_name("deploy_event_search") == "deploy_event_search"
    # Return None for empty/missing values
    assert normalize_tool_name(None) is None
    assert normalize_tool_name("   ") is None


# --- 2. TRACE ADAPTER TESTS ---

def test_trace_adapter():
    # Simple strings sequence
    trace_str = ["log_pattern_search", "metric_window_analysis"]
    assert extract_tool_names_from_trace(trace_str) == trace_str

    # Dictionary sequence
    trace_dict = [
        {"tool_name": "log_pattern_search"},
        {"tool_name": "metric_window_analysis"},
        None,
        {"some_other_field": "val"}
    ]
    assert extract_tool_names_from_trace(trace_dict) == ["log_pattern_search", "metric_window_analysis"]

    # ToolCallTraceRecord sequence (Pydantic model)
    trace_records = [
        ToolCallTraceRecord(tool_name="log_pattern_search", success=True),
        ToolCallTraceRecord(tool_name="metric_window_analysis", success=False),  # preserve failed
        ToolCallTraceRecord(tool_name="log_pattern_search", success=True)        # preserve duplicates
    ]
    assert extract_tool_names_from_trace(trace_records) == [
        "log_pattern_search", "metric_window_analysis", "log_pattern_search"
    ]

    # Non-mutation check
    orig = list(trace_records)
    extract_tool_names_from_trace(trace_records)
    assert trace_records == orig

    # Empty inputs
    assert extract_tool_names_from_trace([]) == []
    assert extract_tool_names_from_trace(None) == []


# --- 3. REQUIRED TOOL RECALL TESTS ---

def test_required_tool_recall():
    required = ["log_pattern_search", "metric_window_analysis", "deployment_event_search"]

    # 1. Full recall
    observed_full = ["log_pattern_search", "metric_window_analysis", "deployment_event_search"]
    res = evaluate_required_tool_recall(observed_full, required)
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 1.0

    # 2. Partial recall
    observed_partial = ["log_pattern_search", "deployment_event_search"]
    res = evaluate_required_tool_recall(observed_partial, required)
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 2.0 / 3.0

    # 3. Zero recall
    observed_zero = ["service_topology_lookup"]
    res = evaluate_required_tool_recall(observed_zero, required)
    assert res.value == 0.0

    # 4. Duplicate calls do not increase recall beyond 1.0
    observed_dups = ["log_pattern_search", "log_pattern_search", "metric_window_analysis", "deployment_event_search"]
    res = evaluate_required_tool_recall(observed_dups, required)
    assert res.value == 1.0

    # 5. Extra acceptable and irrelevant tools do not reduce recall
    observed_extras = ["log_pattern_search", "metric_window_analysis", "deployment_event_search", "time_window_adjuster", "unknown_tool"]
    res = evaluate_required_tool_recall(observed_extras, required)
    assert res.value == 1.0

    # 6. Empty required set -> NOT_APPLICABLE
    res = evaluate_required_tool_recall(["log_pattern_search"], [])
    assert res.status == MetricStatus.NOT_APPLICABLE

    # 7. Empty observed calls
    res = evaluate_required_tool_recall([], required)
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 0.0


# --- 4. ALLOWED TOOL PRECISION TESTS ---

def test_allowed_tool_precision():
    required = ["log_pattern_search"]
    acceptable = ["metric_window_analysis"]

    # 1. All required tools only
    res = evaluate_allowed_tool_precision(["log_pattern_search"], required, acceptable)
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 1.0

    # 2. Required plus acceptable tools
    res = evaluate_allowed_tool_precision(["log_pattern_search", "metric_window_analysis"], required, acceptable)
    assert res.value == 1.0

    # 3. One irrelevant tool
    res = evaluate_allowed_tool_precision(["log_pattern_search", "time_window_adjuster"], required, acceptable)
    assert res.value == 0.5

    # 4. One forbidden tool
    res = evaluate_allowed_tool_precision(["log_pattern_search", "forbidden_tool"], required, acceptable)
    assert res.value == 0.5

    # 5. Unknown tool
    res = evaluate_allowed_tool_precision(["unknown_tool"], required, acceptable)
    assert res.value == 0.0

    # 6. Duplicates do not inflate unique precision
    res = evaluate_allowed_tool_precision(["log_pattern_search", "log_pattern_search", "unknown_tool"], required, acceptable)
    assert res.value == 0.5  # Unique: log_pattern_search (allowed) vs unknown_tool (not allowed)

    # 7. Empty observed -> NOT_APPLICABLE
    res = evaluate_allowed_tool_precision([], required, acceptable)
    assert res.status == MetricStatus.NOT_APPLICABLE


# --- 5. FORBIDDEN TOOL INVOCATION COUNT TESTS ---

def test_forbidden_tool_invocation_count():
    forbidden = ["forbidden_tool_a", "forbidden_tool_b"]

    # 1. None
    res = evaluate_forbidden_tool_invocation_count(["log_pattern_search"], forbidden)
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 0.0

    # 2. One forbidden call
    res = evaluate_forbidden_tool_invocation_count(["forbidden_tool_a"], forbidden)
    assert res.value == 1.0

    # 3. Repeated forbidden call (all calls counted)
    res = evaluate_forbidden_tool_invocation_count(["forbidden_tool_a", "forbidden_tool_a"], forbidden)
    assert res.value == 2.0
    assert res.metadata["unique_forbidden_tools_invoked"] == 1

    # 4. Multiple forbidden tools
    res = evaluate_forbidden_tool_invocation_count(["forbidden_tool_a", "forbidden_tool_b"], forbidden)
    assert res.value == 2.0
    assert res.metadata["unique_forbidden_tools_invoked"] == 2

    # 5. Irrelevant non-forbidden tool does not count
    res = evaluate_forbidden_tool_invocation_count(["time_window_adjuster"], forbidden)
    assert res.value == 0.0

    # 6. Unknown tool does not count unless listed
    res = evaluate_forbidden_tool_invocation_count(["unknown_tool"], forbidden)
    assert res.value == 0.0

    # 7. Empty forbidden list -> NOT_APPLICABLE
    res = evaluate_forbidden_tool_invocation_count(["forbidden_tool_a"], [])
    assert res.status == MetricStatus.NOT_APPLICABLE


# --- 6. FORBIDDEN TOOL COMPLIANCE TESTS ---

def test_forbidden_tool_compliance():
    forbidden = ["forbidden_tool_a"]

    # 1. Compliant
    res = evaluate_forbidden_tool_compliance(["log_pattern_search"], forbidden)
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 1.0

    # 2. One violation
    res = evaluate_forbidden_tool_compliance(["forbidden_tool_a"], forbidden)
    assert res.value == 0.0

    # 3. Repeated violation
    res = evaluate_forbidden_tool_compliance(["forbidden_tool_a", "forbidden_tool_a"], forbidden)
    assert res.value == 0.0

    # 4. Unknown tool distinction (compliant)
    res = evaluate_forbidden_tool_compliance(["unknown_tool"], forbidden)
    assert res.value == 1.0

    # 5. Empty forbidden list -> NOT_APPLICABLE
    res = evaluate_forbidden_tool_compliance(["forbidden_tool_a"], [])
    assert res.status == MetricStatus.NOT_APPLICABLE


# --- 7. UNNECESSARY TOOL CALL COUNT TESTS ---

def test_unnecessary_tool_call_count():
    required = ["log_pattern_search"]
    acceptable = ["metric_window_analysis"]

    # 1. Zero unnecessary
    res = evaluate_unnecessary_tool_call_count(["log_pattern_search", "metric_window_analysis"], required, acceptable)
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 0.0

    # 2. One irrelevant
    res = evaluate_unnecessary_tool_call_count(["log_pattern_search", "time_window_adjuster"], required, acceptable)
    assert res.value == 1.0

    # 3. Repeated irrelevant (each counted)
    res = evaluate_unnecessary_tool_call_count(["time_window_adjuster", "time_window_adjuster"], required, acceptable)
    assert res.value == 2.0

    # 4. Forbidden call counts as unnecessary
    res = evaluate_unnecessary_tool_call_count(["log_pattern_search", "forbidden_tool"], required, acceptable)
    assert res.value == 1.0

    # 5. Unknown call
    res = evaluate_unnecessary_tool_call_count(["unknown_tool"], required, acceptable)
    assert res.value == 1.0

    # 6. Empty allowed contract with no calls
    res = evaluate_unnecessary_tool_call_count([], [], [])
    assert res.value == 0.0

    # 7. Empty allowed contract with calls (all are unnecessary)
    res = evaluate_unnecessary_tool_call_count(["log_pattern_search", "metric_window_analysis"], [], [])
    assert res.value == 2.0


# --- 8. DUPLICATE TOOL CALL COUNT TESTS ---

def test_duplicate_tool_call_count():
    # 1. No calls
    res = evaluate_duplicate_tool_call_count([])
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 0.0

    # 2. All unique
    res = evaluate_duplicate_tool_call_count(["log_pattern_search", "metric_window_analysis"])
    assert res.value == 0.0

    # 3. One duplicate
    res = evaluate_duplicate_tool_call_count(["log_pattern_search", "metric_window_analysis", "log_pattern_search"])
    assert res.value == 1.0
    assert res.metadata["duplicate_details"] == {"log_pattern_search": 1}

    # 4. Multiple duplicates
    res = evaluate_duplicate_tool_call_count(["log", "metric", "log", "log", "metric"])
    assert res.value == 3.0
    assert res.metadata["duplicate_details"] == {"log": 2, "metric": 1}

    # 5. Repeated required tool
    res = evaluate_duplicate_tool_call_count(["required_tool", "required_tool"])
    assert res.value == 1.0

    # 6. Repeated acceptable tool
    res = evaluate_duplicate_tool_call_count(["acceptable_tool", "acceptable_tool"])
    assert res.value == 1.0

    # 7. Repeated forbidden tool
    res = evaluate_duplicate_tool_call_count(["forbidden_tool", "forbidden_tool"])
    assert res.value == 1.0


# --- 9. TOOL CALL EFFICIENCY TESTS ---

def test_tool_call_efficiency():
    required = ["log_pattern_search", "metric_window_analysis"]

    # 1. Ideal call count (2 calls, 2 unique required)
    res = evaluate_tool_call_efficiency(["log_pattern_search", "metric_window_analysis"], required)
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 1.0

    # 2. Extra calls (4 calls, floor is 2)
    res = evaluate_tool_call_efficiency(["log", "metric", "extra1", "extra2"], required)
    assert res.value == 0.5

    # 3. Missing required calls (but they made 1 call total)
    res = evaluate_tool_call_efficiency(["log_pattern_search"], required)
    # Floor / actual = 2 / 1 = 2.0 -> capped at 1.0
    assert res.value == 1.0

    # 4. Zero calls (required floor is 2)
    res = evaluate_tool_call_efficiency([], required)
    assert res.value == 0.0

    # 5. No required tools -> NOT_APPLICABLE
    res = evaluate_tool_call_efficiency(["log_pattern_search"], [])
    assert res.status == MetricStatus.NOT_APPLICABLE


# --- 10. COMBINED EVALUATOR TESTS ---

def test_combined_evaluator():
    required = ["log_pattern_search"]
    acceptable = ["metric_window_analysis"]
    forbidden = ["forbidden_tool"]

    observed = ["log_pattern_search", "metric_window_analysis", "forbidden_tool"]

    results = evaluate_tool_selection(observed, required, acceptable, forbidden)

    assert len(results) == 7
    assert results["required_tool_recall"].value == 1.0
    assert results["allowed_tool_precision"].value == 2.0 / 3.0
    assert results["forbidden_tool_invocation_count"].value == 1.0
    assert results["forbidden_tool_compliance"].value == 0.0
    assert results["unnecessary_tool_call_count"].value == 1.0
    assert results["duplicate_tool_call_count"].value == 0.0
    assert results["tool_call_efficiency"].value == 1.0 / 3.0

    # Verify JSON serialization of all metadata
    for key, metric in results.items():
        assert isinstance(json.dumps(metric.metadata), str)


# --- 11. METRIC RELATIONSHIP AUDIT AND VERIFICATION TESTS ---

def test_metric_relationships():
    # Case 1: Unknown non-forbidden tool invoked
    # Expected: allowed precision decreases, unnecessary call count increases, forbidden count remains zero, compliance remains 1.0
    required = ["log_pattern_search"]
    acceptable = ["metric_window_analysis"]
    forbidden = ["forbidden_tool"]

    observed_1 = ["log_pattern_search", "unknown_tool"]
    res_precision_1 = evaluate_allowed_tool_precision(observed_1, required, acceptable)
    res_unnecessary_1 = evaluate_unnecessary_tool_call_count(observed_1, required, acceptable)
    res_forbidden_count_1 = evaluate_forbidden_tool_invocation_count(observed_1, forbidden)
    res_compliance_1 = evaluate_forbidden_tool_compliance(observed_1, forbidden)

    assert res_precision_1.value == 0.5  # decreased
    assert res_unnecessary_1.value == 1.0  # increased
    assert res_forbidden_count_1.value == 0.0  # remains zero
    assert res_compliance_1.value == 1.0  # remains 1.0

    # Case 2: Required tool missing but only acceptable tool invoked
    # Expected: recall decreases, allowed precision remains 1.0
    observed_2 = ["metric_window_analysis"]
    res_recall_2 = evaluate_required_tool_recall(observed_2, required)
    res_precision_2 = evaluate_allowed_tool_precision(observed_2, required, acceptable)

    assert res_recall_2.value == 0.0  # decreased
    assert res_precision_2.value == 1.0  # remains 1.0

    # Case 3: Repeated required tool
    # Expected: recall remains 1.0, precision remains 1.0, duplicate count increases, unnecessary remains zero
    observed_3 = ["log_pattern_search", "log_pattern_search"]
    res_recall_3 = evaluate_required_tool_recall(observed_3, required)
    res_precision_3 = evaluate_allowed_tool_precision(observed_3, required, acceptable)
    res_duplicate_3 = evaluate_duplicate_tool_call_count(observed_3)
    res_unnecessary_3 = evaluate_unnecessary_tool_call_count(observed_3, required, acceptable)

    assert res_recall_3.value == 1.0
    assert res_precision_3.value == 1.0
    assert res_duplicate_3.value == 1.0  # increased
    assert res_unnecessary_3.value == 0.0  # remains zero

    # Case 4: Forbidden tool invoked
    # Expected: precision decreases, forbidden count increases, compliance becomes 0.0, unnecessary increases if forbidden is outside allowed set
    observed_4 = ["log_pattern_search", "forbidden_tool"]
    res_precision_4 = evaluate_allowed_tool_precision(observed_4, required, acceptable)
    res_forbidden_count_4 = evaluate_forbidden_tool_invocation_count(observed_4, forbidden)
    res_compliance_4 = evaluate_forbidden_tool_compliance(observed_4, forbidden)
    res_unnecessary_4 = evaluate_unnecessary_tool_call_count(observed_4, required, acceptable)

    assert res_precision_4.value == 0.5  # decreased
    assert res_forbidden_count_4.value == 1.0  # increased
    assert res_compliance_4.value == 0.0  # becomes 0.0
    assert res_unnecessary_4.value == 1.0  # increased (since forbidden_tool is not in required/acceptable)
