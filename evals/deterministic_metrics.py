import math
import re
from typing import Any, Sequence
from evals.schemas import MetricResult, MetricStatus

# --- CITATION ID VALIDITY ---

def evaluate_citation_id_validity(
    cited_ids: Sequence[str],
    authoritative_universe_ids: Sequence[str]
) -> MetricResult:
    """
    Measure whether cited evidence IDs exist in the authoritative evidence universe.
    Formula: valid cited IDs / unique cited IDs
    """
    unique_cited = sorted(list(set(cited_ids)))
    if not unique_cited:
        return MetricResult(
            metric_name="Citation ID Validity",
            status=MetricStatus.NOT_APPLICABLE,
            reason="No citation IDs were available for validity evaluation."
        )

    valid_universe = set(authoritative_universe_ids)
    valid_count = sum(1 for cid in unique_cited if cid in valid_universe)
    total_unique = len(unique_cited)
    invalid_count = total_unique - valid_count

    value = float(valid_count) / total_unique

    return MetricResult(
        metric_name="Citation ID Validity",
        status=MetricStatus.SUCCESS,
        value=value,
        metadata={
            "valid_count": valid_count,
            "invalid_count": invalid_count,
            "total_unique_citations": total_unique
        }
    )


def evaluate_invalid_citation_count(
    cited_ids: Sequence[str],
    authoritative_universe_ids: Sequence[str]
) -> MetricResult:
    """
    Count the number of unique cited evidence IDs not found in the authoritative evidence universe.
    """
    unique_cited = set(cited_ids)
    valid_universe = set(authoritative_universe_ids)
    
    invalid_ids = unique_cited.difference(valid_universe)
    invalid_count = len(invalid_ids)

    return MetricResult(
        metric_name="Invalid Citation Count",
        status=MetricStatus.SUCCESS,
        value=float(invalid_count),
        metadata={
            "invalid_count": invalid_count,
            "total_unique_citations": len(unique_cited)
        }
    )


# --- REQUIRED EVIDENCE RECALL ---

def evaluate_required_evidence_recall(
    observed_ids: Sequence[str],
    required_ids: Sequence[str]
) -> MetricResult:
    """
    Measure coverage of scenario-required evidence.
    Formula: unique required evidence IDs found / unique required evidence IDs
    """
    unique_required = sorted(list(set(required_ids)))
    if not unique_required:
        return MetricResult(
            metric_name="Required Evidence Recall",
            status=MetricStatus.NOT_APPLICABLE,
            reason="Scenario has no required evidence labels for this metric."
        )

    observed_set = set(observed_ids)
    found_count = sum(1 for rid in unique_required if rid in observed_set)
    total_required = len(unique_required)
    missing_count = total_required - found_count

    value = float(found_count) / total_required

    return MetricResult(
        metric_name="Required Evidence Recall",
        status=MetricStatus.SUCCESS,
        value=value,
        metadata={
            "found_required_count": found_count,
            "missing_required_count": missing_count,
            "total_required_count": total_required
        }
    )


def evaluate_required_evidence_missing_count(
    observed_ids: Sequence[str],
    required_ids: Sequence[str]
) -> MetricResult:
    """
    Count the number of unique required evidence IDs absent from observed evidence.
    """
    unique_required = set(required_ids)
    if not unique_required:
        return MetricResult(
            metric_name="Required Evidence Missing Count",
            status=MetricStatus.NOT_APPLICABLE,
            reason="Scenario has no required evidence labels for this metric."
        )

    observed_set = set(observed_ids)
    missing_ids = unique_required.difference(observed_set)
    missing_count = len(missing_ids)

    return MetricResult(
        metric_name="Required Evidence Missing Count",
        status=MetricStatus.SUCCESS,
        value=float(missing_count),
        metadata={
            "missing_required_count": missing_count,
            "total_required_count": len(unique_required)
        }
    )


# --- TERMINAL OUTCOME CORRECTNESS ---

def evaluate_terminal_outcome_correctness(
    actual_outcome: str,
    acceptable_outcomes: Sequence[str]
) -> MetricResult:
    """
    Determine whether the actual graph terminal outcome is allowed by the scenario contract.
    """
    if not actual_outcome:
        return MetricResult(
            metric_name="Terminal Outcome Correctness",
            status=MetricStatus.SUCCESS,
            value=0.0,
            reason="Actual outcome is empty."
        )

    value = 1.0 if actual_outcome in acceptable_outcomes else 0.0

    return MetricResult(
        metric_name="Terminal Outcome Correctness",
        status=MetricStatus.SUCCESS,
        value=value,
        metadata={
            "actual_outcome": actual_outcome,
            "acceptable_outcomes": list(acceptable_outcomes)
        }
    )


# --- BUDGET UTILIZATION METRICS ---

