# OpsGraph AI — Phase 9 Implementation Report

**Phase 9 Status:** PHASE 9 IN PROGRESS  
**Active Branch:** `feature/phase-9-evaluation-framework`  
**Latest Merge / Commit:** 642b55d (merge: finalize phase 9 evaluation architecture plan)  

---

## Completed Milestones

### Milestone 1 — Evaluation Contracts and Trace Schema
*   **Status**: Completed (2026-07-10)
*   **Description**: Created Pydantic schemas, enums, golden scenario contracts, timing models, trace structures, run manifests, and result envelopes for Phase 9 evaluation.

#### Files Added
*   `evals/schemas.py`: Pydantic models for evaluation.
*   `tests/unit/test_evaluation_schemas.py`: Unit tests for evaluation schemas.

#### Files Modified
*   `evals/__init__.py`: Cleaned to import only Phase 9 schemas, decoupling them from legacy metric imports to prevent `ragas` dependency errors during offline import.
*   `evals/metrics.py`: Reverted back to its original state (no longer contains `try...except ImportError` blocks) to keep legacy metrics unaltered.

#### Contracts Implemented
1.  **DatasetSplit**: Enum values: `dev`, `validation`, `test`.
2.  **ScenarioAmbiguity**: Enum values: `unambiguous`, `partially_ambiguous`, `irreducibly_ambiguous`.
3.  **ExpectedTerminalOutcome**: Aligned with Phase 8 routing terminal states: `finalize_rca`, `human_review`, `failure`.
4.  **EvaluationMode**: Enum values: `metric_only`, `mock_graph`, `offline_component`, `live`.
5.  **MetricStatus**: Enum values: `success`, `not_applicable`, `failed`.
6.  **GoldenRCALabels**: Structured labels (affected service, fault category, root-cause code, root-cause summary) with acceptable/forbidden lists.
7.  **GoldenScenario**: Core Golden scenario expectations (IDs, split, ambiguity, outcomes, labels, tools, remediation codes).
8.  **NodeTimingRecord**: Timezone-aware timing models ensuring correct entry/exit order.
9.  **ToolCallTraceRecord**: Structured JSON-serializable diagnostic tool invocations trace records.
10. **CriticTraceRecord**: Iteration-level critic decisions and confidence mapping.
11. **EvaluationTrace**: Full state graph execution trace schema.
12. **EvaluationRunManifest**: Run-level environment and configuration snapshots structurally excluding credential fields.
13. **MetricResult**: Status envelope separating valid numeric scores, N/A, and failures.
14. **ScenarioEvaluationResult**: Envelope containing aggregated results, trace details, warnings, and errors.

#### Validation Invariants
*   **Critic Confidence boundaries**: The trace schema strictly allows `0.0 <= confidence <= 1.0` (inclusive), matching the runtime `CriticDecisionResponse` boundaries, and rejects values outside this range.
*   **Structured Secret Exclusion**: Dedicated credential fields (API keys, tokens, auth headers, environment dumps) are structurally excluded from the run manifest. Runtime leakage scanning of arbitrary nested metadata is handled separately and does not constitute a universal secret-safety guarantee.
*   **Duplicate Rejection Policy**: Rejects duplicate values across terminal outcomes, evidence IDs, required tools, acceptable tools, forbidden tools, tags, acceptable equivalent root-cause codes, forbidden unsupported cause codes, acceptable remediation codes, and scenario IDs in manifests.
*   **Tool Overlap Policy**: Rejects overlaps between `required_tools` and `forbidden_tools`, and between `acceptable_tools` and `forbidden_tools`.
*   **Timestamp Validation**: timing ordering is enforced (finished_at cannot be earlier than started_at) and negative duration is rejected. Unfinished timing records (finished_at = None) are supported.
*   **Finite Numeric Metrics**: The `value` field in `MetricResult` must be a finite float (rejects `NaN` and positive/negative infinity).
*   **Metric Result Invariants**: Validates that SUCCESS status must have a value and zero errors, NOT_APPLICABLE status must have a reason and no value, and FAILED status must have an error type/reason and no value.

---

### Milestone 2 — Deterministic Citation, Evidence, Terminal-State, and Budget Metrics
*   **Status**: Completed (2026-07-10)
*   **Description**: Implemented pure, offline-capable deterministic metrics using Milestone 1 schemas.

