from typing import Any, Sequence
from evals.schemas import MetricResult, MetricStatus

# --- NORMALIZATION POLICY ---

def normalize_identifier(val: str | None) -> str | None:
    """
    Applies the deterministic normalization policy for structured RCA identifiers:
    1. Trims leading and trailing whitespace.
    2. Converts to lowercase (case-insensitive identifiers).
    3. Preserves internal punctuation (e.g. underscores, dashes).
    Returns None for empty/missing values.
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    return s.lower()


# --- RCA INPUT ADAPTER ---

def adapt_rca_decision_to_structured(rca_response: Any) -> dict[str, Any]:
    """
    Adapter that converts a runtime RCADecisionResponse (or dict) to a structured dictionary
    of predicted fields for evaluation.
    Extracts fields dynamically, returning None if they are missing.
    Does not infer structured fields from natural-language summaries.
    """
    if rca_response is None:
        return {
            "affected_service": None,
            "fault_category": None,
            "root_cause_code": None
        }

    if isinstance(rca_response, dict):
        return {
            "affected_service": rca_response.get("affected_service"),
            "fault_category": rca_response.get("fault_category"),
            "root_cause_code": rca_response.get("root_cause_code")
        }

    # Pydantic or custom object
    return {
        "affected_service": getattr(rca_response, "affected_service", None),
        "fault_category": getattr(rca_response, "fault_category", None),
        "root_cause_code": getattr(rca_response, "root_cause_code", None)
    }


# --- INDIVIDUAL RCA METRICS ---

def evaluate_affected_service_correctness(
    predicted: str | None,
    expected: str | None
) -> MetricResult:
    """
    Compare predicted affected service against golden affected service.
    """
    norm_expected = normalize_identifier(expected)
    if norm_expected is None:
        return MetricResult(
            metric_name="Affected Service Correctness",
            status=MetricStatus.NOT_APPLICABLE,
            reason="No affected service expected in golden label."
        )

    norm_predicted = normalize_identifier(predicted)
    if norm_predicted is None:
        return MetricResult(
            metric_name="Affected Service Correctness",
            status=MetricStatus.SUCCESS,
            value=0.0,
            metadata={"prediction_missing": True}
        )

    value = 1.0 if norm_predicted == norm_expected else 0.0

    return MetricResult(
        metric_name="Affected Service Correctness",
        status=MetricStatus.SUCCESS,
        value=value,
        metadata={"prediction_missing": False}
    )


def evaluate_fault_category_correctness(
    predicted: str | None,
    expected: str | None
) -> MetricResult:
    """
    Compare predicted fault category against golden category.
    """
    norm_expected = normalize_identifier(expected)
    if norm_expected is None:
        return MetricResult(
            metric_name="Fault Category Correctness",
            status=MetricStatus.NOT_APPLICABLE,
            reason="No fault category expected in golden label."
        )

    norm_predicted = normalize_identifier(predicted)
    if norm_predicted is None:
        return MetricResult(
            metric_name="Fault Category Correctness",
            status=MetricStatus.SUCCESS,
            value=0.0,
            metadata={"prediction_missing": True}
        )

    value = 1.0 if norm_predicted == norm_expected else 0.0

    return MetricResult(
        metric_name="Fault Category Correctness",
        status=MetricStatus.SUCCESS,
        value=value,
        metadata={"prediction_missing": False}
    )


def evaluate_root_cause_code_correctness(
    predicted: str | None,
    expected: str | None,
    acceptable_equivalents: Sequence[str] | None = None
) -> MetricResult:
    """
    Compare predicted root-cause code against golden canonical code and equivalents.
    """
    accepted_set = set()
    norm_expected = normalize_identifier(expected)
    if norm_expected is not None:
        accepted_set.add(norm_expected)

    if acceptable_equivalents:
        for eq in acceptable_equivalents:
            norm_eq = normalize_identifier(eq)
            if norm_eq is not None:
                accepted_set.add(norm_eq)

    if not accepted_set:
        return MetricResult(
            metric_name="Root-Cause Code Correctness",
            status=MetricStatus.NOT_APPLICABLE,
            reason="No root-cause code expectations defined in golden label."
        )

    norm_predicted = normalize_identifier(predicted)
    if norm_predicted is None:
        return MetricResult(
            metric_name="Root-Cause Code Correctness",
            status=MetricStatus.SUCCESS,
            value=0.0,
            metadata={"prediction_missing": True, "match_type": "none"}
        )

    if norm_expected is not None and norm_predicted == norm_expected:
        return MetricResult(
            metric_name="Root-Cause Code Correctness",
            status=MetricStatus.SUCCESS,
            value=1.0,
            metadata={"prediction_missing": False, "match_type": "canonical"}
        )

    if norm_predicted in accepted_set:
        return MetricResult(
            metric_name="Root-Cause Code Correctness",
            status=MetricStatus.SUCCESS,
            value=1.0,
            metadata={"prediction_missing": False, "match_type": "acceptable_equivalent"}
        )

    return MetricResult(
        metric_name="Root-Cause Code Correctness",
        status=MetricStatus.SUCCESS,
        value=0.0,
        metadata={"prediction_missing": False, "match_type": "none"}
    )


def evaluate_forbidden_unsupported_cause_detection(
    predicted: str | None,
    forbidden_codes: Sequence[str] | None
) -> MetricResult:
    """
    Detect whether predicted root-cause code is in the forbidden unsupported set.
    """
    if not forbidden_codes:
        return MetricResult(
            metric_name="Forbidden Unsupported Cause Detection",
            status=MetricStatus.NOT_APPLICABLE,
            reason="No forbidden unsupported causes expected in golden label."
        )

    norm_predicted = normalize_identifier(predicted)
    if norm_predicted is None:
        return MetricResult(
            metric_name="Forbidden Unsupported Cause Detection",
            status=MetricStatus.SUCCESS,
            value=1.0,
            metadata={"forbidden_match_detected": False, "prediction_missing": True}
        )

    norm_forbidden = {normalize_identifier(fc) for fc in forbidden_codes}
    if norm_predicted in norm_forbidden:
        return MetricResult(
            metric_name="Forbidden Unsupported Cause Detection",
            status=MetricStatus.SUCCESS,
            value=0.0,
            metadata={"forbidden_match_detected": True, "prediction_missing": False}
        )

    return MetricResult(
        metric_name="Forbidden Unsupported Cause Detection",
        status=MetricStatus.SUCCESS,
        value=1.0,
        metadata={"forbidden_match_detected": False, "prediction_missing": False}
    )


def evaluate_structured_rca_field_coverage(
    predicted: dict[str, Any],
    golden: dict[str, Any]
) -> MetricResult:
    """
    Measure structured RCA prediction completeness against expected golden labels.
    Fields checked: affected_service, fault_category, root_cause_code
    """
    fields = ["affected_service", "fault_category", "root_cause_code"]
    expected_fields = [f for f in fields if golden.get(f)]

    if not expected_fields:
        return MetricResult(
            metric_name="Structured RCA Field Coverage",
            status=MetricStatus.NOT_APPLICABLE,
            reason="No structured RCA fields expected in golden label."
        )

    present_count = 0
    for f in expected_fields:
        val = predicted.get(f)
        if val is not None and str(val).strip() != "":
            present_count += 1

    value = float(present_count) / len(expected_fields)

    return MetricResult(
        metric_name="Structured RCA Field Coverage",
        status=MetricStatus.SUCCESS,
        value=value,
        metadata={
            "expected_field_count": len(expected_fields),
            "present_field_count": present_count
        }
    )


# --- COMBINED EVALUATION HELPER ---

def evaluate_structured_rca(
    predicted_rca: Any,
    golden_labels: dict[str, Any],
    acceptable_equivalents: Sequence[str] | None = None,
    forbidden_codes: Sequence[str] | None = None
) -> dict[str, MetricResult]:
    """
    Convenience function that returns individual structured RCA metrics.
    Does not combine or average results to maintain metrics isolation.
    """
    pred = adapt_rca_decision_to_structured(predicted_rca)

    return {
        "affected_service_correctness": evaluate_affected_service_correctness(
            pred.get("affected_service"),
            golden_labels.get("affected_service")
        ),
        "fault_category_correctness": evaluate_fault_category_correctness(
            pred.get("fault_category"),
            golden_labels.get("fault_category")
        ),
        "root_cause_code_correctness": evaluate_root_cause_code_correctness(
            pred.get("root_cause_code"),
            golden_labels.get("root_cause_code"),
            acceptable_equivalents=acceptable_equivalents
        ),
        "forbidden_unsupported_cause_detection": evaluate_forbidden_unsupported_cause_detection(
            pred.get("root_cause_code"),
            forbidden_codes=forbidden_codes
        ),
        "structured_rca_field_coverage": evaluate_structured_rca_field_coverage(
            pred,
            golden_labels
        )
    }
