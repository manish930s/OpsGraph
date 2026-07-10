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
12. **EvaluationRunManifest**: Run-level environment and configuration snapshots without credential leakage.
13. **MetricResult**: Status envelope separating valid numeric scores, N/A, and failures.
14. **ScenarioEvaluationResult**: Envelope containing aggregated results, trace details, warnings, and errors.

#### Validation Invariants
*   **Critic Confidence boundaries**: The trace schema strictly allows `0.0 <= confidence <= 1.0` (inclusive), matching the runtime `CriticDecisionResponse` boundaries, and rejects values outside this range.
*   **Structured Secret Exclusion**: Dedicated credential fields (API keys, tokens, auth headers, full environment dumps) are structurally excluded from the run manifest. Runtime leakage scanning of arbitrary nested metadata is deferred to later milestones.
*   **Duplicate Rejection Policy**: Rejects duplicate values across terminal outcomes, evidence IDs, required tools, acceptable tools, forbidden tools, tags, acceptable equivalent root-cause codes, forbidden unsupported cause codes, acceptable remediation codes, and scenario IDs in manifests.
*   **Tool Overlap Policy**: Rejects overlaps between `required_tools` and `forbidden_tools`, and between `acceptable_tools` and `forbidden_tools`.
*   **Timestamp Validation**: timing ordering is enforced (finished_at cannot be earlier than started_at) and negative duration is rejected. Unfinished timing records (finished_at = None) are supported.
*   **Finite Numeric Metrics**: The `value` field in `MetricResult` must be a finite float (rejects `NaN` and positive/negative infinity).
*   **Metric Result Invariants**: Validates that SUCCESS status must have a value and zero errors, NOT_APPLICABLE status must have a reason and no value, and FAILED status must have an error type/reason and no value.

#### Targeted Test Results
*   **Command**: `.\venv\Scripts\python.exe -m pytest tests/unit/test_evaluation_schemas.py -v`
*   **Collected**: 26
*   **Passed**: 26
*   **Failed**: 0
*   **Warnings**: 0
*   **Execution Time**: 0.17s

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
*   Runtime secret safety scanning of arbitrary metadata is deferred to later safety milestones.
*   No v0.9.0 release has been created.

---

## Next Milestone
*   **Milestone 2**: Deterministic citation, evidence, terminal, and budget metrics.