#### Files Added
*   `evals/deterministic_metrics.py`: Pure function metrics implementations.
*   `tests/unit/test_deterministic_metrics.py`: Dedicated unit tests for the deterministic metrics.

#### Files Modified
*   `evals/__init__.py`: Exposed deterministic metric functions in package exports.

#### Metrics Implemented
1.  **Citation ID Validity** (`evaluate_citation_id_validity`):
    *   *Formula*: `valid cited IDs / unique cited IDs`
    *   *Empty policy*: Returns `NOT_APPLICABLE` if zero citations are supplied.
    *   *Duplicate policy*: Deduplicates input citations before matching, preventing duplicate inflation.
    *   *Scope*: Validates against caller-provided authoritative universe IDs (e.g. `evidence.json`).
2.  **Invalid Citation Count** (`evaluate_invalid_citation_count`):
    *   *Formula*: Unique cited IDs not found in authoritative universe.
    *   *Empty policy*: Returns `0` if empty.
3.  **Required Evidence Recall** (`evaluate_required_evidence_recall`):
    *   *Formula*: `unique required evidence IDs found / unique required evidence IDs`
    *   *Empty policy*: Returns `NOT_APPLICABLE` if required evidence list is empty.
    *   *Duplicate policy*: Observed and required IDs are deduplicated. Extra observed evidence does not penalize recall.
4.  **Required Evidence Missing Count** (`evaluate_required_evidence_missing_count`):
    *   *Formula*: Number of unique required evidence IDs absent from observed evidence.
    *   *Empty policy*: Returns `NOT_APPLICABLE` if required list is empty.
5.  **Terminal Outcome Correctness** (`evaluate_terminal_outcome_correctness`):
    *   *Rule*: Returns `1.0` if actual terminal outcome is present in the scenario's acceptable outcomes list, otherwise `0.0`.
6.  **Iteration Budget Utilization** (`evaluate_iteration_budget_utilization`):
    *   *Formula*: `iteration_count / max_iterations`
    *   *Rules*: Validates non-negative counts and positive max budget. Does not clamp values exceeding `1.0`.
7.  **Tool Call Budget Utilization** (`evaluate_tool_budget_utilization`):
    *   *Formula*: `tool_call_count / max_tool_calls`
8.  **Context Rebuild Budget Utilization** (`evaluate_context_rebuild_budget_utilization`):
    *   *Formula*: `context_rebuild_count / max_rebuilds`
9.  **Budget Compliance** (`evaluate_budget_compliance`):
    *   *Rule*: Returns `1.0` if all iteration, tool-call, and context rebuild counters are within limit, otherwise `0.0`.
    *   *Metadata*: Exposes a list of exceeded dimensions in `exceeded_budgets`.
10. **Known Secret Leakage Detection** (`evaluate_known_secret_leakage`):
    *   *Rule*: Returns `1.0` if no leaked values or bearer token patterns are detected, otherwise `0.0`.
    *   *Empty policy*: Returns `NOT_APPLICABLE` if the known secrets list is empty and pattern scanning is disabled.
    *   *Limitations*: Scanning is limited to caller-provided known secrets list and standard authorization bearer patterns. Secrets under 4 characters are ignored to prevent false positives. Metadata does not expose matched text.

#### Targeted Test Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest tests/unit/test_deterministic_metrics.py -v`
*   **Collected**: 28
*   **Passed**: 28
*   **Failed**: 0
*   **Warnings**: 0
*   **Execution Time**: 0.20s

#### Full Offline Suite Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest`
*   **Collected**: 172
*   **Passed**: 170
*   **Failed**: 0
*   **Skipped**: 2
*   **Warnings**: 3
*   **Execution Time**: 18.90s

---

### Milestone 3 — Structured RCA Matching Metrics
*   **Status**: Completed (2026-07-11)
*   **Description**: Implemented pure, offline-capable structured RCA matching metrics to evaluate RCA outputs against scenario golden labels.

#### Files Added
*   `evals/rca_metrics.py`: Structured RCA matching metrics implementations.
*   `tests/unit/test_rca_metrics.py`: Dedicated unit tests for the structured RCA metrics.

#### Files Modified
*   `evals/__init__.py`: Exposed structured RCA metrics and helper in package exports.

