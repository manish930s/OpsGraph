# OpsGraph AI — Phase 9 Evaluation, Benchmarking, and Quality Framework Plan

**Release Status:** PLANNING COMPLETE — IMPLEMENTATION NOT STARTED  
**Phase:** Phase 9 — Evaluation, Benchmarking, and Investigation Quality Framework  
**Execution Date:** 2026-07-10  
**Python Runtime:** CPython 3.14.0 (Windows)  

---

## 1. Executive Summary

Phase 9 establishes a rigorous, offline-safe evaluation and benchmarking framework for OpsGraph AI. Having successfully implemented the stateful, bounded investigation graph in Phase 8, we must systematically measure the quality of generated root-cause analyses (RCAs), the accuracy and precision of telemetry tool invocations, the correctness of critic decisions, and overall execution safety.

This revised plan addresses crucial evaluation requirements, separating dataset split semantics from scenario ambiguity, defining explicit terminal outcome contracts, and implementing mathematically sound metric formulas. It prioritizes fast, rule-based python evaluators over costly, non-deterministic LLM-as-judge runs, laying out a baseline-first path to quality benchmarking.

---

## 2. Current Evaluation Assets

An audit of the repository shows the following evaluation-ready files and datasets are already implemented and available:

1.  **Scenario Definitions Directory** (`DATA/scenarios/definitions/`):
    *   `SCN-DB-POOL-001.json`: Medium-difficulty database connection pool regression incident. Maps the timeline, required evidence types, expected tools, and acceptable remediation codes.
2.  **Synthetic Scenario Telemetry** (`DATA/generated/SCN-DB-POOL-001/`):
    *   `incident.json`: Ground-truth incident record details (`INC-0042`).
    *   `evidence.json`: Pre-packaged diagnostic evidence items (deployments, metrics, logs, and traces) with stable IDs (e.g., `DEPLOY-EV-0042-001`).
    *   `deployments.json` & `logs.jsonl` & `metrics.jsonl`: Raw simulated repository database observations used by retrieval tools.
    *   `golden.json`: Curated ground-truth targets matching the `GoldenCase` Pydantic model.
3.  **General QA Benchmark** (`evals/golden_dataset.json`):
    *   260 lines of general Kubernetes RAG question-answer pairs (`rag_samples`). This is used for general retrieval metrics and is historically distinct from SRE incident troubleshooting.
4.  **Existing Code Structures**:
    *   `GoldenCase` schema (`app/schemas/rca.py`): Model constraints for evaluating outcomes.
    *   `ScenarioRepository` (`app/services/telemetry/repository.py`): Code for loading scenarios, telemetry, and golden targets.

---

## 3. Evaluation Goals and Non-Goals

### Goals
*   **Deterministic Auditing**: Validate citation correctness, budget utilization, and terminal states using zero-token python logic.
*   **Investigation Quality Assessment**: Measure if the graph collects all necessary telemetry evidence before reaching an ACCEPT decision.
*   **Calibrated Escalation**: Ensure that the critic correctly routes to `human_review` under ambiguous or incomplete data and terminates with `failure` under parameter mismatches.
*   **Leakage Verification**: Detect known credential leakage into evaluation artifacts, traces, failure payloads, and reports.
*   **Regression Guarding**: Provide a runnable command-line interface to catch quality degradations before merging code changes.

### Non-Goals
*   **No Unnecessary LLM Judges**: Do not use LLMs to score properties that can be calculated deterministically (such as tool counts or citation ID presence).
*   **No Production REST API / GUI**: Phase 9 does not implement Streamlit UI elements for evaluations, web-based dashboards, or continuous online monitoring of production endpoints.
*   **No Multi-Agent Competition**: We evaluate a single instance of a bounded state graph, not self-modifying prompts or multi-agent negotiations.

---

## 4. Evaluation Levels

OpsGraph AI is evaluated at four distinct levels:

