import time
from typing import Any, Sequence
from pathlib import Path
from evals.schemas import (
    BenchmarkConfig,
    BenchmarkResult,
    DatasetSummary,
    DatasetEvaluationResult,
    EvaluationRunManifest,
    EvaluationMode
)
from evals.dataset_loader import load_dataset, validate_dataset
from evals.runner import evaluate_scenario
from evals.report_compiler import compile_dataset_report
from evals.export import export_dataset_result_json, export_benchmark_result_json


def validate_benchmark(config: BenchmarkConfig) -> DatasetSummary:
    """
    Validates the dataset under the benchmark configuration.
    """
    return validate_dataset(config.dataset_path)


def run_dataset(
    config: BenchmarkConfig,
    scenarios: Sequence[Any],
    dataset_summary: DatasetSummary | None = None,
    traces: dict[str, Any] | None = None,
    predicted_rcas: dict[str, Any] | None = None,
    run_id: str | None = None
) -> DatasetEvaluationResult:
    """
    Evaluates scenarios sequentially and compiles the dataset evaluation report.
    """
    import uuid
    from datetime import datetime, timezone

    # 1. Run sequential evaluations
    scenario_results = evaluate_scenario(
        scenario=scenarios,
        trace=traces,
        predicted_rca=predicted_rcas,
        mode=config.evaluation_mode,
        run_id=run_id
    )

    if not isinstance(scenario_results, list):
        scenario_results = [scenario_results]

    actual_run_id = run_id or (scenario_results[0].run_id if scenario_results else str(uuid.uuid4()))

    # 2. Collect run manifest info
    scenario_ids = [s.scenario_id for s in scenarios]
    manifest = EvaluationRunManifest(
        run_id=actual_run_id,
        evaluation_version="1.0",
        evaluation_mode=config.evaluation_mode,
        started_at=datetime.now(timezone.utc),
        scenario_ids=scenario_ids
    )

    # 3. Compile report
    return compile_dataset_report(manifest, scenario_results, dataset_summary)


def run_benchmark(
    config: BenchmarkConfig,
    traces: dict[str, Any] | None = None,
    predicted_rcas: dict[str, Any] | None = None
) -> BenchmarkResult:
    """
    Executes a complete benchmark pipeline: loading, validation, evaluation, compilation, and export.
    """
    import uuid
    from datetime import datetime, timezone

    start_time = time.time()
    errors = []
    warnings = []

    dataset_summary = None
    scenarios = []
    dataset_eval_result = None
    exported_paths = []

    actual_run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)

    early_manifest = EvaluationRunManifest(
        run_id=actual_run_id,
        evaluation_version="1.0",
        evaluation_mode=config.evaluation_mode,
        started_at=started_at,
        scenario_ids=[]
    )

    try:
        # 1. Loader & Validation
        try:
            scenarios, dataset_summary = load_dataset(config.dataset_path)
            early_manifest.scenario_ids = [s.scenario_id for s in scenarios]
        except Exception as e:
            errors.append(f"Dataset loader failed: {str(e)}")
            duration = time.time() - start_time
            return BenchmarkResult(
                benchmark_name=config.benchmark_name,
                run_manifest=early_manifest,
                execution_duration_sec=duration,
                benchmark_status="failed",
                errors=errors,
                warnings=warnings
            )

        # 2. Check validation errors
        if dataset_summary.validation_errors:
            for scn_id, err_list in dataset_summary.validation_errors.items():
                for err in err_list:
                    errors.append(f"Validation error for scenario {scn_id}: {err}")

            if config.fail_on_validation_errors:
                duration = time.time() - start_time
                return BenchmarkResult(
                    benchmark_name=config.benchmark_name,
                    run_manifest=early_manifest,
                    dataset_summary=dataset_summary,
                    execution_duration_sec=duration,
                    benchmark_status="failed",
                    errors=errors,
                    warnings=warnings
                )

        # 3. Evaluate and Compile
        if scenarios:
            try:
                dataset_eval_result = run_dataset(
                    config=config,
                    scenarios=scenarios,
                    dataset_summary=dataset_summary,
                    traces=traces,
                    predicted_rcas=predicted_rcas,
                    run_id=actual_run_id
                )

                if dataset_eval_result.run_manifest:
                    early_manifest = dataset_eval_result.run_manifest
            except Exception as e:
                errors.append(f"Evaluation runner or compiler failed: {str(e)}")
                duration = time.time() - start_time
                return BenchmarkResult(
                    benchmark_name=config.benchmark_name,
                    run_manifest=early_manifest,
                    dataset_summary=dataset_summary,
                    execution_duration_sec=duration,
                    benchmark_status="failed",
                    errors=errors,
                    warnings=warnings
                )
        else:
            warnings.append("Benchmark dataset is empty.")

    except Exception as e:
        errors.append(f"Unexpected benchmark execution error: {str(e)}")

    duration = time.time() - start_time

    # Determine status
    if errors:
        status = "failed"
    elif dataset_eval_result and dataset_eval_result.overall_completion_status == "failed":
        status = "failed"
    else:
        status = "passed"

    result = BenchmarkResult(
        benchmark_name=config.benchmark_name,
        run_manifest=early_manifest,
        dataset_summary=dataset_summary,
        dataset_evaluation_result=dataset_eval_result,
        execution_duration_sec=duration,
        exported_artifact_paths=exported_paths,
        benchmark_status=status,
        warnings=warnings,
        errors=errors
    )

    # 4. JSON Export
    if config.export_json:
        try:
            out_dir = Path(config.output_directory)
            out_dir.mkdir(parents=True, exist_ok=True)

            if dataset_eval_result:
                report_path = out_dir / f"{config.benchmark_name}_report.json"
                export_dataset_result_json(dataset_eval_result, report_path)
                exported_paths.append(str(report_path.resolve()))

            result_path = out_dir / f"{config.benchmark_name}_result.json"
            result.exported_artifact_paths = [str(p) for p in exported_paths] + [str(result_path.resolve())]
            export_benchmark_result_json(result, result_path)
            exported_paths.append(str(result_path.resolve()))

            result.exported_artifact_paths = exported_paths
        except Exception as e:
            result.errors.append(f"Export failed: {str(e)}")
            result.benchmark_status = "failed"

    return result