#### Normalization Policy
Identifiers (affected service, fault category, root-cause code) are normalized strictly as follows:
1.  Trim leading and trailing whitespace.
2.  Convert to lowercase (making comparisons case-insensitive).
3.  Punctuation and separators (underscores, dashes) are preserved.
No fuzzy matching, token overlaps, or substring matching is performed. For example:
*   `DB_POOL_EXHAUSTION` matches `db_pool_exhaustion`.
*   `DB_POOL_EXHAUSTION` does not match `DB-POOL-EXHAUSTION`.
*   `payments-api` does not match `payments_api`.
*   `database` does not match `database-service`.
*   `pool exhaustion` does not match `connection pool exhaustion`.

#### Runtime RCA Compatibility and Adapter Behavior
The actual runtime RCA output schema is `RCADecisionResponse` in `app/schemas/model_response.py`.
*   **Runtime compatibility limitation**: The runtime `RCADecisionResponse` does *not* directly expose structured fields for `affected_service`, `fault_category`, or `root_cause_code`. These fields exist only in evaluation-layer contracts (e.g. `GoldenRCALabels`).
*   **Adapter Behavior**: The adapter `adapt_rca_decision_to_structured` safely converts `RCADecisionResponse` to structured fields. It returns `None` for missing keys and explicitly avoids parsing or inferring codes from natural language fields (such as `summary` or `hypotheses`).

#### Root-Cause Expectation Policy
The accepted root-cause code set is defined as the union of the canonical expected `root_cause_code` (if present) and the `acceptable_equivalent_root_cause_codes`.
*   **Equivalent-only expectations**: If the canonical expected code is absent but acceptable equivalents are defined, the scenario remains valid and prediction is matched against the equivalent set.
*   **Empty accepted set**: If both canonical and equivalent expectations are absent, the metric returns `NOT_APPLICABLE`.

#### Forbidden Cause Independence
Forbidden unsupported cause detection operates independently of correctness. An incorrect prediction that does not match a forbidden code will score `0.0` for correctness and `1.0` for forbidden cause detection.

#### Missing Prediction Policies
*   **Affected Service / Fault Category Correctness**: Returns `0.0` with `prediction_missing: True` in metadata.
*   **Root-Cause Code Correctness**: Returns `0.0` with `prediction_missing: True` in metadata.
*   **Forbidden Unsupported Cause Detection**: Returns `1.0` with `prediction_missing: True` in metadata (as no forbidden code was emitted).

#### Metrics Implemented
1.  **Affected Service Correctness** (`evaluate_affected_service_correctness`):
    *   *Rule*: Returns `1.0` if normalized prediction matches normalized golden affected service.
    *   *Empty policy*: Returns `NOT_APPLICABLE` if golden label has no affected service defined.
2.  **Fault Category Correctness** (`evaluate_fault_category_correctness`):
    *   *Rule*: Compare predicted fault category against golden category.
    *   *Empty policy*: Returns `NOT_APPLICABLE` if golden label is empty.
3.  **Root-Cause Code Correctness** (`evaluate_root_cause_code_correctness`):
    *   *Rule*: Returns `1.0` if normalized prediction equals golden root-cause code or matches an acceptable equivalent code. Otherwise `0.0`.
4.  **Forbidden Unsupported Cause Detection** (`evaluate_forbidden_unsupported_cause_detection`):
    *   *Rule*: Returns `0.0` if predicted root-cause code is in the forbidden set, otherwise `1.0`.
    *   *Empty policy*: Returns `NOT_APPLICABLE` if forbidden set is empty.
5.  **Structured RCA Field Coverage** (`evaluate_structured_rca_field_coverage`):
    *   *Formula*: `number of expected fields with non-empty predictions / number of fields expected in golden`
    *   *Rule*: Computes completeness across `affected_service`, `fault_category`, and `root_cause_code`. Whitespace-only values are treated as missing. Fields without golden expectations are excluded from denominator.
6.  **Combined RCA Evaluator** (`evaluate_structured_rca`):
    *   *Rule*: Runs all 5 metrics and returns a dictionary of results. Aggregations (like averages or quality scores) are intentionally avoided, and individual `NOT_APPLICABLE` statuses are preserved independently.
7.  **RCA Input Adapter** (`adapt_rca_decision_to_structured`):
    *   *Rule*: Safely maps dictionary or Pydantic structures to structured rca inputs. Does not infer structured keys from natural language text.

#### Targeted Test Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest tests/unit/test_rca_metrics.py -v`
*   **Collected**: 12
*   **Passed**: 12
*   **Failed**: 0
*   **Warnings**: 0
*   **Execution Time**: 0.22s