```
+-----------------------------------------------------------------+
| Level 4: Scenario Benchmark (Suite-wide success, costs, budgets)|
+-----------------------------------------------------------------+
                               ↓
+-----------------------------------------------------------------+
| Level 3: Graph Run Evaluation (Terminal states, budget adherence|
+-----------------------------------------------------------------+
                               ↓
+-----------------------------------------------------------------+
| Level 2: Node Evaluation (Hypothesis quality, Critic decisions) |
+-----------------------------------------------------------------+
                               ↓
+-----------------------------------------------------------------+
| Level 1: Component Evaluation (Retrieval precision, assembler)  |
+-----------------------------------------------------------------+
```

*   **Level 1 — Component Evaluation**: Isolated unit metrics evaluating individual building blocks. Focuses on retrieval precision (semantic vs. lexical), prompt template compilation correctness, and citation schema validation.
*   **Level 2 — Node Evaluation**: Evaluates outputs of specific graph steps. Focuses on LLM outputs (e.g., if hypothesis generation produces parsable JSON, if tool selection requests correct parameters).
*   **Level 3 — Graph Run Evaluation**: Evaluates a single end-to-end execution trace of the LangGraph engine for an incident. Focuses on terminal state correctness, iteration budgets, and error boundary propagation.
*   **Level 4 — Scenario Benchmark**: Aggregated performance metrics compiled across the entire SRE incident suite (e.g., mean iterations, budget exhaustion rates, overall resolution success rate).

---

## 5. Golden Scenario Contract

To decouple dataset split metadata from scenario resolution policies and prevent implicit signals, the golden scenario schema is designed as follows:

```json
{
  "schema_version": "1.0",
  "scenario_id": "SCN-DB-POOL-001",
  "incident_id": "INC-0042",
  "split": "dev",
  "labels": {
    "affected_service": "checkout-service",
    "fault_category": "database_connection_pool",
    "root_cause_code": "DB_POOL_MAX_CONNECTIONS_REGRESSION",
    "root_cause_summary": "Invalid connection pool configuration introduced during deployment."
  },
  "ambiguity": "unambiguous",
  "expected_terminal_outcome": "finalize_rca",
  "acceptable_terminal_outcomes": ["finalize_rca"],
  "required_evidence_ids": [
    "DEPLOY-EV-0042-001",
    "METRIC-EV-0042-001",
    "LOG-EV-0042-001"
  ],
  "expected_tools": [
    "deployment_event_search",
    "metric_window_analysis",
    "log_pattern_search"
  ],
  "acceptable_remediation_codes": [
    "ROLLBACK_POOL_CONFIG",
    "RESTORE_VALIDATED_POOL_LIMITS",
    "VERIFY_CONNECTION_WAIT",
    "VERIFY_HTTP_ERROR_RATE"
  ],
  "forbidden_unsupported_causes": [
    "REDIS_OUTAGE",
    "DNS_FAILURE"
  ]
}
```

### Key Contract Mappings
1.  **Dataset Splits**: Distinct values for `split`: `dev`, `validation`, and `test`.
2.  **Ambiguity Level**: Explicitly captured via `ambiguity`: `unambiguous` (clear causal chain), `partially_ambiguous` (some missing telemetry, may require exploration), or `irreducibly_ambiguous` (contradictory logs or missing sources, must trigger human review).
3.  **Expected Terminal Outcome**: Mapped via `expected_terminal_outcome` and `acceptable_terminal_outcomes` (representing one or more acceptable terminal states: `finalize_rca`, `human_review`, or `failure`).
4.  **Evidence IDs**: Explicitly defined required evidence IDs. An empty list is no longer an implicit signal for human review; the terminal state must be explicitly set to `human_review`.
5.  **Multi-Answer Root Cause Support**:
    *   `labels.root_cause_code`: The canonical root cause.
    *   `acceptable_root_cause_codes` (optional list): Semantically equivalent codes.
    *   `forbidden_unsupported_causes`: Root causes that must not be proposed.

