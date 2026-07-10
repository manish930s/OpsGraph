# OpsGraph AI — Phase 9 Evaluation, Benchmarking, and Quality Framework Plan

**Release Status:** PLANNING COMPLETE — IMPLEMENTATION NOT STARTED  
**Phase:** Phase 9 — Evaluation, Benchmarking, and Investigation Quality Framework  
**Execution Date:** 2026-07-10  
**Python Runtime:** CPython 3.14.0 (Windows)  

---

## 1. Executive Summary

Phase 9 establishes a rigorous, offline-safe evaluation and benchmarking framework for OpsGraph AI. Having successfully implemented the stateful, bounded investigation graph in Phase 8, we must systematically measure the quality of generated root-cause analyses (RCAs), the accuracy and precision of telemetry tool invocations, the correctness of critic decisions, and overall execution safety.

This plan details:
*   **Evaluation Levels**: Ranging from component-level metrics (retrieval, prompt templates) to full-system scenario benchmarks.
*   **Deterministic Metric Library**: Heavy prioritization of fast, rule-based python evaluators (checking citations, tool calls, and service categories) over costly, non-deterministic LLM-as-judge runs.
*   **Golden Scenario Schema**: Verification against verified, synthetically-generated incidents like `SCN-DB-POOL-001`.
*   **Evaluation Runner CLI**: An offline-safe command-line execution engine supporting mock and live modes.
*   **Safety Gates**: Automated CI regression criteria enforcing budget limits, citation validity, and zero credential leaks.

---

## 2. Current Evaluation Assets

An audit of the repository shows the following evaluation-ready files and datasets are already implemented and available:

1.  **Scenario Definitions Directory** (`data/scenarios/definitions/`):
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
*   **Calibrated Escalation**: Ensure that the critic correct routes to `human_review` under ambiguous or incomplete data and terminates with `failure` under parameter mismatches.
*   **Zero Leakage**: Enforce safety limits to ensure that API credentials never appear in diagnostic logs or error state outputs.
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

The evaluation runner loads targets using the existing `GoldenCase` Pydantic model (`app/schemas/rca.py`):

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

### Mandated and Optional Fields
*   **Mandatory**: `scenario_id`, `incident_id`, `split`, `labels`, `required_evidence_ids`.
*   **Optional**: `expected_tools`, `acceptable_remediation_codes`, `forbidden_unsupported_causes`.
*   **Ambiguous Incidents Representation**: Handled by setting `split="test"` and including multiple items in `acceptable_remediation_codes` or leaving `required_evidence_ids` empty to force a correct `human_review` escalation.

---

## 6. Metric Definitions

### A. Evidence Retrieval and Citations (Deterministic)
*   **Evidence ID Recall**:
    *   *Definition*: The proportion of required scenario evidence items successfully collected in `evidence_list`.
    *   *Required Inputs*: Graph final state `evidence_list`, Golden `required_evidence_ids`.
    *   *Formula*: $|collected \cap required| / |required|$
    *   *Range*: `[0.0, 1.0]` (where 1.0 means all required evidence was gathered).
*   **Citation Precision**:
    *   *Definition*: The proportion of cited evidence IDs in `current_rca` that are actually present in the graph's `evidence_list`.
    *   *Required Inputs*: `RCADecisionResponse` supporting/contradicting references, state `evidence_list`.
    *   *Formula*: $|cited\_references \cap evidence\_list| / |cited\_references|$
    *   *Range*: `[0.0, 1.0]` (where 1.0 means zero hallucinated citations).

### B. RCA Accuracy (Deterministic & Semantic)
*   **Service Localization Accuracy**:
    *   *Definition*: Binary indicator matching if the generated RCA correctly identifies the root service.
    *   *Required Inputs*: State `current_rca`, Golden `labels.affected_service`.
    *   *Range*: `{0, 1}` (where 1 represents an exact match).
*   **Remediation Relevance**:
    *   *Definition*: Match rate of recommended actions to acceptable remediation codes.
    *   *Required Inputs*: State `current_rca.recommended_actions`, Golden `acceptable_remediation_codes`.
    *   *Range*: `[0.0, 1.0]`.
*   **Root-Cause Semantic Similarity** (LLM Judge / Vector Similarity):
    *   *Definition*: Similarity score between the model's generated `summary` and the golden `root_cause_summary`.
    *   *Required Inputs*: State `current_rca.summary`, Golden `labels.root_cause_summary`.
    *   *Range*: `[0.0, 1.0]` (calculated using Cosine Similarity over local embeddings or structured LLM scoring).

