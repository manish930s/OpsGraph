import json
from pathlib import Path
from evals.schemas import BenchmarkConfig, EvaluationMode
from evals.benchmark import run_benchmark


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

    return dataset_dir


def test_deterministic_benchmark_artifacts(tmp_path):
    dataset_dir = setup_mock_dataset(tmp_path)
    output_dir_1 = tmp_path / "output_1"
    output_dir_2 = tmp_path / "output_2"

    config_1 = BenchmarkConfig(
        benchmark_name="test_bench",
        dataset_path=str(dataset_dir),
        evaluation_mode=EvaluationMode.MOCK_GRAPH,
        output_directory=str(output_dir_1),
        export_json=True
    )

    config_2 = BenchmarkConfig(
        benchmark_name="test_bench",
        dataset_path=str(dataset_dir),
        evaluation_mode=EvaluationMode.MOCK_GRAPH,
        output_directory=str(output_dir_2),
        export_json=True
    )

    result_1 = run_benchmark(config_1)
    result_2 = run_benchmark(config_2)

    # Read files
    report_file_1 = output_dir_1 / "test_bench_report.json"
    report_file_2 = output_dir_2 / "test_bench_report.json"
    result_file_1 = output_dir_1 / "test_bench_result.json"
    result_file_2 = output_dir_2 / "test_bench_result.json"

    assert report_file_1.exists()
    assert report_file_2.exists()
    assert result_file_1.exists()
    assert result_file_2.exists()

    with open(report_file_1, "r", encoding="utf-8") as f:
        rep_1 = json.load(f)
    with open(report_file_2, "r", encoding="utf-8") as f:
        rep_2 = json.load(f)

    with open(result_file_1, "r", encoding="utf-8") as f:
        res_1 = json.load(f)
    with open(result_file_2, "r", encoding="utf-8") as f:
        res_2 = json.load(f)

    # Check that report_1 and report_2 are identical except for timestamp/run_id fields
    if "run_manifest" in rep_1 and "started_at" in rep_1["run_manifest"]:
        rep_1["run_manifest"]["started_at"] = "placeholder"
        rep_1["run_manifest"]["run_id"] = "placeholder"
    if "run_manifest" in rep_2 and "started_at" in rep_2["run_manifest"]:
        rep_2["run_manifest"]["started_at"] = "placeholder"
        rep_2["run_manifest"]["run_id"] = "placeholder"

    for result in rep_1.get("scenario_results", []):
        result["run_id"] = "placeholder"
    for result in rep_2.get("scenario_results", []):
        result["run_id"] = "placeholder"

    assert rep_1 == rep_2

    # Check result_1 and result_2 are identical except for runtime/timings/run_id/paths
    if "run_manifest" in res_1 and "started_at" in res_1["run_manifest"]:
        res_1["run_manifest"]["started_at"] = "placeholder"
        res_1["run_manifest"]["run_id"] = "placeholder"
    if "run_manifest" in res_2 and "started_at" in res_2["run_manifest"]:
        res_2["run_manifest"]["started_at"] = "placeholder"
        res_2["run_manifest"]["run_id"] = "placeholder"

    res_1["execution_duration_sec"] = 0.0
    res_2["execution_duration_sec"] = 0.0
    res_1["exported_artifact_paths"] = []
    res_2["exported_artifact_paths"] = []

    if "dataset_evaluation_result" in res_1 and res_1["dataset_evaluation_result"]:
        res_1["dataset_evaluation_result"]["run_manifest"]["started_at"] = "placeholder"
        res_1["dataset_evaluation_result"]["run_manifest"]["run_id"] = "placeholder"
        for scn in res_1["dataset_evaluation_result"]["scenario_results"]:
            scn["run_id"] = "placeholder"

    if "dataset_evaluation_result" in res_2 and res_2["dataset_evaluation_result"]:
        res_2["dataset_evaluation_result"]["run_manifest"]["started_at"] = "placeholder"
        res_2["dataset_evaluation_result"]["run_manifest"]["run_id"] = "placeholder"
        for scn in res_2["dataset_evaluation_result"]["scenario_results"]:
            scn["run_id"] = "placeholder"

    assert res_1 == res_2


def test_html_report_export(tmp_path):
    from evals.html_reporter import export_html_report
    dataset_dir = setup_mock_dataset(tmp_path)
    config = BenchmarkConfig(
        benchmark_name="test_bench",
        dataset_path=str(dataset_dir),
        evaluation_mode=EvaluationMode.MOCK_GRAPH,
        output_directory=str(tmp_path / "output"),
        export_json=False
    )
    result = run_benchmark(config)
    der = result.dataset_evaluation_result
    assert der is not None

    html_path = tmp_path / "report.html"
    export_html_report(der, html_path)
    assert html_path.exists()
    
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    assert "OpsGraph AI — Evaluation Report" in html_content
    assert "SCN-001" in html_content