---

## 6. Metric Definitions

Every metric enforces strict input checks, duplicate handling rules, and mathematical safety.

### A. Evidence Retrieval and Citations (Deterministic)
*   **Evidence ID Recall**:
    *   *Definition*: The proportion of required scenario evidence items successfully collected in `evidence_list`.
    *   *Formula*: $|collected \cap required| / |required|$
    *   *Empty Denominator Policy*: If `required_evidence_ids` is empty, this metric returns `N/A` (omitted from aggregate averaging).
    *   *Duplicate Handling*: Evidence items are deduplicated by `evidence_id` prior to comparison.
    *   *Aggregation Method*: Macro average across applicable scenarios.
*   **Citation Validity**:
    *   *Definition*: The proportion of cited evidence IDs in the RCA response that are actually present in the graph's `evidence_list`.
    *   *Formula*: $|cited\_references \cap evidence\_list\_ids| / |cited\_references|$
    *   *Empty Denominator Policy*: If `cited_references` is empty, returns `1.0` if no required evidence was defined, otherwise `0.0`.
    *   *Duplicate Handling*: Cited references are deduplicated prior to scoring.
    *   *Aggregation Method*: Macro average.
*   **Citation Relevance (Semantic)**:
    *   *Definition*: Measures whether the cited evidence actually supports or contradicts the associated claim. (Requires semantic verification via sentence embedding or optional LLM judge).

### B. RCA Accuracy (Deterministic & Semantic)
*   **Service Localization Accuracy**:
    *   *Definition*: Exact string match on the target affected service.
    *   *Formula*: `1` if `current_rca.primary_hypothesis.affected_service == labels.affected_service` else `0`.
    *   *Empty Denominator Policy*: N/A (always has a service value).
    *   *Aggregation Method*: Simple Accuracy.
*   **Remediation Relevance**:
    *   *Definition*: Evaluates if the recommended actions correspond to acceptable remediation codes.
    *   *Mapping Strategy*: Since generated actions (`recommended_actions`) are natural language objects with type enums, we map the enum `type` (`ActionType`) or match action description substrings to the expected `acceptable_remediation_codes` list.
    *   *Range*: `[0.0, 1.0]`.

### C. Execution Efficiency (Deterministic)
*   **Tool Execution Precision**:
    *   *Definition*: Evaluates tool selection efficiency without penalizing alternative valid paths.
    *   *Scoring Rules*:
        *   Golden scenario contract specifies `required_tools`, `acceptable_tools`, and `forbidden_tools`.
        *   If any tool in `forbidden_tools` is called $\rightarrow$ Precision is penalized.
        *   If all `required_tools` are called and no forbidden tools are called $\rightarrow$ Precision is `1.0`.
        *   Additional allowed tools in `acceptable_tools` do not penalize the score. Unlisted tools are classed as `unnecessary_tools` and introduce a small penalty.
*   **Iteration Efficiency**:
    *   *Definition*: Measures efficiency of graph cycles conditional on outcome correctness.
    *   *Formula*: If terminal state and RCA correctness score $\ge 0.80$, score is $1.0 - (iteration\_count - 1) / INVESTIGATION\_MAX\_ITERATIONS$, otherwise `0.0`.
    *   *Rationale*: Prevents incorrect one-iteration failures from getting high efficiency scores.

### D. Decision and Calibration (Deterministic)
*   **Critic Accuracy**:
    *   *Definition*: Evaluates if the critic decision correctly matches required evidence completeness.
    *   *Scoring*:
        *   If decision is `ACCEPT` but required evidence is missing $\rightarrow$ Score = `0` (False Acceptance).
        *   If decision is `ACCEPT` and required evidence is present $\rightarrow$ Score = `1` (Correct Acceptance).
        *   If decision is `CONTINUE_INVESTIGATION` and required evidence is missing $\rightarrow$ Score = `1` (Correct Continuation).
        *   If decision is `CONTINUE_INVESTIGATION` and required evidence is already present $\rightarrow$ Score = `0` (Unnecessary Continuation).