### C. Execution Efficiency (Deterministic)
*   **Tool Execution Precision**:
    *   *Definition*: Ratio of expected diagnostic tool invocations to total tool invocations.
    *   *Required Inputs*: Trace history of tool calls, Golden `expected_tools`.
    *   *Formula*: $|called \cap expected| / |called|$
    *   *Range*: `[0.0, 1.0]`.
*   **Iteration Efficiency**:
    *   *Definition*: Efficiency of graph cycle usage.
    *   *Required Inputs*: State `iteration_count`.
    *   *Formula*: $1.0 - (iteration\_count - 1) / INVESTIGATION\_MAX\_ITERATIONS$ (normalized).
    *   *Range*: `[0.0, 1.0]`.

### D. Decision and Calibration (Deterministic)
*   **Critic Accuracy**:
    *   *Definition*: Evaluates if the critic correctly accepted, rejected, or continued based on evidence presence.
    *   *Required Inputs*: State `critic_decision.decision`, Golden `required_evidence_ids`.
    *   *Scoring*:
        *   If `ACCEPT` is returned but required evidence is missing $\rightarrow$ Score = `0` (False Acceptance).
        *   If `ACCEPT` is returned and all required evidence is present $\rightarrow$ Score = `1` (Correct Acceptance).

---

## 7. Node-Level Evaluation Mapping

| Node Name | Key Metric | Target / Range | Evaluator Type |
|---|---|---|---|
| `initialize` | Setup status | Binary `{0,1}` | Deterministic |
| `build_context` | Token count compliance | Within budget (< 4000 words) | Deterministic |
| `generate_hypothesis` | Schema compliance | Valid JSON structure | Deterministic |
| `evaluate_hypothesis` | Confidence calibration | Correlation with evidence | Deterministic |
| `identify_evidence_gap` | Gap detection accuracy | Matches missing required codes | Deterministic |
| `select_tool` | Parameter schemas validity | Valid against registry models | Deterministic |
| `execute_tool` | Execution success rate | Mapped error boundaries | Deterministic |
| `validate_evidence` | Deduplication accuracy | Unique ID sets preserved | Deterministic |
| `rebuild_context` | Context latency | `< 800ms` | Deterministic |

---

## 8. SRE Failure & Refusal Metrics

To prevent collapsing all exit outcomes, terminal states are scored into fine-grained SRE metrics:

1.  **Expected Failure Rate**: Correctly aborted runs on garbage or invalid schema inputs (e.g. invalid topologies). Mapped via `FailureTerminalState`.
2.  **Unsafe Successful Completion Rate (Critical Failure)**: Occurs when a run exits with a successful `"RCA accepted by critic"` code but contains hallucinated, invalid, or missing required evidence. Must be 0%.
3.  **Controlled Human Escalation Rate**: Ratio of runs exiting via `human_review` because of budget exhaustion or critic request. This is a valid, safe SRE outcome.
4.  **Gateway Exhaustion Rate**: Runs ending in failure due to provider timeouts or rate-limiting.

---

## 9. Evaluation Runner Architecture

The framework implements a headless execution runner (`evals/runner.py`) containing the following stages:

```
[Scenario List]
      ↓
[Scenario Loader] (reads definition & raw telemetry)
      ↓
[Graph Execution Loop] (mocks or executes LLMGateway requests)
      ↓
[Trace & Metrics Collector] (collects states, counts, and timings)
      ↓
[Deterministic Evaluators] (scores citations, schemas, and budgets)
      ↓
[Output Reporter] (writes JSONL and Markdown results)
```

### CLI Command Proposals
The runner is invoked via command line parameters to isolate runs:

```powershell
# Run a single scenario
python -m evals.run --scenario SCN-DB-POOL-001

# Run a dev suite split (fully offline-safe)
python -m evals.run --suite dev --provider mock

# Run live provider tests (opt-in)
python -m evals.run --suite benchmark --provider groq
```

---

## 10. Output Artifacts

Every benchmark run produces a unique directory under `evals/results/<run_id>/`:

*   **`run_manifest.json`**: Captures metadata for reproducibility:
    ```json
    {
      "run_id": "run_20260710_120000",
      "timestamp": "2026-07-10T12:00:00Z",
      "git_commit": "eef9690f30dc0037dcbafbb190a018c25d6f4d0c",
      "generation_model": "llama-3.3-70b-versatile",
      "embedding_model": "gemini-embedding-2-preview",
      "max_iterations": 3,
      "max_tool_calls": 6
    }
    ```
