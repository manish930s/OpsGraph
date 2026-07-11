import sys
import platform
import uuid
import json
import subprocess
from datetime import datetime, timezone
from typing import Any, Sequence

from evals.schemas import (
    GoldenScenario,
    EvaluationTrace,
    EvaluationMode,
    MetricStatus,
    MetricResult,
    ScenarioEvaluationResult,
    EvaluationRunManifest
)
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
    evaluate_known_secret_leakage
)
from evals.rca_metrics import (
    evaluate_affected_service_correctness,
    evaluate_fault_category_correctness,
    evaluate_root_cause_code_correctness,
    evaluate_forbidden_unsupported_cause_detection,
    evaluate_structured_rca_field_coverage,
    adapt_rca_decision_to_structured
)
from evals.tool_metrics import (
    extract_tool_names_from_trace,
    evaluate_required_tool_recall,
    evaluate_allowed_tool_precision,
    evaluate_forbidden_tool_invocation_count,
    evaluate_forbidden_tool_compliance,
    evaluate_unnecessary_tool_call_count,
    evaluate_duplicate_tool_call_count,
    evaluate_tool_call_efficiency
)


def get_git_commit() -> str | None:
    """
    Safely retrieves the current git commit HEAD hash.
    """
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()
    except Exception:
        return None