---

## 7. Metric Applicability Matrix by Evaluation Mode

Different evaluation modes support different metric categories.

| Metric | Metric-Only Mode | Mock-Graph Mode | Offline-Component Mode | Live Mode |
|---|---|---|---|---|
| Citation Validity | Yes | Yes | No | Yes |
| Evidence Recall | Yes | Yes | Yes | Yes |
| Service Localization | Yes | Yes | No | Yes |
| Critic Accuracy | Yes | Yes | No | Yes |
| Iteration Efficiency | Yes | Yes | No | Yes |
| Tool Precision | Yes | Yes | No | Yes |

*   **Metric-Only Mode**: Evaluates pre-stored execution traces and prediction JSONs.
*   **Mock-Graph Mode**: Executes the LangGraph orchestration engine using deterministic canned Gateway responses.
*   **Offline-Component Mode**: Evaluates standalone retrieval, document chunking, and validation classes in isolation.
*   **Live Mode**: Executes the graph against live provider backends (Groq/Gemini).

---

## 8. Execution Trace Contract

The runner records a structured execution trace object (`EvaluationTrace`) for auditing:

```python
class EvaluationTrace(TypedDict):
    scenario_id: str
    investigation_id: str
    node_sequence: list[str]                # Order of traversed nodes
    node_timings: dict[str, float]          # Start/end latency per node
    iteration_count: int
    tool_calls: list[dict[str, Any]]        # Sanitized parameters & called tool names
    evidence_ids: list[str]                 # Unique IDs of collected evidence items
    critic_decisions: list[str]             # List of decision outputs ("ACCEPT", etc.)
    critic_confidences: list[float]         # Progression of confidence scores
    context_rebuild_count: int
    provider_used: str                      # Final Gateway provider
    fallback_occurrence: bool               # True if fallback triggered
    termination_reason: str | None
    final_terminal_type: str                # "finalize_rca", "human_review", "failure"
    total_latency_ms: float
```

---

## 9. Baseline Experiments Matrix

Evaluation runs must keep providers constant to evaluate graph architecture differences.

| Experiment ID | System Architecture | Provider | Model | Test Scenarios | Key Evaluated Metrics |
|---|---|---|---|---|---|
| **E-BASE-A** | One-Pass RAG-only | Groq | `llama-3.3-70b-versatile` | Dev Suite | Localization, Citation Validity |
| **E-BASE-B** | Retrieval-augmented one-pass | Groq | `llama-3.3-70b-versatile` | Dev Suite | Localization, Recall |
| **E-SYS-C** | Phase 8 Stateful Graph | Groq | `llama-3.3-70b-versatile` | Dev Suite | Recall, Tool Precision, Latency |

---

## 10. Regression Comparison Rules

To prevent comparing aggregate scores blindly when scenario sets shift, the comparison runner applies these rules:
1.  **Strict Caching**: Baseline runs are cached under a unique ID.
2.  **Paired Comparisons**: Scenario metrics are compared pairwise (e.g. SCN-DB-POOL-001 in Candidate vs SCN-DB-POOL-001 in Baseline). Aggregate differences are only reported on the intersection of successfully run scenarios.
3.  **Variance Buffer**: For live hosted provider runs, a $\pm 5\%$ threshold variance buffer is applied to semantic or confidence scores to prevent blocking on provider non-determinism.

---

## 11. Reproducibility & Secret Exposure Controls

### Reproducibility Configuration Snapshotting
The framework serializes a snapshot of the runtime configuration:
*   Requested temperature, provider/model settings, prompt versions, graph budgets, retrieval parameters, embedding settings, Git commit hash, and evaluation runner version.
*   *Note*: Temperature `0.0` does not guarantee deterministic output from hosted providers.