#### Full Offline Suite Results (Milestone 3 Corrected Baseline)
*   **Command**: `.\venv\Scripts\python.exe -m pytest`
*   **Collected**: 184
*   **Passed**: 182
*   **Failed**: 0
*   **Skipped**: 2
*   **Warnings**: 3
*   **Execution Time**: 24.18s

---

### Milestone 4 — Tool-Selection Precision and Efficiency Metrics
*   **Status**: Completed (2026-07-11)
*   **Description**: Implemented pure, offline-capable tool metrics to evaluate tool use against scenario-level contracts.

#### Files Added
*   `evals/tool_metrics.py`: Tool metrics implementation file.
*   `tests/unit/test_tool_metrics.py`: Focused unit tests for tool metrics.

#### Files Modified
*   `evals/__init__.py`: Exposed tool metrics and adapter helper in package exports.

#### Tool Normalization Policy
Tool names are normalized as follows:
1.  Trim leading/trailing whitespace.
2.  Convert to lowercase.
3.  Preserves all internal characters and punctuation (underscores, dashes).
No fuzzy matching, aliases, or substring matches are performed.

#### Trace Parser Adapter and Attempted vs Successful Calls
*   **Trace Adapter** (`extract_tool_names_from_trace`): Extracts tool names in order from a sequence of tool trace records (`ToolCallTraceRecord`), dicts, or strings.
*   **Attempted Call Semantics**: The metrics evaluate all attempted tool selections. Failed tool selections are preserved and evaluated because a forbidden tool selection constitutes a policy violation regardless of runtime execution success.

#### Metrics Implemented
1.  **Required Tool Recall** (`evaluate_required_tool_recall`):
    *   *Formula*: `unique required tools observed / unique required tools expected`
    *   *Empty policy*: Returns `NOT_APPLICABLE` if required tool expectations are empty.
    *   *Duplicates*: Duplicates do not increase recall.
2.  **Allowed Tool Precision** (`evaluate_allowed_tool_precision`):
    *   *Formula*: `unique observed tools in allowed set / unique observed tools`
    *   *Allowed set*: Required tools union acceptable tools.
    *   *Empty policy*: Returns `NOT_APPLICABLE` if no tools were invoked.
3.  **Forbidden Tool Invocation Count** (`evaluate_forbidden_tool_invocation_count`):
    *   *Rule*: Total count of forbidden tool invocations.
    *   *Empty policy*: Returns `NOT_APPLICABLE` if forbidden set is empty.
4.  **Forbidden Tool Compliance** (`evaluate_forbidden_tool_compliance`):
    *   *Rule*: Binary safety compliance (1.0 if no forbidden tools invoked, else 0.0).
    *   *Empty policy*: Returns `NOT_APPLICABLE` if forbidden set is empty.
5.  **Unnecessary Tool Call Count** (`evaluate_unnecessary_tool_call_count`):
    *   *Rule*: Total count of tool calls outside required/acceptable tools. Unknown tools are treated as unnecessary.
    *   *Empty policy*: If required and acceptable contracts are empty, all observed calls are unnecessary.
6.  **Duplicate Tool Call Count** (`evaluate_duplicate_tool_call_count`):
    *   *Rule*: Total count of tool calls beyond the first invocation of each tool name.
7.  **Tool Call Efficiency** (`evaluate_tool_call_efficiency`):
    *   *Formula*: `unique required expected count / total actual tool calls` capped at 1.0.
    *   *Empty policy*: Returns `0.0` if actual calls is zero and required floor is non-zero. Returns `NOT_APPLICABLE` if required floor is zero.
    *   *Note*: Efficiency is an operational count-ratio indicator and does not measure correctness.
8.  **Combined Tool Evaluator** (`evaluate_tool_selection`):
    *   *Rule*: Runs all 7 metrics and returns a dictionary. Individual N/A statuses are preserved independently, and averages are not calculated.

#### Targeted Test Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest tests/unit/test_tool_metrics.py -v`
*   **Collected**: 11
*   **Passed**: 11
*   **Failed**: 0
*   **Warnings**: 0
*   **Execution Time**: 0.27s

#### Regression Test Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest tests/unit/test_evaluation_schemas.py tests/unit/test_deterministic_metrics.py tests/unit/test_rca_metrics.py tests/unit/test_tool_metrics.py -v`
*   **Collected**: 77
*   **Passed**: 77
*   **Failed**: 0
*   **Warnings**: 0
*   **Execution Time**: 0.43s

