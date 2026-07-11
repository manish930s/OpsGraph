from typing import Any, Sequence
from evals.schemas import (
    DatasetSummary,
    EvaluationRunManifest,
    ScenarioEvaluationResult,
    MetricStatus,
    MetricResult,
    MetricSummary,
    WarningCategorySummary,
    ErrorCategorySummary,
    EvaluationStatistics,
    DatasetEvaluationResult
)


def calculate_median(values: list[float]) -> float | None:
    """
    Computes the median of a list of floats.
    """
    if not values:
        return None
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return sorted_vals[mid]
    else:
        return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0


def categorize_warning(warn: str) -> str:
    """
    Maps a warning message to a standard category string.
    """
    warn_lower = warn.lower()
    if "evaluationtrace" in warn_lower or "trace is missing" in warn_lower:
        return "missing_trace"
    if "timing" in warn_lower:
        return "missing_timing"
    if "tool" in warn_lower:
        return "missing_tool_trace"
    if "predicted rca" in warn_lower:
        return "missing_rca"
    if "label" in warn_lower:
        return "missing_labels"
    if "validation" in warn_lower or "validate" in warn_lower or "invalid" in warn_lower:
        return "validation_warning"
    return "other_warning"


def categorize_error(err: str) -> str:
    """
    Maps an error message to a standard category string.
    """
    err_lower = err.lower()
    if "validation" in err_lower or "schema" in err_lower or "invalid scenario" in err_lower or "invalid trace" in err_lower:
        return "validation_errors"
    if "unexpected error" in err_lower or "unexpected exception" in err_lower or "exception" in err_lower or "crash" in err_lower:
        return "unexpected_exceptions"
    return "evaluation_failures"


def compile_dataset_report(
    run_manifest: EvaluationRunManifest,
    scenario_results: Sequence[ScenarioEvaluationResult],
    dataset_summary: DatasetSummary | None = None
) -> DatasetEvaluationResult:
    """
    Aggregates scenario evaluation results into a dataset-level DatasetEvaluationResult.
    Ensures stable, sorted, and deterministic representation.
    """
    results_list = list(scenario_results)
    
    # 1. Deterministic scenario results sorting by scenario_id ascending
    results_list.sort(key=lambda r: r.scenario_id)

    # 2. Metric Aggregation
    metrics_by_name = {}
    for res in results_list:
        for metric in res.metrics:
            metrics_by_name.setdefault(metric.metric_name, []).append(metric)

    metric_summaries = {}
    for name in sorted(metrics_by_name.keys()):
        m_list = metrics_by_name[name]
        
        total_count = len(m_list)
        success_count = sum(1 for m in m_list if m.status == MetricStatus.SUCCESS)
        na_count = sum(1 for m in m_list if m.status == MetricStatus.NOT_APPLICABLE)
        failed_count = sum(1 for m in m_list if m.status == MetricStatus.FAILED)
        
        success_vals = [m.value for m in m_list if m.status == MetricStatus.SUCCESS and m.value is not None]
        
        min_val = min(success_vals) if success_vals else None
        max_val = max(success_vals) if success_vals else None
        mean_val = sum(success_vals) / len(success_vals) if success_vals else None
        median_val = calculate_median(success_vals)

        metric_summaries[name] = MetricSummary(
            metric_name=name,
            total_count=total_count,
            success_count=success_count,
            na_count=na_count,
            failed_count=failed_count,
            min_value=min_val,
            max_value=max_val,
            mean_value=mean_val,
            median_value=median_val
        )

    # 3. Warning Aggregation
    warnings_by_cat = {}
    for res in results_list:
        for warn in res.warnings:
            cat = categorize_warning(warn)
            warnings_by_cat.setdefault(cat, []).append(res.scenario_id)

    warning_summary = {}
    for cat in sorted(warnings_by_cat.keys()):
        affected = sorted(list(set(warnings_by_cat[cat])))
        warning_summary[cat] = WarningCategorySummary(
            count=len(warnings_by_cat[cat]),
            affected_scenarios=affected
        )

    # 4. Error Aggregation
    errors_by_cat = {}
    for res in results_list:
        for err in res.errors:
            cat = categorize_error(err)
            errors_by_cat.setdefault(cat, []).append(res.scenario_id)

    # Include validation errors from dataset_summary if present
    if dataset_summary and dataset_summary.validation_errors:
        for scn_id, err_list in dataset_summary.validation_errors.items():
            for err in err_list:
                cat = categorize_error(err)
                errors_by_cat.setdefault(cat, []).append(scn_id)

    error_summary = {}
    for cat in sorted(errors_by_cat.keys()):
        affected = sorted(list(set(errors_by_cat[cat])))
        error_summary[cat] = ErrorCategorySummary(
            count=len(errors_by_cat[cat]),
            affected_scenarios=affected
        )

    # 5. Statistics Computation
    total_scenarios = dataset_summary.total_scenarios if dataset_summary else len(results_list)
    evaluated_scenarios = len(results_list)
    
    successful_evaluations = 0
    partial_evaluations = 0
    failed_evaluations = 0
    
    for res in results_list:
        has_errors = len(res.errors) > 0
        has_metrics = len(res.metrics) > 0
        
        if not has_errors:
            successful_evaluations += 1
        elif has_metrics:
            partial_evaluations += 1
        else:
            failed_evaluations += 1

    # Adjust failed count if there are loaded scenarios that didn't run at all due to validation errors
    # i.e., total_scenarios > evaluated_scenarios.
    validation_failures = max(0, total_scenarios - evaluated_scenarios)
    failed_evaluations += validation_failures

    completion_ratio = float(successful_evaluations + partial_evaluations) / total_scenarios if total_scenarios > 0 else 0.0

    stats = EvaluationStatistics(
        total_scenarios=total_scenarios,
        evaluated_scenarios=evaluated_scenarios,
        successful_evaluations=successful_evaluations,
        partial_evaluations=partial_evaluations,
        failed_evaluations=failed_evaluations,
        completion_ratio=completion_ratio
    )

    # 6. Overall Status
    if total_scenarios == 0:
        overall_status = "completed"
    elif successful_evaluations == total_scenarios:
        overall_status = "completed"
    elif failed_evaluations == total_scenarios:
        overall_status = "failed"
    else:
        overall_status = "partial"

    return DatasetEvaluationResult(
        run_manifest=run_manifest,
        dataset_summary=dataset_summary,
        scenario_results=results_list,
        metric_summaries=metric_summaries,
        warning_summary=warning_summary,
        error_summary=error_summary,
        evaluation_statistics=stats,
        overall_completion_status=overall_status
    )
