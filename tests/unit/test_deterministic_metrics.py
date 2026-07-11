import json
import pytest
from evals.schemas import MetricStatus
from evals.deterministic_metrics import (
    evaluate_citation_id_validity,
    evaluate_invalid_citation_count,
    evaluate_required_evidence_recall,
    evaluate_required_evidence_missing_count,
    evaluate_terminal_outcome_correctness,
    evaluate_iteration_budget_utilization,
    evaluate_tool_budget_utilization,
    evaluate_context_rebuild_budget_utilization,
    evaluate_budget_compliance,
    evaluate_known_secret_leakage,
)

# --- 1. CITATION ID VALIDITY TESTS ---

def test_citation_id_validity_all_valid():
    res = evaluate_citation_id_validity(
        cited_ids=["A", "B", "C"],
        authoritative_universe_ids=["A", "B", "C", "D"]
    )
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 1.0
    assert res.metadata["valid_count"] == 3
    assert res.metadata["invalid_count"] == 0
    assert res.metadata["total_unique_citations"] == 3


def test_citation_id_validity_partial():
    res = evaluate_citation_id_validity(
        cited_ids=["A", "B", "X"],
        authoritative_universe_ids=["A", "B", "C"]
    )
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 2.0 / 3.0
    assert res.metadata["valid_count"] == 2
    assert res.metadata["invalid_count"] == 1


def test_citation_id_validity_all_invalid():
    res = evaluate_citation_id_validity(
        cited_ids=["X", "Y"],
        authoritative_universe_ids=["A", "B", "C"]
    )
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 0.0
    assert res.metadata["valid_count"] == 0
    assert res.metadata["invalid_count"] == 2


def test_citation_id_validity_duplicates():
    res = evaluate_citation_id_validity(
        cited_ids=["A", "A", "B", "B"],
        authoritative_universe_ids=["A", "B", "C"]
    )
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 1.0
    assert res.metadata["total_unique_citations"] == 2


def test_citation_id_validity_empty_citations():
    res = evaluate_citation_id_validity(
        cited_ids=[],
        authoritative_universe_ids=["A", "B"]
    )
    assert res.status == MetricStatus.NOT_APPLICABLE
    assert res.value is None
    assert "No citation IDs" in res.reason


def test_citation_id_validity_empty_universe():
    res = evaluate_citation_id_validity(
        cited_ids=["A"],
        authoritative_universe_ids=[]
    )
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 0.0


# --- 2. INVALID CITATION COUNT TESTS ---

def test_invalid_citation_count():
    res = evaluate_invalid_citation_count(
        cited_ids=["A", "B", "X", "Y", "X"],
        authoritative_universe_ids=["A", "B", "C"]
    )
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 2.0  # X and Y are invalid (X counts once)
    assert res.metadata["invalid_count"] == 2


def test_invalid_citation_count_empty():
    res = evaluate_invalid_citation_count(
        cited_ids=[],
        authoritative_universe_ids=["A"]
    )
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 0.0


# --- 3. REQUIRED EVIDENCE RECALL TESTS ---

def test_evidence_recall_full():
    res = evaluate_required_evidence_recall(
        observed_ids=["A", "B", "C"],
        required_ids=["A", "B"]
    )
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 1.0
    assert res.metadata["found_required_count"] == 2
    assert res.metadata["missing_required_count"] == 0


def test_evidence_recall_partial():
    res = evaluate_required_evidence_recall(
        observed_ids=["A", "X"],
        required_ids=["A", "B", "C"]
    )
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 1.0 / 3.0
    assert res.metadata["found_required_count"] == 1
    assert res.metadata["missing_required_count"] == 2


def test_evidence_recall_zero():
    res = evaluate_required_evidence_recall(
        observed_ids=["X", "Y"],
        required_ids=["A", "B"]
    )
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 0.0


def test_evidence_recall_duplicates():
    res = evaluate_required_evidence_recall(
        observed_ids=["A", "A", "B"],
        required_ids=["A", "B", "B"]
    )
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 1.0
    assert res.metadata["total_required_count"] == 2


def test_evidence_recall_empty_required():
    res = evaluate_required_evidence_recall(
        observed_ids=["A"],
        required_ids=[]
    )
    assert res.status == MetricStatus.NOT_APPLICABLE
    assert res.value is None


# --- 4. REQUIRED EVIDENCE MISSING COUNT TESTS ---

def test_required_evidence_missing_count():
    res = evaluate_required_evidence_missing_count(
        observed_ids=["A", "B"],
        required_ids=["A", "B", "C", "D"]
    )
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 2.0  # C and D are missing
    assert res.metadata["missing_required_count"] == 2


def test_required_evidence_missing_count_empty_required():
    res = evaluate_required_evidence_missing_count(
        observed_ids=["A"],
        required_ids=[]
    )
    assert res.status == MetricStatus.NOT_APPLICABLE


# --- 5. TERMINAL OUTCOME CORRECTNESS TESTS ---