### Secret Exposure Scanning
The runner implements deterministic credential scans on execution traces, manifests, and failure logs:
1.  **Value Scanning**: Scans for exact values of configured environment keys (e.g. `GROQ_API_KEY`, `GEMINI_API_KEY`).
2.  **Pattern Scanning**: Regex matches for authentication headers (`Bearer ...`), Portkey credentials, or classic token structures.
3.  **Sanitization Check**: Verifies that exception handlers successfully stripped raw tokens from `FailureTerminalState` error messages.

---

## 12. Quality & Regression Gates

Initial Phase 9 release gates focus on implementation correctness rather than arbitrary quality thresholds.

### Hard Gates (Block Release)
*   **Schema Validity**: `100%` of output files must comply with Pydantic expectations.
*   **Budget Compliance**: `0` runs may violate configured iteration/tool budgets.
*   **Secret Safety**: `0` scanned credentials or tokens may appear in results.
*   **Invalid Citation Rate**: `0%` of cited IDs may be completely missing from telemetry database options.

### Soft / Informational Metrics (Non-Blocking)
*   Root Cause Accuracy.
*   Evidence Recall.
*   Tool Selection Precision.
*   *Threshold Introduction Policy*: Hard quality thresholds (e.g., Recall $\ge 85\%$) will only be set after executing Baseline Experiments on at least 15 development benchmark scenarios to establish statistical variance.

---

## 13. Proposed File Structure

To prevent code fragmentation, the initial framework is consolidated into four cohesive modules:

```text
evals/
├── __init__.py
├── schemas.py             # EvaluationTrace and GoldenCase Pydantic structures
├── metrics.py             # Deterministic and semantic scoring functions
├── runner.py              # Scenario loader and execution loops
└── reporting.py           # Markdown aggregator and regression comparator
```

---

## 14. CI Strategy

*   **Current State**: CI integration is planned but not currently implemented (no GitHub actions exist).
*   **PR Staging Plan**:
    *   *PR Verification*: Runs only fast deterministic metric unit tests and smoke scenarios (fully offline-safe, zero provider keys required).
    *   *Main Branch Merge*: Runs the full offline benchmark suite.
    *   *Scheduled Runs*: Nightly live provider evaluation (requires hosted credentials; run within a secure, isolated runner).

---

## 15. Risks and Mitigations

*   **Benchmark Overfitting**:
    *   *Mitigation*: Partition scenarios into distinct `dev`, `validation`, and `test` splits. Frozen test scenarios are run only before major releases.
*   **Answer Leakage**:
    *   *Mitigation*: Review golden files to ensure telemetry logs do not explicitly state the root cause code, and verify tool outputs do not print raw answers.
*   **Stale Golden Labels**:
    *   *Mitigation*: Unit tests validate that all scenario datasets conform to the active telemetry and context builder schemas.
*   **Composite Score Bias**:
    *   *Mitigation*: Report metrics independently rather than compiling a single arbitrary weighted score.

---

## 16. Implementation Milestones

1.  **Milestone 1 — Evaluation Contracts**: Define evaluation state schemas and trace models.
2.  **Milestone 2 — Deterministic Metrics**: Implement citation, evidence coverage, and budget trackers.
3.  **Milestone 3 — Structured RCA Metrics**: Implement service localization and remediation matching.
4.  **Milestone 4 — Tool & Critic Metrics**: Build path-independent tool precision and critic accuracy evaluators.
5.  **Milestone 5 — Offline Runner**: Implement the execution loop supporting `mock-graph` and `offline-component` modes.
6.  **Milestone 6 — Aggregation & Reporting**: Write markdown results aggregator and paired regression rules.
7.  **Milestone 7 — Baseline Experiments**: Run comparative baselines and write `DATA/scenarios/definitions/` updates.
