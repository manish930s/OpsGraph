import json
import pytest
from evals.schemas import MetricStatus
from evals.rca_metrics import (
    evaluate_affected_service_correctness,
    evaluate_fault_category_correctness,
    evaluate_root_cause_code_correctness,
    evaluate_forbidden_unsupported_cause_detection,
    evaluate_structured_rca_field_coverage,
    evaluate_structured_rca,
    adapt_rca_decision_to_structured
)

# Mock class mimicking a pydantic model response
class MockRCADecision:
    def __init__(self, affected_service=None, fault_category=None, root_cause_code=None, summary=""):
        self.affected_service = affected_service
        self.fault_category = fault_category
        self.root_cause_code = root_cause_code
        self.summary = summary


# --- 1. RCA INPUT ADAPTER TESTS ---

def test_rca_input_adapter():
    # 1. Dict input
    pred_dict = {"affected_service": "checkout", "fault_category": "db", "root_cause_code": "code1"}
    res = adapt_rca_decision_to_structured(pred_dict)
    assert res == pred_dict

    # 2. Object input
    pred_obj = MockRCADecision(affected_service="checkout", fault_category="db", root_cause_code="code1")
    res = adapt_rca_decision_to_structured(pred_obj)
    assert res == {
        "affected_service": "checkout",
        "fault_category": "db",
        "root_cause_code": "code1"
    }

    # 3. None / Missing fields
    res = adapt_rca_decision_to_structured(None)
    assert res == {
        "affected_service": None,
        "fault_category": None,
        "root_cause_code": None
    }

    # 4. Standard runtime RCADecisionResponse which doesn't have these fields
    class StandardRCA:
        summary = "Natural language summary of DB pool exhaustion."
    res = adapt_rca_decision_to_structured(StandardRCA())
    assert res == {
        "affected_service": None,
        "fault_category": None,
        "root_cause_code": None
    }


# --- 2. AFFECTED SERVICE CORRECTNESS TESTS ---

def test_affected_service_correctness():
    # Exact match
    res = evaluate_affected_service_correctness("checkout-service", "checkout-service")
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 1.0

    # Normalized match (whitespace & case)
    res = evaluate_affected_service_correctness("  Checkout-Service  ", "checkout-service")
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 1.0

    # Mismatch
    res = evaluate_affected_service_correctness("payment-service", "checkout-service")
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 0.0

    # Missing prediction
    res = evaluate_affected_service_correctness(None, "checkout-service")
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 0.0
    assert res.metadata["prediction_missing"] is True

    # Missing expected label (N/A)
    res = evaluate_affected_service_correctness("checkout-service", None)
    assert res.status == MetricStatus.NOT_APPLICABLE
    assert "No affected service expected" in res.reason

    # Partial string mismatch
    res = evaluate_affected_service_correctness("checkout", "checkout-service")
    assert res.value == 0.0


# --- 3. FAULT CATEGORY CORRECTNESS TESTS ---

def test_fault_category_correctness():
    # Exact match
    res = evaluate_fault_category_correctness("database_connection_pool", "database_connection_pool")
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 1.0

    # Normalized match
    res = evaluate_fault_category_correctness(" DATABASE_CONNECTION_POOL ", "database_connection_pool")
    assert res.value == 1.0

    # Mismatch
    res = evaluate_fault_category_correctness("memory_leak", "database_connection_pool")
    assert res.value == 0.0

    # Missing prediction
    res = evaluate_fault_category_correctness(None, "database_connection_pool")
    assert res.value == 0.0
    assert res.metadata["prediction_missing"] is True

    # Missing expected label (N/A)
    res = evaluate_fault_category_correctness("db", None)
    assert res.status == MetricStatus.NOT_APPLICABLE


# --- 4. ROOT-CAUSE CODE CORRECTNESS TESTS ---