#### Full Offline Suite Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest`
*   **Collected**: 195
*   **Passed**: 193
*   **Failed**: 0
*   **Skipped**: 2
*   **Warnings**: 3
*   **Execution Time**: 24.55s

---

### Milestone 5 — Offline Evaluation Runner
*   **Status**: Completed (2026-07-11)
*   **Description**: Implemented the offline evaluation runner responsible for orchestrating the metrics implemented during Milestones 2–4.

#### Files Added
*   `evals/runner.py`: Deterministic evaluation runner implementing wrapper evaluation functions.
*   `tests/unit/test_runner.py`: Unit tests for the evaluation runner.

#### Files Modified
*   `evals/__init__.py`: Exposed public runner functions in package exports.

#### Runner Architecture
*   **Sequential Execution**: Orchestrates evaluation sequentially (no parallelization) to preserve deterministic, reproducible ordering.
*   **No Internal Metric Logic**: Coordinates existing metrics from `evals/deterministic_metrics.py`, `evals/rca_metrics.py`, and `evals/tool_metrics.py` without introducing new metric calculations.
*   **Non-Mutating Context**: Extracted context (cited evidence, authoritative universe, observed evidence, terminal outcome, budgets, timings) is treated as read-only.

#### Supported Modes
*   `MOCK_GRAPH`: Expects trace to be present. Missing traces trigger warnings and evaluate trace-dependent metrics as `NOT_APPLICABLE`.
*   `OFFLINE_COMPONENT`: Supports components evaluation. Missing traces trigger warnings and evaluate trace-dependent metrics as `NOT_APPLICABLE`.
*   *Note: `LIVE` mode is not implemented and remains future work.*

#### Metric Execution Pipeline Order
Evaluation executes metric functions in the following exact pipeline order:
1.  Citation metrics (`Citation ID Validity`, `Invalid Citation Count`)
2.  Evidence metrics (`Required Evidence Recall`, `Required Evidence Missing Count`)
3.  Terminal outcome metrics (`Terminal Outcome Correctness`)
4.  Budget metrics (`Iteration/Tool/Context Budget Utilization`, `Budget Compliance`)
5.  Secret leakage metrics (`Known Secret Leakage Detection`)
6.  Structured RCA metrics (`Affected Service/Fault Category/Root-Cause Code Correctness`, `Forbidden Unsupported Cause Detection`, `Structured RCA Field Coverage`)
7.  Tool metrics (`Required Recall`, `Allowed Precision`, `Forbidden Invocation Count`, `Forbidden Compliance`, `Unnecessary Count`, `Duplicate Count`, `Tool Call Efficiency`)

#### Aggregation Rules
*   Collects all `MetricResult` objects into a flat list under `ScenarioEvaluationResult.metrics`.
*   Does not average scores, weight metrics, or calculate composite quality scores.
*   Preserves individual `NOT_APPLICABLE` and `FAILED` metric statuses independently.

#### Warning and Failure Handling
*   **Warnings**: Non-fatal conditions (missing trace, missing timing records, missing tool trace, missing predicted RCA, missing golden labels) append warning strings to `ScenarioEvaluationResult.warnings` without failing the evaluation.
*   **Failures**: Fatal conditions that prevent evaluation from proceeding (invalid scenario object, invalid trace object, unexpected metric exceptions) are captured, append descriptive errors to `ScenarioEvaluationResult.errors`, and keep evaluation results valid but empty of metrics.

#### Manifest Generation
*   **Pydantic schema**: `EvaluationRunManifest`
*   **Populated fields**: timezone-aware started/finished timestamps, mode, scenario IDs, system platform, Python version, git commit hash (retrieved dynamically), LLM config, and graph budgets (read from active settings).
*   **Secrets**: No API keys, credentials, or environment variables are inspected, scanned, or written to the manifest.

#### Public API
*   `evaluate_scenario(scenario: GoldenScenario, trace: EvaluationTrace | None, predicted_rca: Any, mode: EvaluationMode, run_id: str | None = None) -> ScenarioEvaluationResult`
*   `evaluate_mock_graph(scenario: GoldenScenario, trace: EvaluationTrace | None, predicted_rca: Any, run_id: str | None = None) -> ScenarioEvaluationResult`
*   `evaluate_offline_component(scenario: GoldenScenario, trace: EvaluationTrace | None, predicted_rca: Any, run_id: str | None = None) -> ScenarioEvaluationResult`