def test_terminal_outcome_correctness():
    # Expected matches
    res1 = evaluate_terminal_outcome_correctness(
        actual_outcome="finalize_rca",
        acceptable_outcomes=["finalize_rca", "human_review"]
    )
    assert res1.status == MetricStatus.SUCCESS
    assert res1.value == 1.0

    # Unacceptable outcome
    res2 = evaluate_terminal_outcome_correctness(
        actual_outcome="failure",
        acceptable_outcomes=["finalize_rca"]
    )
    assert res2.status == MetricStatus.SUCCESS
    assert res2.value == 0.0

    # Empty outcome
    res3 = evaluate_terminal_outcome_correctness(
        actual_outcome="",
        acceptable_outcomes=["finalize_rca"]
    )
    assert res3.status == MetricStatus.SUCCESS
    assert res3.value == 0.0


# --- 6. BUDGET UTILIZATION TESTS ---

def test_budget_utilization_success():
    res1 = evaluate_iteration_budget_utilization(iteration_count=2, max_iterations=3)
    assert res1.value == 2.0 / 3.0

    res2 = evaluate_tool_budget_utilization(tool_call_count=3, max_tool_calls=6)
    assert res2.value == 0.5

    res3 = evaluate_context_rebuild_budget_utilization(context_rebuild_count=1, max_rebuilds=3)
    assert res3.value == 1.0 / 3.0


def test_budget_utilization_over_budget():
    res = evaluate_tool_budget_utilization(tool_call_count=8, max_tool_calls=6)
    assert res.value == 8.0 / 6.0  # Should allow exceeding 1.0 without clamping


def test_budget_utilization_invalid_inputs():
    with pytest.raises(ValueError):
        evaluate_iteration_budget_utilization(iteration_count=-1, max_iterations=3)
    with pytest.raises(ValueError):
        evaluate_iteration_budget_utilization(iteration_count=2, max_iterations=0)
    with pytest.raises(ValueError):
        evaluate_iteration_budget_utilization(iteration_count=2, max_iterations=-3)


# --- 7. BUDGET COMPLIANCE TESTS ---

def test_budget_compliance_success():
    res = evaluate_budget_compliance(
        iteration_count=3, max_iterations=3,
        tool_call_count=5, max_tool_calls=6,
        context_rebuild_count=1, max_rebuilds=3
    )
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 1.0
    assert len(res.metadata["exceeded_budgets"]) == 0


def test_budget_compliance_violations():
    # Iteration violation
    res1 = evaluate_budget_compliance(
        iteration_count=4, max_iterations=3,
        tool_call_count=5, max_tool_calls=6,
        context_rebuild_count=1, max_rebuilds=3
    )
    assert res1.value == 0.0
    assert res1.metadata["exceeded_budgets"] == ["iterations"]

    # Multiple violations
    res2 = evaluate_budget_compliance(
        iteration_count=4, max_iterations=3,
        tool_call_count=8, max_tool_calls=6,
        context_rebuild_count=4, max_rebuilds=3
    )
    assert res2.value == 0.0
    assert sorted(res2.metadata["exceeded_budgets"]) == ["context_rebuilds", "iterations", "tool_calls"]


def test_budget_compliance_negatives():
    with pytest.raises(ValueError):
        evaluate_budget_compliance(-1, 3, 2, 6, 1, 3)
    with pytest.raises(ValueError):
        evaluate_budget_compliance(1, 0, 2, 6, 1, 3)


# --- 8. KNOWN SECRET LEAKAGE DETECTION TESTS ---

def test_secret_leakage_no_leakage():
    res = evaluate_known_secret_leakage(
        artifact_text="This is a safe trace log with no keys.",
        known_secrets=["my-groq-secret-value", "my-gemini-secret-value"],
        scan_patterns=True
    )
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 1.0
    assert res.metadata["detection_count"] == 0


def test_secret_leakage_explicit_match():
    secret = "sk-groq-12345abcdef"
    res = evaluate_known_secret_leakage(
        artifact_text=f"An error occurred: credential was {secret} in request.",
        known_secrets=[secret, "another-secret"],
        scan_patterns=False
    )
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 0.0
    assert res.metadata["detection_count"] == 1
    assert "known_secret" in res.metadata["detection_categories"]


def test_secret_leakage_bearer_pattern():
    res = evaluate_known_secret_leakage(
        artifact_text="Headers: {'Authorization': 'Bearer gsk_yA721bDx_untrusted_token_value'}",
        known_secrets=[],
        scan_patterns=True
    )
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 0.0
    assert res.metadata["detection_count"] == 1
    assert "bearer_token_pattern" in res.metadata["detection_categories"]


def test_secret_leakage_short_secrets():
    res = evaluate_known_secret_leakage(
        artifact_text="Benign text containing single letters like a or key or API.",
        known_secrets=["a", "api", "key"],  # Less than 4 chars
        scan_patterns=False
    )
    # Since secrets are too short, they are filtered out, resulting in NOT_APPLICABLE
    assert res.status == MetricStatus.NOT_APPLICABLE


def test_secret_leakage_empty_not_applicable():
    res = evaluate_known_secret_leakage(
        artifact_text="benign text",
        known_secrets=[],
        scan_patterns=False
    )
    assert res.status == MetricStatus.NOT_APPLICABLE


# --- 9. METRIC CONTRACT INTEGRATION TESTS ---

def test_metric_contract_integration():
    res = evaluate_citation_id_validity(["A"], ["A"])
    # Verify metadata JSON serialization
    serialized = json.dumps(res.metadata)
    assert "valid_count" in serialized