def test_root_cause_code_correctness():
    # Canonical match
    res = evaluate_root_cause_code_correctness("DB_POOL_REGRESSION", "DB_POOL_REGRESSION")
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 1.0
    assert res.metadata["match_type"] == "canonical"

    # Acceptable equivalent match
    res = evaluate_root_cause_code_correctness(
        "DB_POOL_ERROR",
        "DB_POOL_REGRESSION",
        acceptable_equivalents=["db_pool_error", "connection_failure"]
    )
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 1.0
    assert res.metadata["match_type"] == "acceptable_equivalent"

    # Mismatch
    res = evaluate_root_cause_code_correctness(
        "REDIS_OUTAGE",
        "DB_POOL_REGRESSION",
        acceptable_equivalents=["DB_POOL_ERROR"]
    )
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 0.0
    assert res.metadata["match_type"] == "none"

    # Missing prediction
    res = evaluate_root_cause_code_correctness(None, "DB_POOL_REGRESSION")
    assert res.value == 0.0
    assert res.metadata["prediction_missing"] is True

    # Missing expected label
    res = evaluate_root_cause_code_correctness("CODE_A", None)
    assert res.status == MetricStatus.NOT_APPLICABLE


# --- 5. FORBIDDEN UNSUPPORTED CAUSE DETECTION TESTS ---

def test_forbidden_unsupported_cause_detection():
    # Predicted forbidden code
    res = evaluate_forbidden_unsupported_cause_detection(
        "REDIS_OUTAGE",
        forbidden_codes=["redis_outage", "dns_failure"]
    )
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 0.0
    assert res.metadata["forbidden_match_detected"] is True

    # Predicted allowed canonical code
    res = evaluate_forbidden_unsupported_cause_detection(
        "DB_POOL_REGRESSION",
        forbidden_codes=["redis_outage"]
    )
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 1.0
    assert res.metadata["forbidden_match_detected"] is False

    # Empty forbidden list
    res = evaluate_forbidden_unsupported_cause_detection("REDIS_OUTAGE", [])
    assert res.status == MetricStatus.NOT_APPLICABLE

    # Missing prediction
    res = evaluate_forbidden_unsupported_cause_detection(None, ["redis_outage"])
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 1.0
    assert res.metadata["forbidden_match_detected"] is False
    assert res.metadata["prediction_missing"] is True


# --- 6. STRUCTURED RCA FIELD COVERAGE TESTS ---

def test_structured_rca_field_coverage():
    golden = {"affected_service": "checkout", "fault_category": "db", "root_cause_code": "code1"}

    # Full coverage
    pred_full = {"affected_service": "checkout", "fault_category": "db", "root_cause_code": "code1"}
    res = evaluate_structured_rca_field_coverage(pred_full, golden)
    assert res.status == MetricStatus.SUCCESS
    assert res.value == 1.0
    assert res.metadata["expected_field_count"] == 3
    assert res.metadata["present_field_count"] == 3

    # Partial coverage
    pred_partial = {"affected_service": "checkout", "fault_category": "", "root_cause_code": None}
    res = evaluate_structured_rca_field_coverage(pred_partial, golden)
    assert res.value == 1.0 / 3.0
    assert res.metadata["present_field_count"] == 1

    # Zero coverage
    pred_zero = {"affected_service": None, "fault_category": "", "root_cause_code": "  "}
    res = evaluate_structured_rca_field_coverage(pred_zero, golden)
    assert res.value == 0.0

    # No golden fields expected
    res = evaluate_structured_rca_field_coverage(pred_full, {})
    assert res.status == MetricStatus.NOT_APPLICABLE


# --- 7. COMBINED EVALUATION HELPER TESTS ---

def test_combined_evaluation_helper():
    golden = {
        "affected_service": "checkout-service",
        "fault_category": "database_connection_pool",
        "root_cause_code": "DB_POOL_MAX_CONNECTIONS_REGRESSION"
    }
    pred = MockRCADecision(
        affected_service="checkout-service",
        fault_category="database_connection_pool",
        root_cause_code="DB_POOL_ERROR"  # equivalent
    )
    
    results = evaluate_structured_rca(
        predicted_rca=pred,
        golden_labels=golden,
        acceptable_equivalents=["DB_POOL_ERROR"],
        forbidden_codes=["REDIS_OUTAGE"]
    )

    assert len(results) == 5
    assert results["affected_service_correctness"].value == 1.0
    assert results["fault_category_correctness"].value == 1.0
    assert results["root_cause_code_correctness"].value == 1.0
    assert results["root_cause_code_correctness"].metadata["match_type"] == "acceptable_equivalent"
    assert results["forbidden_unsupported_cause_detection"].value == 1.0
    assert results["structured_rca_field_coverage"].value == 1.0

    # Verify JSON serialization of all metadata
    for key, metric in results.items():
        assert isinstance(json.dumps(metric.metadata), str)