#### Targeted Test Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest tests/unit/test_runner.py -v`
*   **Collected**: 6
*   **Passed**: 6
*   **Failed**: 0
*   **Warnings**: 0
*   **Execution Time**: 0.75s

#### Regression Test Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest tests/unit/test_evaluation_schemas.py tests/unit/test_deterministic_metrics.py tests/unit/test_rca_metrics.py tests/unit/test_tool_metrics.py tests/unit/test_runner.py -v`
*   **Collected**: 83
*   **Passed**: 83
*   **Failed**: 0
*   **Warnings**: 0
*   **Execution Time**: 0.87s

#### Full Offline Suite Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest`
*   **Collected**: 201
*   **Passed**: 199
*   **Failed**: 0
*   **Skipped**: 2
*   **Warnings**: 3
*   **Execution Time**: 26.10s

---

### Milestone 6 — Dataset Loader and Golden Scenario Integration
*   **Status**: Completed (2026-07-11)
*   **Description**: Implemented deterministic dataset loading, validation, and runner integration supporting complete datasets of Golden Scenarios.

#### Files Added
*   `evals/dataset_loader.py`: Dataset loader and validation logic.
*   `tests/unit/test_dataset_loader.py`: Unit tests for the dataset loader.

#### Files Modified
*   `evals/__init__.py`: Exposed dataset loader functions in package exports.
*   `evals/runner.py`: Extended all runner wrappers to accept either a single scenario or an iterable dataset of scenarios, mapping traces/inputs scenario-by-scenario.

#### Dataset Directory Structure
*   **Directory Format**: Directories containing `golden.json` and optionally `evidence.json`.
*   **Standalone Format**: Standalone JSON files describing a scenario.
*   **Discovered paths**: Sorted deterministically by name, and final datasets are sorted ascending by `scenario_id`.

#### Compatibility Mapping
*   Automatically maps legacy schema fields (like `expected_tools` to `required_tools` and `ground_truth` to `labels`).
*   Applies fallback defaults (e.g. `split: "dev"`, `ambiguity: "unambiguous"`, `expected_terminal_outcome: "finalize_rca"`, `acceptable_terminal_outcomes: ["finalize_rca"]`) for missing fields.

#### Validation Strategy
*   Checks for missing required fields (`scenario_id`, `incident_id`).
*   Runs strict Pydantic validation against `GoldenScenario` schema.
*   Validates scenario references by matching all required evidence IDs against actual entries in `evidence.json`.
*   Detects duplicate scenario IDs across the entire dataset.
*   Collects all validation errors/warnings continuously across all items without short-circuiting on the first error.

#### DatasetSummary
Structure includes:
*   `total_scenarios` (integer)
*   `split_counts` (dictionary of split counts)
*   `ambiguity_counts` (dictionary of ambiguity counts)
*   `scenario_ids` (sorted list of scenario IDs)
*   `validation_errors` (scenario ID -> list of error strings)
*   `validation_warnings` (scenario ID -> list of warning strings)

#### Public API
*   `discover_scenarios(base_dir: str | Path) -> list[Path]`
*   `load_scenario(path: str | Path) -> tuple[GoldenScenario | None, list[str], list[str]]`
*   `load_dataset(base_dir: str | Path) -> tuple[list[GoldenScenario], DatasetSummary]`
*   `validate_dataset(base_dir: str | Path) -> DatasetSummary`

#### Runner Integration
*   `evaluate_scenario`, `evaluate_mock_graph`, and `evaluate_offline_component` check the `scenario` type.
*   If passed an iterable (excluding string/dict/BaseModel), they run evaluations sequentially and return a `list[ScenarioEvaluationResult]`.
*   Trace and predicted RCA parameters can be passed as dictionaries keyed by scenario ID for matching, maintaining full backward compatibility.

#### Targeted Test Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest tests/unit/test_dataset_loader.py -v`
*   **Collected**: 8
*   **Passed**: 8
*   **Failed**: 0
*   **Warnings**: 0
*   **Execution Time**: 0.70s

#### Regression Test Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest tests/unit/test_evaluation_schemas.py tests/unit/test_deterministic_metrics.py tests/unit/test_rca_metrics.py tests/unit/test_tool_metrics.py tests/unit/test_runner.py tests/unit/test_dataset_loader.py -v`
*   **Collected**: 91
*   **Passed**: 91
*   **Failed**: 0
*   **Warnings**: 0
*   **Execution Time**: 1.34s

