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
*   `evals/__init__.py`: Added imports for Phase 9 schema classes to expose them cleanly.
*   `evals/metrics.py`: Wrapped `ragas` imports in `try...except ImportError` blocks to enable offline imports without `ragas` dependency.

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
12. **EvaluationRunManifest**: Run-level environment and configuration snapshots without credential leakage.
13. **MetricResult**: Status envelope separating valid numeric scores, N/A, and failures.
14. **ScenarioEvaluationResult**: Envelope containing aggregated results, trace details, warnings, and errors.

#### Validation Invariants
*   Acceptable terminal outcomes must contain the expected terminal outcome.
*   All duplicate values are strictly rejected across lists (e.g. required evidence, acceptable terminal outcomes, tools, tags) to prevent malformed data.
*   Conflicting tools categories are rejected (cannot overlap required/acceptable with forbidden).
*   Negative bounds are blocked (e.g., negative duration, negative iteration counts, negative latency).
*   Timing ordering is enforced (finished_at cannot be before started_at).
*   Critic confidence must lie strictly between `0.0` and `1.0`.
*   Metric status combinations are strictly validated (e.g., failed status cannot have a numeric value, success status must have a value).

#### Targeted Test Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest tests/unit/test_evaluation_schemas.py -v`
*   **Collected**: 25
*   **Passed**: 25
*   **Failed**: 0
*   **Warnings**: 0
*   **Execution Time**: 2.33s

#### Full Offline Suite Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest`
*   **Collected**: 143
*   **Passed**: 141
*   **Failed**: 0
*   **Skipped**: 2
*   **Warnings**: 3
*   **Execution Time**: 66.04s

---

## Known Limitations and Deferred Instrumentation
*   Runtime node timings, sequence traversal logging, and critic trace logging must be instrumented in the runner/collector phase (Milestone 5/6).
*   Ragas integration remains deferred due to lack of environment installation support.
*   Credential safety scanning is defined in schemas but will be enforced at runtime by the future evaluation runner.
*   No v0.9.0 release has been created.

---

## Next Milestone
*   **Milestone 2**: Deterministic citation, evidence, terminal, and budget metrics.