*   **`scenario_results.jsonl`**: Individual scenario execution metrics.
*   **`aggregate_metrics.json`**: Aggregated averages of precision, recall, latencies, and budget usage.
*   **`report.md`**: Human-readable markdown summary detailing regressions.

---

## 11. Reproducibility Controls

To combat provider non-determinism, the runner applies the following execution constraints:
1.  **Strict Temperature**: Hardcoded to `0.0` for all evaluator or model calls.
2.  **Configuration Snapping**: Serializes active `app/config.py` environment settings into the run manifest.
3.  **Stable Seeds**: Mocks Scenario random generator seed values before running tools or generating telemetry.

---

## 12. Quality & Regression Gates

The project establishes a clear release criteria boundary:

| Metric Group | Metric Name | Gate Condition | Release Policy |
|---|---|---|---|
| **Hard Gates** | Citation Validity | `100%` | Block release on failure |
| **Hard Gates** | Schema Validity | `100%` | Block release on failure |
| **Hard Gates** | Budget Compliance | `100%` | Block release on failure |
| **Hard Gates** | Secret Exposure | `0 leaks` | Block release on failure |
| **Soft Quality** | Root Cause Accuracy | $\ge 90\%$ | Warn / Review required |
| **Soft Quality** | Evidence Recall | $\ge 85\%$ | Warn / Review required |
| **Soft Quality** | Tool Precision | $\ge 80\%$ | Warn / Review required |

---

## 13. Proposed File Structure

Following repository conventions, Phase 9 will implement the following lightweight directory tree:

```text
evals/
├── __init__.py
├── runner.py              # CLI scenario executor
├── schemas.py             # Evaluation state & report structures
├── metrics/
│   ├── __init__.py
│   ├── citations.py       # Citation precision & recall
│   ├── evidence.py        # Evidence ID matching & category validations
│   ├── rca.py             # Service localization & remediation score
│   └── efficiency.py      # Budget utilization & latency trackers
├── datasets/
│   └── loader.py          # Scenario Repository loader wrappers
└── reporting/
    ├── aggregator.py      # Aggregates scores across runs
    └── markdown.py        # Markdown report generator

tests/
└── unit/
    ├── test_eval_metrics.py    # Unit tests for scoring logic
    └── test_eval_runner.py     # Unit tests for runner flows
```

---

## 14. Dependency Decision

*   **Existing Dependencies Reused**: `pydantic`, `pandas`, `pytest`.
*   **Ragas / DeepEval Decision**: **Do Not Adopt**. Ragas introduces heavy external dependencies, requires internet connectivity, and has installation issues under Python 3.14 on Windows.
*   **Recommendation**: Implement a custom, lightweight, deterministic metric library. Custom python scoring ensures zero overhead, 100% offline predictability, fast execution, and strict OS/runtime compatibility.

---

## 15. Cost and Performance Controls

*   **Offline Mocking by Default**: All evaluations run against offline repository mocks without calling hosted API endpoints.
*   **Max Live Scenarios Cap**: Live evaluation runs are capped at `10` incidents max to prevent runaway token costs.
*   **No Parallelism Overload**: Concurrent evaluation requests are executed sequentially or in small throttled batches to satisfy Groq/Gemini TPM rate limits.

---

## 16. Risks and Mitigations

*   **Benchmark Overfitting**:
    *   *Risk*: Prompt templates or routing rules are modified to pass the database pool scenario specifically, losing generalization.
    *   *Mitigation*: Introduce diverse scenario categories (e.g. latency degradation, dependency failures) and partition splits (`dev` vs `test`).
*   **Hosted Provider Non-Determinism**:
    *   *Risk*: Model API updates alter responses at temperature `0.0`.
    *   *Mitigation*: Maintain regression gates with a slight accuracy tolerance margin while keeping schema and citation checks at `100%`.

---

## 17. Implementation Milestones

1.  **Milestone 1 — Evaluation Schemas**: Define scenario results and runner settings Pydantic models.
2.  **Milestone 2 — Deterministic Metrics**: Implement citation, evidence coverage, and budget efficiency scorers.
3.  **Milestone 3 — Semantic Scoring**: Implement service localization and remediation matching.
4.  **Milestone 4 — Scenario Runner**: Write `runner.py` with arguments and mock execution modes.
5.  **Milestone 5 — Aggregation & Reporting**: Write markdown and JSON results serialization.
6.  **Milestone 6 — Integration Tests**: Verify the runner using pytest.