def evaluate_iteration_budget_utilization(
    iteration_count: int,
    max_iterations: int
) -> MetricResult:
    """
    Proportion of configured iteration budget consumed.
    """
    if iteration_count < 0:
        raise ValueError("iteration_count cannot be negative")
    if max_iterations <= 0:
        raise ValueError("max_iterations must be greater than zero")

    value = float(iteration_count) / max_iterations

    return MetricResult(
        metric_name="Iteration Budget Utilization",
        status=MetricStatus.SUCCESS,
        value=value,
        metadata={
            "iteration_count": iteration_count,
            "max_iterations": max_iterations
        }
    )


def evaluate_tool_budget_utilization(
    tool_call_count: int,
    max_tool_calls: int
) -> MetricResult:
    """
    Proportion of configured tool-call budget consumed.
    """
    if tool_call_count < 0:
        raise ValueError("tool_call_count cannot be negative")
    if max_tool_calls <= 0:
        raise ValueError("max_tool_calls must be greater than zero")

    value = float(tool_call_count) / max_tool_calls

    return MetricResult(
        metric_name="Tool Call Budget Utilization",
        status=MetricStatus.SUCCESS,
        value=value,
        metadata={
            "tool_call_count": tool_call_count,
            "max_tool_calls": max_tool_calls
        }
    )


def evaluate_context_rebuild_budget_utilization(
    context_rebuild_count: int,
    max_rebuilds: int
) -> MetricResult:
    """
    Proportion of configured context rebuild budget consumed.
    """
    if context_rebuild_count < 0:
        raise ValueError("context_rebuild_count cannot be negative")
    if max_rebuilds <= 0:
        raise ValueError("max_rebuilds must be greater than zero")

    value = float(context_rebuild_count) / max_rebuilds

    return MetricResult(
        metric_name="Context Rebuild Budget Utilization",
        status=MetricStatus.SUCCESS,
        value=value,
        metadata={
            "context_rebuild_count": context_rebuild_count,
            "max_rebuilds": max_rebuilds
        }
    )


# --- BUDGET COMPLIANCE ---

def evaluate_budget_compliance(
    iteration_count: int,
    max_iterations: int,
    tool_call_count: int,
    max_tool_calls: int,
    context_rebuild_count: int,
    max_rebuilds: int
) -> MetricResult:
    """
    Determine whether all graph counters remain within configured hard limits.
    """
    if iteration_count < 0 or tool_call_count < 0 or context_rebuild_count < 0:
        raise ValueError("Counters cannot be negative")
    if max_iterations <= 0 or max_tool_calls <= 0 or max_rebuilds <= 0:
        raise ValueError("Maximum budgets must be greater than zero")

    exceeded = []
    if iteration_count > max_iterations:
        exceeded.append("iterations")
    if tool_call_count > max_tool_calls:
        exceeded.append("tool_calls")
    if context_rebuild_count > max_rebuilds:
        exceeded.append("context_rebuilds")

    value = 0.0 if exceeded else 1.0

    return MetricResult(
        metric_name="Budget Compliance",
        status=MetricStatus.SUCCESS,
        value=value,
        metadata={
            "exceeded_budgets": exceeded,
            "iteration_count": iteration_count,
            "max_iterations": max_iterations,
            "tool_call_count": tool_call_count,
            "max_tool_calls": max_tool_calls,
            "context_rebuild_count": context_rebuild_count,
            "max_rebuilds": max_rebuilds
        }
    )


# --- KNOWN SECRET LEAKAGE DETECTION ---

BEARER_TOKEN_PATTERN = re.compile(r"Bearer\s+[A-Za-z0-9\-\._~\+\/]{10,}", re.IGNORECASE)

def evaluate_known_secret_leakage(
    artifact_text: str,
    known_secrets: Sequence[str] | None = None,
    scan_patterns: bool = True
) -> MetricResult:
    """
    Detect known credential leakage into evaluation artifacts, traces, failure payloads, and reports.
    """
    secrets = list(known_secrets) if known_secrets else []
    
    # Filter out empty or trivially short secrets to prevent false positives
    valid_secrets = [s for s in secrets if s and len(s) >= 4]

    # If both known secrets and pattern scanning are disabled/empty, return NOT_APPLICABLE
    if not valid_secrets and not scan_patterns:
        return MetricResult(
            metric_name="Known Secret Leakage Detection",
            status=MetricStatus.NOT_APPLICABLE,
            reason="No known secrets provided and pattern scanning is disabled."
        )

    detections = 0
    categories = []

    # 1. Scan for explicit known secrets
    for secret in valid_secrets:
        if secret in artifact_text:
            detections += 1
            if "known_secret" not in categories:
                categories.append("known_secret")

    # 2. Pattern scanning
    if scan_patterns:
        matches = BEARER_TOKEN_PATTERN.findall(artifact_text)
        if matches:
            detections += len(matches)
            categories.append("bearer_token_pattern")

    value = 0.0 if detections > 0 else 1.0

    return MetricResult(
        metric_name="Known Secret Leakage Detection",
        status=MetricStatus.SUCCESS,
        value=value,
        metadata={
            "detection_count": detections,
            "detection_categories": categories
        }
    )