def evaluate_scenario(
    scenario: GoldenScenario | Sequence[GoldenScenario] | Iterable[GoldenScenario],
    trace: EvaluationTrace | None | dict[str, EvaluationTrace | None] = None,
    predicted_rca: Any = None,
    mode: EvaluationMode = EvaluationMode.MOCK_GRAPH,
    run_id: str | None = None
) -> ScenarioEvaluationResult | list[ScenarioEvaluationResult]:
    """
    Orchestrates the evaluation of a single scenario or an iterable of scenarios using deterministic metrics.
    Sequential execution ensures reproducibility and strict metric isolation.
    """
    from collections.abc import Iterable
    from pydantic import BaseModel
    if isinstance(scenario, Iterable) and not isinstance(scenario, (str, dict, BaseModel)):
        results = []
        actual_run_id = run_id or str(uuid.uuid4())
        for scn in scenario:
            t = None
            if isinstance(trace, dict):
                t = trace.get(scn.scenario_id)
            elif trace is not None and not isinstance(trace, dict):
                t = trace

            pr = None
            if isinstance(predicted_rca, dict) and scn.scenario_id in predicted_rca:
                pr = predicted_rca[scn.scenario_id]
            else:
                pr = predicted_rca

            results.append(evaluate_scenario(
                scenario=scn,
                trace=t,
                predicted_rca=pr,
                mode=mode,
                run_id=actual_run_id
            ))
        return results

    started_at = datetime.now(timezone.utc)
    errors = []
    warnings = []
    metrics = []

    # 1. Input validation
    if not isinstance(scenario, GoldenScenario):
        errors.append(f"Invalid scenario object: expected GoldenScenario, got {type(scenario)}")
        return ScenarioEvaluationResult(
            run_id=run_id or str(uuid.uuid4()),
            scenario_id=getattr(scenario, "scenario_id", "unknown"),
            errors=errors,
            warnings=warnings,
            metrics=[]
        )

    if trace is not None and not isinstance(trace, EvaluationTrace):
        errors.append(f"Invalid trace object: expected EvaluationTrace, got {type(trace)}")

    if errors:
        return ScenarioEvaluationResult(
            run_id=run_id or str(uuid.uuid4()),
            scenario_id=scenario.scenario_id,
            errors=errors,
            warnings=warnings,
            metrics=[]
        )

    # 2. Manifest Generation
    actual_run_id = run_id or str(uuid.uuid4())
    from app.config import settings

    graph_budgets = {
        "INVESTIGATION_MAX_ITERATIONS": settings.INVESTIGATION_MAX_ITERATIONS,
        "INVESTIGATION_MAX_TOOL_CALLS": settings.INVESTIGATION_MAX_TOOL_CALLS,
        "INVESTIGATION_MAX_CONTEXT_REBUILDS": settings.INVESTIGATION_MAX_CONTEXT_REBUILDS
    }

    manifest = EvaluationRunManifest(
        run_id=actual_run_id,
        evaluation_version="1.0",
        evaluation_mode=mode,
        started_at=started_at,
        git_commit=get_git_commit(),
        scenario_ids=[scenario.scenario_id],
        provider=settings.LLM_DEFAULT_PROVIDER,
        generation_model=settings.LLM_MODEL,
        embedding_model=settings.GEMINI_EMBEDDING_MODEL,
        embedding_dimension=settings.GEMINI_EMBEDDING_DIMENSION,
        graph_budgets=graph_budgets,
        python_version=sys.version,
        platform=platform.platform()
    )

    # 3. Diagnostic Warning Collection
    if trace is None:
        warnings.append("EvaluationTrace is missing.")
    else:
        if not trace.node_timings:
            warnings.append("Node timings are missing in trace.")
        if not trace.tool_calls:
            warnings.append("Tool calls are missing in trace.")

    if predicted_rca is None:
        warnings.append("Predicted RCA is missing.")

    if not scenario.labels:
        warnings.append("Scenario Golden labels are missing.")

    # 4. Metric Pipeline Order:
    # Citation -> Evidence -> Terminal -> Budget -> Structured RCA -> Tool
    try:
        # A. CITATION METRICS
        if predicted_rca is None:
            metrics.append(MetricResult(
                metric_name="Citation ID Validity",
                status=MetricStatus.NOT_APPLICABLE,
                reason="Predicted RCA is missing."
            ))
            metrics.append(MetricResult(
                metric_name="Invalid Citation Count",
                status=MetricStatus.NOT_APPLICABLE,
                reason="Predicted RCA is missing."
            ))
        else:
            cited_ids = []
            if isinstance(predicted_rca, dict):
                cited_ids.extend(predicted_rca.get("supporting_evidence_references", []))
                cited_ids.extend(predicted_rca.get("contradicting_evidence_references", []))
            else:
                cited_ids.extend(getattr(predicted_rca, "supporting_evidence_references", []))
                cited_ids.extend(getattr(predicted_rca, "contradicting_evidence_references", []))

            universe_ids = trace.evidence_ids if trace else []
            metrics.append(evaluate_citation_id_validity(cited_ids, universe_ids))
            metrics.append(evaluate_invalid_citation_count(cited_ids, universe_ids))

        # B. EVIDENCE METRICS
        if trace is None:
            metrics.append(MetricResult(
                metric_name="Required Evidence Recall",
                status=MetricStatus.NOT_APPLICABLE,
                reason="EvaluationTrace is missing."
            ))
            metrics.append(MetricResult(
                metric_name="Required Evidence Missing Count",
                status=MetricStatus.NOT_APPLICABLE,
                reason="EvaluationTrace is missing."
            ))
        else:
            metrics.append(evaluate_required_evidence_recall(trace.evidence_ids, scenario.required_evidence_ids))
            metrics.append(evaluate_required_evidence_missing_count(trace.evidence_ids, scenario.required_evidence_ids))

        # C. TERMINAL OUTCOME METRICS
        if trace is None:
            metrics.append(MetricResult(
                metric_name="Terminal Outcome Correctness",
                status=MetricStatus.NOT_APPLICABLE,
                reason="EvaluationTrace is missing."
            ))
        else:
            metrics.append(evaluate_terminal_outcome_correctness(
                trace.final_terminal_type or "",
                scenario.acceptable_terminal_outcomes
            ))

        # D. BUDGET METRICS
        if trace is None:
            metrics.append(MetricResult(
                metric_name="Iteration Budget Utilization",
                status=MetricStatus.NOT_APPLICABLE,
                reason="EvaluationTrace is missing."
            ))
            metrics.append(MetricResult(
                metric_name="Tool Call Budget Utilization",
                status=MetricStatus.NOT_APPLICABLE,
                reason="EvaluationTrace is missing."
            ))
            metrics.append(MetricResult(
                metric_name="Context Rebuild Budget Utilization",
                status=MetricStatus.NOT_APPLICABLE,
                reason="EvaluationTrace is missing."
            ))
            metrics.append(MetricResult(
                metric_name="Budget Compliance",
                status=MetricStatus.NOT_APPLICABLE,
                reason="EvaluationTrace is missing."
            ))
        else:
            max_iters = settings.INVESTIGATION_MAX_ITERATIONS
            max_tools = settings.INVESTIGATION_MAX_TOOL_CALLS
            max_rebuilds = settings.INVESTIGATION_MAX_CONTEXT_REBUILDS

            metrics.append(evaluate_iteration_budget_utilization(trace.iteration_count or 0, max_iters))
            metrics.append(evaluate_tool_budget_utilization(trace.tool_call_count or 0, max_tools))
            metrics.append(evaluate_context_rebuild_budget_utilization(trace.context_rebuild_count or 0, max_rebuilds))
            metrics.append(evaluate_budget_compliance(
                trace.iteration_count or 0, max_iters,
                trace.tool_call_count or 0, max_tools,
                trace.context_rebuild_count or 0, max_rebuilds
            ))

        # E. SECRET LEAKAGE METRICS
        # Scan trace details and RCA results
        artifact_text_parts = []
        if predicted_rca is not None:
            if isinstance(predicted_rca, dict):
                artifact_text_parts.append(predicted_rca.get("summary", ""))
                artifact_text_parts.append(" ".join(predicted_rca.get("hypotheses", [])))
            else:
                artifact_text_parts.append(getattr(predicted_rca, "summary", ""))
                artifact_text_parts.append(" ".join(getattr(predicted_rca, "hypotheses", [])))
        if trace is not None:
            artifact_text_parts.append(" ".join(trace.node_sequence))
            artifact_text_parts.append(trace.termination_reason or "")
            for tc in trace.tool_calls:
                artifact_text_parts.append(tc.tool_name)
                artifact_text_parts.append(tc.error_type or "")
                artifact_text_parts.append(json.dumps(tc.parameters))

        artifact_text = "\n".join(artifact_text_parts)
        metrics.append(evaluate_known_secret_leakage(artifact_text, known_secrets=None, scan_patterns=True))

        # F. STRUCTURED RCA METRICS
        if predicted_rca is None:
            metrics.append(MetricResult(
                metric_name="Affected Service Correctness",
                status=MetricStatus.NOT_APPLICABLE,
                reason="Predicted RCA is missing."
            ))
            metrics.append(MetricResult(
                metric_name="Fault Category Correctness",
                status=MetricStatus.NOT_APPLICABLE,
                reason="Predicted RCA is missing."
            ))
            metrics.append(MetricResult(
                metric_name="Root-Cause Code Correctness",
                status=MetricStatus.NOT_APPLICABLE,
                reason="Predicted RCA is missing."
            ))
            metrics.append(MetricResult(
                metric_name="Forbidden Unsupported Cause Detection",
                status=MetricStatus.NOT_APPLICABLE,
                reason="Predicted RCA is missing."
            ))
            metrics.append(MetricResult(
                metric_name="Structured RCA Field Coverage",
                status=MetricStatus.NOT_APPLICABLE,
                reason="Predicted RCA is missing."
            ))
        else:
            golden_labels_dict = scenario.labels.model_dump()
            predicted_rca_dict = adapt_rca_decision_to_structured(predicted_rca)

            metrics.append(evaluate_affected_service_correctness(
                predicted_rca_dict.get("affected_service"),
                golden_labels_dict.get("affected_service")
            ))
            metrics.append(evaluate_fault_category_correctness(
                predicted_rca_dict.get("fault_category"),
                golden_labels_dict.get("fault_category")
            ))
            metrics.append(evaluate_root_cause_code_correctness(
                predicted_rca_dict.get("root_cause_code"),
                golden_labels_dict.get("root_cause_code"),
                acceptable_equivalents=golden_labels_dict.get("acceptable_equivalent_root_cause_codes")
            ))
            metrics.append(evaluate_forbidden_unsupported_cause_detection(
                predicted_rca_dict.get("root_cause_code"),
                forbidden_codes=golden_labels_dict.get("forbidden_unsupported_cause_codes")
            ))
            metrics.append(evaluate_structured_rca_field_coverage(
                predicted_rca_dict,
                golden_labels_dict
            ))

        # G. TOOL METRICS
        if trace is None:
            metrics.append(MetricResult(
                metric_name="Required Tool Recall",
                status=MetricStatus.NOT_APPLICABLE,
                reason="EvaluationTrace is missing."
            ))
            metrics.append(MetricResult(
                metric_name="Allowed Tool Precision",
                status=MetricStatus.NOT_APPLICABLE,
                reason="EvaluationTrace is missing."
            ))
            metrics.append(MetricResult(
                metric_name="Forbidden Tool Invocation Count",
                status=MetricStatus.NOT_APPLICABLE,
                reason="EvaluationTrace is missing."
            ))
            metrics.append(MetricResult(
                metric_name="Forbidden Tool Compliance",
                status=MetricStatus.NOT_APPLICABLE,
                reason="EvaluationTrace is missing."
            ))
            metrics.append(MetricResult(
                metric_name="Unnecessary Tool Call Count",
                status=MetricStatus.NOT_APPLICABLE,
                reason="EvaluationTrace is missing."
            ))
            metrics.append(MetricResult(
                metric_name="Duplicate Tool Call Count",
                status=MetricStatus.NOT_APPLICABLE,
                reason="EvaluationTrace is missing."
            ))
            metrics.append(MetricResult(
                metric_name="Tool Call Efficiency",
                status=MetricStatus.NOT_APPLICABLE,
                reason="EvaluationTrace is missing."
            ))
        else:
            observed_tool_names = extract_tool_names_from_trace(trace.tool_calls)
            metrics.append(evaluate_required_tool_recall(observed_tool_names, scenario.required_tools))
            metrics.append(evaluate_allowed_tool_precision(observed_tool_names, scenario.required_tools, scenario.acceptable_tools))
            metrics.append(evaluate_forbidden_tool_invocation_count(observed_tool_names, scenario.forbidden_tools))
            metrics.append(evaluate_forbidden_tool_compliance(observed_tool_names, scenario.forbidden_tools))
            metrics.append(evaluate_unnecessary_tool_call_count(observed_tool_names, scenario.required_tools, scenario.acceptable_tools))
            metrics.append(evaluate_duplicate_tool_call_count(observed_tool_names))
            metrics.append(evaluate_tool_call_efficiency(observed_tool_names, scenario.required_tools))

    except Exception as e:
        errors.append(f"Unexpected error during metric evaluation: {str(e)}")

    manifest.finished_at = datetime.now(timezone.utc)

    return ScenarioEvaluationResult(
        run_id=actual_run_id,
        scenario_id=scenario.scenario_id,
        terminal_outcome=trace.final_terminal_type if trace else None,
        metrics=metrics,
        warnings=warnings,
        errors=errors,
        trace=trace
    )


def evaluate_mock_graph(
    scenario: GoldenScenario | Sequence[GoldenScenario] | Iterable[GoldenScenario],
    trace: EvaluationTrace | None | dict[str, EvaluationTrace | None] = None,
    predicted_rca: Any = None,
    run_id: str | None = None
) -> ScenarioEvaluationResult | list[ScenarioEvaluationResult]:
    """
    Evaluates scenario execution in mock graph mode.
    """
    return evaluate_scenario(
        scenario=scenario,
        trace=trace,
        predicted_rca=predicted_rca,
        mode=EvaluationMode.MOCK_GRAPH,
        run_id=run_id
    )


def evaluate_offline_component(
    scenario: GoldenScenario | Sequence[GoldenScenario] | Iterable[GoldenScenario],
    trace: EvaluationTrace | None | dict[str, EvaluationTrace | None] = None,
    predicted_rca: Any = None,
    run_id: str | None = None
) -> ScenarioEvaluationResult | list[ScenarioEvaluationResult]:
    """
    Evaluates scenario execution in offline component mode.
    """
    return evaluate_scenario(
        scenario=scenario,
        trace=trace,
        predicted_rca=predicted_rca,
        mode=EvaluationMode.OFFLINE_COMPONENT,
        run_id=run_id
    )
