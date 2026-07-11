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
Identifiers (affected service, fault category, root-cause code) are normalized as follows:
1.  Trim leading/trailing whitespace.
2.  Convert to lowercase (case-insensitive comparison).
3.  Punctuation and separators (underscores, dashes) are preserved.
No fuzzy matching, token overlaps, or substring matching is performed.

#### Metrics Implemented
1.  **Affected Service Correctness** (`evaluate_affected_service_correctness`):
    *   *Rule*: Returns `1.0` if normalized prediction matches normalized golden affected service.
    *   *Empty policy*: Returns `NOT_APPLICABLE` if golden label has no affected service defined.
    *   *Missing prediction policy*: Returns `0.0` with `prediction_missing: True` in metadata.
2.  **Fault Category Correctness** (`evaluate_fault_category_correctness`):
    *   *Rule*: Compare predicted fault category against golden category.
    *   *Empty policy*: Returns `NOT_APPLICABLE` if golden label is empty.
    *   *Missing prediction policy*: Returns `0.0` with `prediction_missing: True`.
3.  **Root-Cause Code Correctness** (`evaluate_root_cause_code_correctness`):
    *   *Rule*: Returns `1.0` if normalized prediction equals golden root-cause code or matches an acceptable equivalent code. Otherwise `0.0`.
    *   *Empty policy*: Returns `NOT_APPLICABLE` if expected code is not defined.
    *   *Missing prediction policy*: Returns `0.0` with `prediction_missing: True`.
    *   *Equivalent codes*: Uses scenario-specific `acceptable_equivalent_root_cause_codes` mapping. No global taxonomy graph is used.
4.  **Forbidden Unsupported Cause Detection** (`evaluate_forbidden_unsupported_cause_detection`):
    *   *Rule*: Returns `0.0` if predicted root-cause code is in the forbidden set, otherwise `1.0`.
    *   *Empty policy*: Returns `NOT_APPLICABLE` if forbidden set is empty.
    *   *Missing prediction policy*: Returns `1.0` with `prediction_missing: True` (no forbidden code emitted).
5.  **Structured RCA Field Coverage** (`evaluate_structured_rca_field_coverage`):
    *   *Formula*: `number of expected fields with non-empty predictions / number of fields expected in golden`
    *   *Rule*: Computes completeness across `affected_service`, `fault_category`, and `root_cause_code`. Does not evaluate summaries or free text.
    *   *Empty policy*: Returns `NOT_APPLICABLE` if no golden structured fields are expected.
6.  **Combined RCA Evaluator** (`evaluate_structured_rca`):
    *   *Rule*: Runs all 5 metrics and returns a dictionary of results. Aggregations (like averages or quality scores) are intentionally avoided.
7.  **RCA Input Adapter** (`adapt_rca_decision_to_structured`):
    *   *Rule*: Safely maps dictionary or Pydantic structures to structured rca inputs. Does not infer structured keys from natural language text.

#### Targeted Test Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest tests/unit/test_rca_metrics.py -v`
*   **Collected**: 7
*   **Passed**: 7
*   **Failed**: 0
*   **Warnings**: 0
*   **Execution Time**: 0.23s

#### Regression Test Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest tests/unit/test_evaluation_schemas.py tests/unit/test_deterministic_metrics.py -v`
*   **Collected**: 54
*   **Passed**: 54
*   **Failed**: 0
*   **Warnings**: 0
*   **Execution Time**: 0.31s

#### Full Offline Suite Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest`
*   **Collected**: 179
*   **Passed**: 177
*   **Failed**: 0
*   **Skipped**: 2
*   **Warnings**: 3
*   **Execution Time**: 29.05s

---

## Known Limitations and Deferred Instrumentation
*   Runtime node timings, sequence traversal logging, and critic trace logging must be instrumented in the runner/collector phase (Milestone 5/6).
*   RAGAS and other semantic or model-assisted evaluation remain optional and deferred because Phase 9 currently prioritizes deterministic, reproducible evaluation contracts and metrics. Optional semantic evaluation may be integrated later without becoming a dependency of the core offline evaluation path.
*   Runtime secret safety scanning of arbitrary metadata is deferred to later safety milestones.
*   No v0.9.0 release has been created.

---

## Next Milestone
*   **Milestone 4**: Tool-selection efficiency and precision metrics.
