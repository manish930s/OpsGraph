import json
import pytest
from pathlib import Path
from evals.schemas import (
    BenchmarkConfig,
    BenchmarkResult,
    EvaluationMode,
    DatasetSplit,
    EvaluationTrace
)
from evals.benchmark import validate_benchmark, run_benchmark


# --- Helpers ---

def create_mock_scenario_json(
    scenario_id="SCN-001",
    incident_id="INC-001",
    extra_fields=None
) -> dict:
    base = {
        "schema_version": "1.0",
        "scenario_id": scenario_id,
        "incident_id": incident_id,
        "split": "dev",
        "ambiguity": "unambiguous",
        "expected_terminal_outcome": "finalize_rca",
        "acceptable_terminal_outcomes": ["finalize_rca"],
        "labels": {
            "affected_service": "checkout-service",
            "fault_category": "database_connection_pool",
            "root_cause_code": "DB_POOL_MAX_CONNECTIONS_REGRESSION",
            "root_cause_summary": "Invalid pool settings."
        },
        "required_evidence_ids": ["EV-1"],
        "required_tools": ["log_pattern_search"],
        "acceptable_tools": ["metric_window_analysis"],
        "forbidden_tools": ["forbidden_tool_a"]
    }
    if extra_fields:
        base.update(extra_fields)
    return base


def setup_mock_dataset(tmp_path: Path):
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    
    # Scenario 1 (nested dir)
    scn1_dir = dataset_dir / "SCN-001"
    scn1_dir.mkdir()
    with open(scn1_dir / "golden.json", "w", encoding="utf-8") as f:
        json.dump(create_mock_scenario_json("SCN-001"), f)
    with open(scn1_dir / "evidence.json", "w", encoding="utf-8") as f:
        json.dump([{"evidence_id": "EV-1", "source_type": "log", "observation": "logs"}], f)

    # Scenario 2 (nested dir)
    scn2_dir = dataset_dir / "SCN-002"
    scn2_dir.mkdir()
    with open(scn2_dir / "golden.json", "w", encoding="utf-8") as f:
        json.dump(create_mock_scenario_json("SCN-002"), f)
    with open(scn2_dir / "evidence.json", "w", encoding="utf-8") as f:
        json.dump([{"evidence_id": "EV-1", "source_type": "log", "observation": "logs"}], f)

    return dataset_dir


# --- Tests ---

def test_validate_benchmark(tmp_path):
    dataset_dir = setup_mock_dataset(tmp_path)
    config = BenchmarkConfig(
        benchmark_name="test_bench",
        dataset_path=str(dataset_dir),
        evaluation_mode=EvaluationMode.MOCK_GRAPH,
        output_directory=str(tmp_path / "output")
    )
    summary = validate_benchmark(config)
    assert summary.total_scenarios == 2
    assert len(summary.validation_errors) == 0


def test_successful_benchmark(tmp_path):
    dataset_dir = setup_mock_dataset(tmp_path)
    output_dir = tmp_path / "output"
    
    config = BenchmarkConfig(
        benchmark_name="test_bench",
        dataset_path=str(dataset_dir),
        evaluation_mode=EvaluationMode.MOCK_GRAPH,
        output_directory=str(output_dir),
        export_json=True,
        fail_on_validation_errors=True
    )
    
    # We will pass mock traces and predicted RCAs
    traces = {
        "SCN-001": EvaluationTrace(run_id="run-123", scenario_id="SCN-001", investigation_id="inv-123"),
        "SCN-002": EvaluationTrace(run_id="run-123", scenario_id="SCN-002", investigation_id="inv-123")
    }
    predicted_rcas = {
        "SCN-001": {"affected_service": "checkout-service", "fault_category": "database_connection_pool", "root_cause_code": "DB_POOL_MAX_CONNECTIONS_REGRESSION"},
        "SCN-002": {"affected_service": "checkout-service", "fault_category": "database_connection_pool", "root_cause_code": "DB_POOL_MAX_CONNECTIONS_REGRESSION"}
    }
    
    result = run_benchmark(config, traces=traces, predicted_rcas=predicted_rcas)
    
    # Assertions on BenchmarkResult
    assert result.benchmark_status == "passed"
    assert result.benchmark_name == "test_bench"
    assert result.execution_duration_sec > 0
    assert result.dataset_summary is not None
    assert result.dataset_summary.total_scenarios == 2
    
    # Assertions on DatasetEvaluationResult
    der = result.dataset_evaluation_result
    assert der is not None
    assert len(der.scenario_results) == 2
    assert der.scenario_results[0].scenario_id == "SCN-001"
    assert der.scenario_results[1].scenario_id == "SCN-002"
    
    # Assert files are exported
    report_file = output_dir / "test_bench_report.json"
    result_file = output_dir / "test_bench_result.json"
    
    assert report_file.exists()
    assert result_file.exists()
    
    # Verify exported paths in result match
    assert str(report_file.resolve()) in result.exported_artifact_paths
    assert str(result_file.resolve()) in result.exported_artifact_paths


def test_validation_failure(tmp_path):
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    
    # Scenario with missing incident_id
    scn1_dir = dataset_dir / "SCN-001"
    scn1_dir.mkdir()
    with open(scn1_dir / "golden.json", "w", encoding="utf-8") as f:
        json.dump({"scenario_id": "SCN-001"}, f) # incomplete

    config = BenchmarkConfig(
        benchmark_name="test_bench_fail",
        dataset_path=str(dataset_dir),
        evaluation_mode=EvaluationMode.MOCK_GRAPH,
        output_directory=str(tmp_path / "output"),
        export_json=True,
        fail_on_validation_errors=True
    )
    
    result = run_benchmark(config)
    assert result.benchmark_status == "failed"
    assert len(result.errors) > 0
    assert any("Validation error" in err for err in result.errors)


def test_empty_dataset(tmp_path):
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    
    config = BenchmarkConfig(
        benchmark_name="test_bench_empty",
        dataset_path=str(dataset_dir),
        evaluation_mode=EvaluationMode.MOCK_GRAPH,
        output_directory=str(tmp_path / "output"),
        export_json=True
    )
    
    result = run_benchmark(config)
    assert result.benchmark_status == "passed"
    assert "Benchmark dataset is empty." in result.warnings
    assert result.dataset_summary.total_scenarios == 0