#### Full Offline Suite Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest`
*   **Collected**: 209
*   **Passed**: 207
*   **Failed**: 0
*   **Skipped**: 2
*   **Warnings**: 3
*   **Execution Time**: 25.32s

---

### Milestone 7 — Dataset Evaluation Result Aggregation and Report Compiler
*   **Status**: Completed (2026-07-11)
*   **Description**: Implemented report compilation and results aggregation, converting individual scenario evaluation results into a single dataset-level `DatasetEvaluationResult` output as deterministic JSON.

#### Files Added
*   `evals/report_compiler.py`: Dataset level report compiler implementation.
*   `evals/export.py`: Stable JSON serialization and file exporter.
*   `tests/unit/test_report_compiler.py`: Unit tests for the report compiler and JSON export.

#### Files Modified
*   `evals/schemas.py`: Appended `DatasetSummary` (moved from dataset_loader), `MetricSummary`, `WarningCategorySummary`, `ErrorCategorySummary`, `EvaluationStatistics`, and `DatasetEvaluationResult` schemas.
*   `evals/dataset_loader.py`: Removed duplicate `DatasetSummary` definition and imported it from schemas.
*   `evals/__init__.py`: Exposed compiler, export helper, and all new schemas.

#### DatasetEvaluationResult Structure
*   `run_manifest`: `EvaluationRunManifest`
*   `dataset_summary`: `DatasetSummary`
*   `scenario_results`: list of `ScenarioEvaluationResult` objects (sorted by `scenario_id` ascending).
*   `metric_summaries`: dictionary mapping metric name to `MetricSummary` objects (sorted by name ascending).
*   `warning_summary`: dictionary mapping category name to `WarningCategorySummary` objects (sorted by category name ascending).
*   `error_summary`: dictionary mapping category name to `ErrorCategorySummary` objects (sorted by category name ascending).
*   `evaluation_statistics`: Pydantic object capturing total scenarios, evaluated, successful, partial, failed, and completion ratio.
*   `overall_completion_status`: string indicator (`completed`, `failed`, or `partial`).

#### Report Compiler Aggregation Rules
*   **Metric Summaries**: Aggregates each metric independently. Computes total counts, SUCCESS count, NOT_APPLICABLE count, FAILED count, minimum, maximum, mean, and median values. It does not average different metric names together.
*   **Warning Aggregation**: Groups warnings by standard categories (`missing_trace`, `missing_timing`, `missing_tool_trace`, `missing_rca`, `missing_labels`, `validation_warning`, `other_warning`). Details count and affected scenarios.
*   **Error Aggregation**: Groups errors by categories (`validation_errors`, `unexpected_exceptions`, `evaluation_failures`). Details count and affected scenarios.
*   **Completion Statistics**: Reports scenario outcomes. A scenario evaluation is successful if it finishes with no errors. It is partial if it finished with both errors and metrics. It is failed if it has errors and zero metrics.

#### Public API
*   `compile_dataset_report(run_manifest: EvaluationRunManifest, scenario_results: Sequence[ScenarioEvaluationResult], dataset_summary: DatasetSummary | None = None) -> DatasetEvaluationResult`
*   `export_dataset_result_json(result: DatasetEvaluationResult, output_path: str | Path) -> None`

#### Export and Serialization Guarantees
*   Uses `export_dataset_result_json` to dump the compiled dataset evaluation result into a deterministic JSON string.
*   Employs sorting of JSON keys (`sort_keys=True`) and standard 2-space indentation formatting, providing OS-independent output.

#### Targeted Test Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest tests/unit/test_report_compiler.py -v`
*   **Collected**: 5
*   **Passed**: 5
*   **Failed**: 0
*   **Warnings**: 0
*   **Execution Time**: 0.23s

#### Regression Test Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest tests/unit/test_evaluation_schemas.py tests/unit/test_deterministic_metrics.py tests/unit/test_rca_metrics.py tests/unit/test_tool_metrics.py tests/unit/test_runner.py tests/unit/test_dataset_loader.py tests/unit/test_report_compiler.py -v`
*   **Collected**: 96
*   **Passed**: 96
*   **Failed**: 0
*   **Warnings**: 0
*   **Execution Time**: 1.49s

#### Full Offline Suite Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest`
*   **Collected**: 214
*   **Passed**: 212
*   **Failed**: 0
*   **Skipped**: 2
*   **Warnings**: 3
*   **Execution Time**: 26.50s

---

