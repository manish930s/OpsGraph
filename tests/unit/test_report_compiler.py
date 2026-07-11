import json
import pytest
from pathlib import Path
from datetime import datetime, timezone
from evals.schemas import (
    EvaluationRunManifest,
    EvaluationMode,
    ScenarioEvaluationResult,
    MetricResult,
    MetricStatus,
    DatasetSummary
)
from evals.report_compiler import compile_dataset_report
from evals.export import export_dataset_result_json


# --- Helpers ---

def make_mock_manifest() -> EvaluationRunManifest:
    return EvaluationRunManifest(
        run_id="run-123",
        evaluation_version="1.0",
        evaluation_mode=EvaluationMode.MOCK_GRAPH,
        started_at=datetime.now(timezone.utc),
        scenario_ids=["SCN-001", "SCN-002"]
    )


def make_mock_metric(name: str, status: MetricStatus, value: float | None = None) -> MetricResult:
    return MetricResult(
        metric_name=name,
        status=status,
        value=value,
        reason="N/A reason" if status == MetricStatus.NOT_APPLICABLE else None,
        error_type="Failed reason" if status == MetricStatus.FAILED else None
    )


# --- Tests ---

def test_empty_dataset():
    manifest = make_mock_manifest()
    result = compile_dataset_report(manifest, [])
    
    assert result.overall_completion_status == "completed"
    assert result.evaluation_statistics.total_scenarios == 0
    assert result.evaluation_statistics.evaluated_scenarios == 0
    assert len(result.metric_summaries) == 0


def test_single_scenario():
    manifest = make_mock_manifest()
    
    metric1 = make_mock_metric("Accuracy", MetricStatus.SUCCESS, 0.8)
    metric2 = make_mock_metric("Latency", MetricStatus.SUCCESS, 150.0)
    
    scenario_result = ScenarioEvaluationResult(
        run_id="run-123",
        scenario_id="SCN-001",
        metrics=[metric1, metric2],
        warnings=["EvaluationTrace is missing."],
        errors=["Validation failed."]
    )

    result = compile_dataset_report(manifest, [scenario_result])
    
    assert result.evaluation_statistics.total_scenarios == 1
    assert result.evaluation_statistics.successful_evaluations == 0
    assert result.evaluation_statistics.partial_evaluations == 1
    assert result.overall_completion_status == "partial"
    
    # Check warning category mapping
    assert "missing_trace" in result.warning_summary
    assert result.warning_summary["missing_trace"].count == 1
    assert result.warning_summary["missing_trace"].affected_scenarios == ["SCN-001"]

    # Check error category mapping
    assert "validation_errors" in result.error_summary
    assert result.error_summary["validation_errors"].count == 1


def test_multiple_scenarios_and_aggregations():
    manifest = make_mock_manifest()
    
    # SCN-001
    scn1 = ScenarioEvaluationResult(
        run_id="run-123",
        scenario_id="SCN-001",
        metrics=[
            make_mock_metric("Accuracy", MetricStatus.SUCCESS, 1.0),
            make_mock_metric("Latency", MetricStatus.SUCCESS, 100.0)
        ]
    )

    # SCN-002
    scn2 = ScenarioEvaluationResult(
        run_id="run-123",
        scenario_id="SCN-002",
        metrics=[
            make_mock_metric("Accuracy", MetricStatus.SUCCESS, 0.5),
            make_mock_metric("Latency", MetricStatus.SUCCESS, 200.0)
        ]
    )

    # SCN-003
    scn3 = ScenarioEvaluationResult(
        run_id="run-123",
        scenario_id="SCN-003",
        metrics=[
            make_mock_metric("Accuracy", MetricStatus.NOT_APPLICABLE),
            make_mock_metric("Latency", MetricStatus.SUCCESS, 150.0)
        ]
    )

    result = compile_dataset_report(manifest, [scn3, scn1, scn2]) # unordered input
    
    # Check deterministic sorting order of results
    assert result.scenario_results[0].scenario_id == "SCN-001"
    assert result.scenario_results[1].scenario_id == "SCN-002"
    assert result.scenario_results[2].scenario_id == "SCN-003"

    # Verify metric summaries
    assert "Accuracy" in result.metric_summaries
    accuracy = result.metric_summaries["Accuracy"]
    assert accuracy.total_count == 3
    assert accuracy.success_count == 2
    assert accuracy.na_count == 1
    assert accuracy.failed_count == 0
    assert accuracy.min_value == 0.5
    assert accuracy.max_value == 1.0
    assert accuracy.mean_value == 0.75
    assert accuracy.median_value == 0.75

    assert "Latency" in result.metric_summaries
    latency = result.metric_summaries["Latency"]
    assert latency.mean_value == 150.0  # (100 + 200 + 150) / 3
    assert latency.median_value == 150.0


def test_warning_and_error_grouping():
    manifest = make_mock_manifest()
    
    scn1 = ScenarioEvaluationResult(
        run_id="run-123",
        scenario_id="SCN-001",
        warnings=["missing predicted rca"],
        errors=["simulated crash exception"]
    )
    scn2 = ScenarioEvaluationResult(
        run_id="run-123",
        scenario_id="SCN-002",
        warnings=["predicted rca is missing"],
        errors=["simulated network exception"]
    )

    result = compile_dataset_report(manifest, [scn1, scn2])
    
    # Warnings are mapped to missing_rca category
    assert "missing_rca" in result.warning_summary
    assert result.warning_summary["missing_rca"].count == 2
    assert result.warning_summary["missing_rca"].affected_scenarios == ["SCN-001", "SCN-002"]

    # Errors are mapped to unexpected_exceptions
    assert "unexpected_exceptions" in result.error_summary
    assert result.error_summary["unexpected_exceptions"].count == 2
    assert result.error_summary["unexpected_exceptions"].affected_scenarios == ["SCN-001", "SCN-002"]


def test_json_export_and_stable_serialization(tmp_path):
    manifest = make_mock_manifest()
    scn = ScenarioEvaluationResult(
        run_id="run-123",
        scenario_id="SCN-001",
        metrics=[make_mock_metric("Accuracy", MetricStatus.SUCCESS, 1.0)]
    )
    
    dataset_summary = DatasetSummary(
        total_scenarios=1,
        split_counts={"dev": 1},
        ambiguity_counts={"unambiguous": 1},
        scenario_ids=["SCN-001"]
    )

    result = compile_dataset_report(manifest, [scn], dataset_summary)
    
    output_file = tmp_path / "report.json"
    export_dataset_result_json(result, output_file)
    
    assert output_file.exists()
    
    with open(output_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert data["overall_completion_status"] == "completed"
    assert data["run_manifest"]["run_id"] == "run-123"
    assert data["evaluation_statistics"]["total_scenarios"] == 1