### Milestone 8 — Benchmark Execution Engine
*   **Status**: Completed (2026-07-11)
*   **Description**: Implemented the benchmark execution engine to run complete datasets of Golden Scenarios and compile and export reproducible benchmark JSON artifacts.

#### Files Added
*   `evals/benchmark.py`: Benchmark execution engine orchestrating loading, validation, sequential execution, compilation, and export.
*   `tests/unit/test_benchmark.py`: Unit tests verifying the benchmark engine.

#### Files Modified
*   `evals/schemas.py`: Appended `BenchmarkConfig` and `BenchmarkResult` schemas.
*   `evals/export.py`: Added `export_benchmark_result_json` helper to export benchmark results deterministically.
*   `evals/__init__.py`: Exposed benchmark config, result, and runner functions.

#### Benchmark pipeline Order
Orchestrates execution sequentially:
Dataset Loader -> Validation -> Scenario Evaluation -> Dataset Report Compilation -> JSON Export

#### BenchmarkConfig Structure
*   `benchmark_name` (str)
*   `dataset_path` (str)
*   `evaluation_mode` (`EvaluationMode`)
*   `output_directory` (str)
*   `export_json` (bool, default `True`)
*   `fail_on_validation_errors` (bool, default `False`)

#### BenchmarkResult Structure
*   `benchmark_name` (str)
*   `run_manifest` (`EvaluationRunManifest`)
*   `dataset_summary` (`DatasetSummary`)
*   `dataset_evaluation_result` (`DatasetEvaluationResult`)
*   `execution_duration_sec` (float)
*   `exported_artifact_paths` (list of str paths)
*   `benchmark_status` (str, `"passed"` or `"failed"`)
*   `warnings` (list of warning strings)
*   `errors` (list of error strings)

#### Error Handling Separation
*   **Dataset loader errors**: Captured and prefixed as `"Dataset loader failed: ..."`
*   **Validation errors**: Captured per scenario as `"Validation error for scenario SCN-XXX: ..."`
*   **Runner/compiler failures**: Captured and prefixed as `"Evaluation runner or compiler failed: ..."`
*   **Export errors**: Captured and prefixed as `"Export failed: ..."`

#### Public API
*   `validate_benchmark(config: BenchmarkConfig) -> DatasetSummary`
*   `run_dataset(config: BenchmarkConfig, scenarios: Sequence[Any], dataset_summary: DatasetSummary | None = None, traces: dict[str, Any] | None = None, predicted_rcas: dict[str, Any] | None = None, run_id: str | None = None) -> DatasetEvaluationResult`
*   `run_benchmark(config: BenchmarkConfig, traces: dict[str, Any] | None = None, predicted_rcas: dict[str, Any] | None = None) -> BenchmarkResult`

#### Targeted Test Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest tests/unit/test_benchmark.py -v`
*   **Collected**: 4
*   **Passed**: 4
*   **Failed**: 0
*   **Warnings**: 0
*   **Execution Time**: 0.71s

#### Regression Test Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest tests/unit/test_evaluation_schemas.py tests/unit/test_deterministic_metrics.py tests/unit/test_rca_metrics.py tests/unit/test_tool_metrics.py tests/unit/test_runner.py tests/unit/test_dataset_loader.py tests/unit/test_report_compiler.py tests/unit/test_benchmark.py -v`
*   **Collected**: 100
*   **Passed**: 100
*   **Failed**: 0
*   **Warnings**: 0
*   **Execution Time**: 1.83s

#### Full Offline Suite Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest`
*   **Collected**: 218
*   **Passed**: 216
*   **Failed**: 0
*   **Skipped**: 2
*   **Warnings**: 3
*   **Execution Time**: 88.56s

---

## Known Limitations and Deferred Instrumentation
*   Runtime execution instrumentation (node timings, sequence traversal logging, and critic trace capture) remains future work. The current evaluation framework consumes existing traces but does not instrument runtime execution.
*   RAGAS and other semantic or model-assisted evaluation remain optional and deferred because Phase 9 currently prioritizes deterministic, reproducible evaluation contracts and metrics. Optional semantic evaluation may be integrated later without becoming a dependency of the core offline evaluation path.
*   Runtime secret safety scanning of arbitrary nested metadata is deferred to later safety milestones.
*   No v0.9.0 release has been created.

---

## Next Milestone
*   **Milestone 9**: Milestone 9 — Release Preparation, CI Integration, Documentation, HTML Reporting and v0.9.0
