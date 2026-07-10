# OpsGraph AI — Phase 9 Evaluation, Benchmarking, and Quality Framework Plan

**Release Status:** PLANNING COMPLETE — IMPLEMENTATION NOT STARTED  
**Phase:** Phase 9 — Evaluation, Benchmarking, and Investigation Quality Framework  
**Execution Date:** 2026-07-10  
**Python Runtime:** CPython 3.14.0 (Windows)  

---

## 1. Executive Summary

Phase 9 establishes a rigorous, offline-safe evaluation and benchmarking framework for OpsGraph AI. Having successfully implemented the stateful, bounded investigation graph in Phase 8, we must systematically measure the quality of generated root-cause analyses (RCAs), the accuracy and precision of telemetry tool invocations, the correctness of critic decisions, and overall execution safety.

This corrected plan locks the exact implementation contracts for all evaluation metrics, dataset splits, terminal outcome validations, baseline execution matrices, trace schemas, and quality regression gates. It ensures that subsequent implementation can proceed milestone by milestone without changes to metric definitions or evaluation semantics.

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

## 6. Complete Metric Contracts Table

The following table details all metrics implemented in Phase 9. No composite single score is computed; metrics are reported as separate dimensions.

| Metric Name | Purpose | Exact Required Inputs | Exact Formula / Decision Rule | Range | Empty-Input Policy | Duplicate Policy | Applicability Modes | Scenario Applicability Conditions | Aggregation Method | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| **Evidence ID Recall** | Measure completeness of collected evidence | final state `evidence_list`, Golden `required_evidence_ids` | $|collected\_ids \cap required\_ids| / |required\_ids|$ | `[0.0, 1.0]` | Returns `N/A` if required set is empty | Deduplicated by ID | All modes | Always applicable | Macro Average | Informational |
| **Citation Validity** | Verify cited evidence exists in graph state | `current_rca` citation IDs, state `evidence_list` | $|cited \cap state\_ids| / |cited|$ | `[0.0, 1.0]` | Returns `1.0` if both cited and required are empty, else `0.0` | Deduplicated by ID | `metric-only`, `mock-graph`, `live` | Requires `current_rca` | Macro Average | **Release-Blocking** |
| **Service Localization Accuracy** | Verify root service is correct | `current_rca` primary hypothesis, Golden `labels.affected_service` | `1.0` if `primary_hypothesis.affected_service == labels.affected_service` else `0.0` | `{0.0, 1.0}` | `0.0` if hypothesis is empty | N/A | `metric-only`, `mock-graph`, `live` | Requires `current_rca` | Simple Accuracy | Informational |
| **Fault Category Accuracy** | Verify root cause category is correct | `current_rca` primary hypothesis, Golden `labels.fault_category` | `1.0` if matches Golden category else `0.0` (uses deterministic mapping table if available, else deferred) | `{0.0, 1.0}` | `0.0` if hypothesis is empty | N/A | `metric-only`, `mock-graph`, `live` | Requires `current_rca` | Simple Accuracy | Informational |
| **Root Cause Match** | Verify specific cause code matches | `current_rca` primary hypothesis, Golden `labels.root_cause_code` | `1.0` if code matches canonical or acceptable list else `0.0` (deferred if generated output does not support code) | `{0.0, 1.0}` | `0.0` if hypothesis is empty | N/A | `metric-only`, `mock-graph`, `live` | Requires `current_rca` | Simple Accuracy | Informational |
| **Forbidden Cause Violation** | Verify no forbidden causes were proposed | `current_rca` primary hypothesis, Golden `forbidden_unsupported_causes` | `0.0` if `cause` in `forbidden_unsupported_causes` else `1.0` | `{0.0, 1.0}` | `1.0` if empty | N/A | `metric-only`, `mock-graph`, `live` | Requires `current_rca` | Simple Accuracy | Informational |
| **Terminal Outcome Correctness** | Verify graph exited in expected state | final terminal state name, Golden `acceptable_terminal_outcomes` | `1.0` if state in `acceptable_terminal_outcomes` else `0.0` | `{0.0, 1.0}` | `0.0` if empty | N/A | `mock-graph`, `live` | Always applicable | Simple Accuracy | Informational |
| **Evidence Sufficiency Decision Accuracy** | Verify critic continuation vs acceptance decisions | critic `decision`, Golden `required_evidence_ids`, state `evidence_list` | `0.0` if `decision == ACCEPT` but required evidence is missing, else `1.0` | `{0.0, 1.0}` | `0.0` if empty | N/A | `metric-only`, `mock-graph`, `live` | Requires critic decision | Macro Average | Informational |
| **RCA Acceptance Correctness** | Verify critic did not accept incorrect RCA | critic `decision`, `current_rca` correctness variables | `1.0` if `decision != ACCEPT` or (localization accuracy == 1.0 and category accuracy == 1.0) else `0.0` | `{0.0, 1.0}` | `0.0` if empty | N/A | `metric-only`, `mock-graph`, `live` | Requires critic decision | Macro Average | Informational |
| **Escalation Decision Correctness** | Verify human escalation was appropriate | critic `decision`, expected outcomes, ambiguity, budget state | `1.0` if `decision == HUMAN_REVIEW` matches expected outcomes or budget is exhausted, else `0.0` | `{0.0, 1.0}` | `0.0` if empty | N/A | `metric-only`, `mock-graph`, `live` | Requires critic decision | Macro Average | Informational |
| **Tool Requirement Coverage** | Verify all required tools were executed | trace tool calls, Golden `expected_tools` / `required_tools` | $|called \cap required| / |required|$ | `1.0` if required is empty, else `0.0` | Distinct tools checked | `mock-graph`, `live` | Always applicable | Macro Average | Informational |
| **Forbidden Tool Violation** | Verify no forbidden tools were executed | trace tool calls, Golden `forbidden_tools` | `0.0` if any called tool in `forbidden_tools` else `1.0` | `{0.0, 1.0}` | `1.0` if empty | Distinct tools checked | `mock-graph`, `live` | Always applicable | Simple Accuracy | Informational |
| **Unnecessary Tool Count** | Count of called tools outside required/acceptable | trace tool calls, Golden expected/acceptable tools | total count of unlisted tools called | Integer $\ge 0$ | `0` if empty | All calls counted | `mock-graph`, `live` | Always applicable | Sum / Mean | Informational |
| **Iteration Budget Utilization** | Proportion of iteration budget consumed | state `iteration_count`, `INVESTIGATION_MAX_ITERATIONS` | `iteration_count / max_iterations` | `[0.0, 1.0]` | `1.0` if missing | N/A | `mock-graph`, `live` | Always applicable | Mean | Informational |
| **Tool Budget Utilization** | Proportion of tool-call budget consumed | state `tool_call_count`, `INVESTIGATION_MAX_TOOL_CALLS` | `tool_call_count / max_tool_calls` | `[0.0, 1.0]` | `1.0` if missing | N/A | `mock-graph`, `live` | Always applicable | Mean | Informational |
| **Context Rebuild Budget Utilization** | Proportion of context rebuild budget consumed | state `context_rebuild_count`, `INVESTIGATION_MAX_CONTEXT_REBUILDS` | `context_rebuild_count / max_rebuilds` | `[0.0, 1.0]` | `1.0` if missing | N/A | `mock-graph`, `live` | Always applicable | Mean | Informational |
| **Budget Compliance** | Verify no budgets were exceeded | iteration count, tool count, rebuild count | `1.0` if all values $\le$ budgets, else `0.0` | `{0.0, 1.0}` | `0.0` if missing | N/A | `mock-graph`, `live` | Always applicable | Simple Accuracy | **Release-Blocking** |
| **Known Secret Leakage Detection** | Verify no active credentials leak in logs | captured traces, results manifests, environment variables | `0.0` if any known credential/header matches regex, else `1.0` | `{0.0, 1.0}` | `1.0` if empty | N/A | All modes | Always applicable | Simple Accuracy | **Release-Blocking** |
| **Execution Latency** | Measure execution time | trace durations | total duration in milliseconds | Float $\ge 0.0$ | `0.0` if missing | N/A | `mock-graph`, `live` | Always applicable | Mean / Median | Informational |

---

### Citation Hard-Gate and Universe Definition
*   **Citation ID Validity Hard Gate**: Enforces that 100% of cited evidence IDs in `current_rca` correspond to items that exist in the active `evidence_list` at the time of finalization.
*   **Authoritative Universe**: Valid IDs must originate strictly from the following structured sources loaded into the graph's `evidence_list`:
    *   *Telemetry Evidence* (metrics and logs generated or processed)
    *   *Deployment Evidence* (deployment events checked)
    *   *Topology Evidence* (service relations verified)
    *   *Knowledge Retrieval Evidence* (derived from hybrid lookup vectors)
    *   *Runbook Evidence* (derived from post-mortem/runbook text matches)
*   **Separation**:
    *   *Citation ID Validity* (deterministic existence of IDs) is **release-blocking**.
    *   *Citation Relevance* (evaluating if the cited evidence actually supports the claim text) is **informational** and handled via semantic similarity.
    *   *Required Evidence Coverage* (evaluating if the graph gathered the required subset) is **informational**.

---

### Remediation Evaluation Policy
Because generated actions (`recommended_actions`) contain natural language instructions while the golden contract defines string keys (e.g. `ROLLBACK_POOL_CONFIG`), a direct deterministic comparison of strings is not possible.
*   **Remediation Relevance Metric**: Classified as **deferred / experimental** in the initial implementation.
*   **Future Normalization**: Substring matching or ad-hoc rule evaluation will not be implemented. Instead, Milestone 12 will test a structured embedding similarity mapping between action enums or descriptions.

---

## 7. Metric Applicability Matrix by Evaluation Mode

The applicability of each metric is bounded by the capabilities of each execution mode.

| Metric Name | Metric-Only Mode | Mock-Graph Mode | Offline-Component Mode | Live Mode |
|---|---|---|---|---|
| **Evidence ID Recall** | Yes | Yes | **Conditional** (1) | Yes |
| **Citation Validity** | Yes | Yes | No | Yes |
| **Service Localization Accuracy** | Yes | Yes | No | Yes |
| **Fault Category Accuracy** | Yes | Yes | No | Yes |
| **Root Cause Match** | Yes | Yes | No | Yes |
| **Forbidden Cause Violation** | Yes | Yes | No | Yes |
| **Terminal Outcome Correctness** | No (2) | Yes | No | Yes |
| **Evidence Sufficiency Decision Accuracy** | Yes | Yes | No | Yes |
| **RCA Acceptance Correctness** | Yes | Yes | No | Yes |
| **Escalation Decision Correctness** | Yes | Yes | No | Yes |
| **Tool Requirement Coverage** | No (2) | Yes | No | Yes |
| **Forbidden Tool Violation** | No (2) | Yes | No | Yes |
| **Unnecessary Tool Count** | No (2) | Yes | No | Yes |
| **Iteration Budget Utilization** | Yes | Yes | No | Yes |
| **Tool Budget Utilization** | Yes | Yes | No | Yes |
| **Context Rebuild Budget Utilization** | Yes | Yes | No | Yes |
| **Budget Compliance** | Yes | Yes | No | Yes |
| **Known Secret Leakage Detection** | Yes | Yes | Yes | Yes |
| **Execution Latency** | No (2) | Yes | Yes | Yes |

*   **(1) Conditional (Offline-Component)**: Only applicable to component tests (e.g., context builder retrieval methods) that directly generate intermediate evidence lists matching a golden set.
*   **(2) No (Metric-Only)**: The execution trace itself must pre-record these values to be parsed. Since metric-only mode does not execute the graph, it cannot calculate new path, tool, or latency metrics.

---

## 8. Complete Trace Source Mapping

The following table records the exact source of every field in the `EvaluationTrace` contract and maps necessary instrumentation tasks.

| Field Name | Existing State Source | Already Available | Instrumentation Required | Sanitization Required |
|---|---|---|---|---|
| `scenario_id` | `state["incident"].scenario_id` | **Yes** | No | No |
| `investigation_id` | `state["investigation_id"]` | **Yes** | No | No |
| `node_sequence` | N/A | **No** | **Yes** (Phase 9 collector wrapper must log the traversal path) | No |
| `node_timings` | N/A | **No** | **Yes** (Phase 9 wrapper must record timestamps on entry and exit) | No |
| `iteration_count` | `state["iteration_count"]` | **Yes** | No | No |
| `tool_calls` | N/A | **No** | **Yes** (Phase 9 wrapper must record selected tool name) | **Yes** (Strip auth tokens or credentials) |
| `tool_parameters` | `state["tool_selection"].parameters` | **Yes** | No | **Yes** (Strip environment variables or secret configurations) |
| `evidence_ids` | `[e.evidence_id for e in state["evidence_list"]]` | **Yes** | No | No |
| `critic_decisions` | N/A | **No** | **Yes** (Phase 9 wrapper must log decisions over cycles) | No |
| `critic_confidences` | N/A | **No** | **Yes** (Phase 9 wrapper must log critic score progression) | No |
| `context_rebuild_count` | `state["context_rebuild_count"]` | **Yes** | No | No |
| `provider_used` | `state["current_rca"].execution_metadata.final_provider` | **Yes** (via Gateway response) | No | No |
| `fallback_occurrence` | `state["current_rca"].execution_metadata.fallback_attempted` | **Yes** | No | No |
| `termination_reason` | `state["termination_reason"]` | **Yes** | No | No |
| `final_terminal_type` | Mapped via final graph exit node | **Yes** | No | No |
| `total_latency_ms` | N/A | **No** | **Yes** (Tracked by Phase 9 runner start/end timer) | No |

---

## 9. Baseline Execution Contracts

To ensure scientific validity, baseline configurations keep models and prompt templates constant.

```
Baseline A (Initial Context Single-Pass RCA)
Incident ----> Deterministic Initial Context ----> Prompt Assembly ----> LLM Gateway ----> RCA Output

Baseline B (Retrieval-Augmented Single-Pass RCA)
Incident ----> Deterministic Initial Context
                    + Hybrid Knowledge Retrieval ----> Prompt Assembly ----> LLM Gateway ----> RCA Output

System C (Bounded Investigation Graph)
Phase 8 Stateful Orchestration Loop (Iterative Tools, Critic, Context Rebuilds, Validation)
```

1.  **Baseline A — Initial Context Single-Pass RCA**:
    *   *Execution*: Incident record $\rightarrow$ deterministic initial context compilation $\rightarrow$ prompt assembly $\rightarrow$ Gateway generation $\rightarrow$ guardrail validation $\rightarrow$ final RCA output.
    *   *Boundaries*: No loops. Telemetry tools do not execute. No critic evaluations or evidence-gap detection.
2.  **Baseline B — Retrieval-Augmented Single-Pass RCA**:
    *   *Execution*: Incident record $\rightarrow$ deterministic initial context + Hybrid Knowledge retrieval (lexical/semantic vector lookup) $\rightarrow$ prompt assembly $\rightarrow$ Gateway generation $\rightarrow$ guardrail validation $\rightarrow$ final RCA output.
    *   *Boundaries*: Telemetry tools are invoked exactly once *before* generation to establish initial context. No state loop or critic feedback.
3.  **System C — Bounded Investigation Graph**:
    *   *Execution*: Full Phase 8 stateful Graph execution (nodes: `initialize`, `build_context`, `generate_hypothesis`, `evaluate_hypothesis`, `identify_evidence_gap`, `select_tool`, `execute_tool`, `validate_evidence`, `rebuild_context`, and terminal finalizers).
4.  **Constant Parameters**: Provider (`Groq`), Model (`llama-3.3-70b-versatile`), prompt family structures, embedding/retrieval parameters, and scenario incident sets must remain identical across comparisons.

---

## 10. Live Evaluation Boundedness

To prevent runaway API token costs or infinite graph runner hang issues during live evaluations, the framework enforces the following execution boundaries:

*   **Scenario Execution Cap**: Maximum of `10` live scenarios executed per command invocation.
*   **Orchestration Limits**: Fall back to Phase 8 graph hard budgets (max 3 iterations, 6 tool calls, 3 context rebuilds).
*   **Gateway Retry Limits**: LLM Gateway controls provider-level connection retries (max 3 with exponential backoff). The evaluation runner will not introduce additional nested retry loops.
*   **Timeout Boundaries**: Strict execution timeout of `30` seconds per scenario, and `300` seconds for the entire evaluation suite run.
*   **Concurrency**: All scenarios run sequentially (concurrency = 1) to respect Groq/Gemini TPM rate limits.

---

## 11. Benchmark Growth Strategy

The benchmark dataset grows in three structured stages:

1.  **Stage A — Smoke Suite**:
    *   *Target*: 3 to 5 incidents.
    *   *Purpose*: Validate runner execution path, metrics logging, output JSON formatting, and basic schemas.
2.  **Developer Benchmark (Stage B)**:
    *   *Target*: 10 to 15 incidents.
    *   *Purpose*: Evaluator debugging, baseline experiment evaluations, and metric validation.
3.  **Reviewed Benchmark (Stage C)**:
    *   *Target*: 20 to 30 incidents.
    *   *Purpose*: Compute project-wide quality indicators and establish statistical regression tolerance limits.
*   *Note*: These are engineering planning targets, not guarantees of statistical significance. The SRE incident benchmark remains completely isolated from the general Kubernetes QA dataset (`golden_dataset.json`).

---

## 12. Scenario Review Workflow & Leakage Controls

To ensure benchmark integrity and prevent models from resolving incidents through trivial leakage, scenarios must pass a strict verification flow:

### Workflow Steps
1.  Scenario specification definition.
2.  Synthetic telemetry generation.
3.  Golden labels creation.
4.  Required evidence review.
5.  Acceptable alternative path review.
6.  Contradictory observations check.
7.  Answer leakage review.
8.  Difficulty classification.
9.  Split assignment (`dev`, `validation`, `test`).
10. Frozen version assignment.

### Leakage Verification Checks
*   **No Explicit Cause in Logs**: Ensure that generated error logs do not copy-paste the exact string of the root-cause code or diagnosis.
*   **No Golden Metadata Exposure**: The scenario repository wrapper must never expose the `golden.json` file or target parameters to the runtime investigation graph.
*   **Metadata Filtering**: Runbook titles, filenames, and trace attributes must not contain the exact target codes or answers.

---

## 13. Complete Risk Register

| Risk Name | Risk Description | Mitigation Strategy |
|---|---|---|
| **Tiny Sample Size** | Aggregate percentages over 1 scenario create false confidence | Report raw counts alongside percentages; clearly mark small-sample results. |
| **Multiple Valid Paths** | Expected tool sequence mismatch penalizes correct variants | Use required, acceptable, unnecessary, and forbidden tool categories instead of static sequencing. |
| **Multiple Valid RCAs** | Text-matching penalizes semantically equivalent summaries | Prioritize structured exact-match labels (affected service); keep text evaluations secondary/experimental. |
| **Ambiguous Evidence** | Scenario telemetry legitimately leads to human review | Implement explicit ambiguity levels and acceptable terminal outcome list contracts. |
| **Synthetic Realism** | Simulated incidents are too clean or simple | Introduce telemetry noise, partial observability, and contradictory data into Stage B/C scenarios. |
| **Provider Nondeterminism** | API updates alter responses at temperature `0.0` | Capture complete configurations, use paired scenario comparisons, and avoid hard gates on semantic scores. |
| **Embedding Mismatch** | Comparing vectors from incompatible spaces | Record active embedding model name and dimension; block cross-space similarity checks. |
| **LLM Judge Bias** | Judge preference favors specific models or formats | Keep judge optional, structured, versioned, and completely non-blocking for initial releases. |
| **Generator/Judge Coupling** | Same-family models systematically favor their own outputs | Enforce provider separation (e.g. use Gemini to judge Groq) or run independent correlation audits. |
| **Cost Growth** | Scenario expansion multiplies hosted API pricing | Enforce offline-first defaults, sequential loops, sequential runs, and explicit scenario execution caps. |
| **Runtime Growth** | Long execution cycles slow down development velocity | Separate tests into fast smoke, offline benchmark, and scheduled live suites. |
| **Stale Golden Labels** | Schema changes invalidate historical expected outputs | Version scenario golden contracts and auto-validate them before execution. |
| **Scenario-Set Drift** | Candidate and baseline aggregate metrics compare different sets | Enforce paired comparison on scenario intersections; explicitly report added/removed incidents. |
| **False Precision** | A single composite score hides critical trade-offs | Report independent metric dimensions (recall, validity, budgets) separately without weights. |

---

## 14. File Structure Description

The evaluation framework is implemented as a compact package with four functional modules plus package initialization:

```text
evals/
├── __init__.py            # Package initialization
├── schemas.py             # EvaluationTrace and GoldenCase Pydantic contracts
├── metrics.py             # Deterministic metric implementations
├── runner.py              # Scenario loader and execution runner loops
└── reporting.py           # Markdown aggregator and regression comparator
```

No additional subfolders or package directories will be created until implementation complexity justifies them.

---

## 15. Locked Implementation Milestones

1.  **Milestone 1 — Evaluation Contracts**: Define evaluation state schemas and trace models.
2.  **Milestone 2 — Deterministic Metrics**: Implement citation, evidence coverage, and budget trackers.
3.  **Milestone 3 — Structured RCA Metrics**: Implement service localization and remediation matching.
4.  **Milestone 4 — Tool & Critic Metrics**: Build path-independent tool precision and critic accuracy evaluators.
5.  **Milestone 5 — Offline Runner**: Implement the execution loop supporting `mock-graph` and `offline-component` modes.
6.  **Milestone 6 — Aggregation & Reporting**: Write markdown results aggregator and paired regression rules.
7.  **Milestone 7 — Smoke Scenario Expansion**: Add 3 to 5 smoke scenarios.
8.  **Milestone 8 — Baseline Experiments**: Run Baseline A, Baseline B, and System C comparisons.
9.  **Milestone 9 — Regression Comparison**: Test the paired comparator against baseline runs.
10. **Milestone 10 — Live-mode Execution**: Implement live-mode runner wrapper with explicit caps.
11. **Milestone 11 — Optional Semantic Evaluator Experiment**: Test local embedding similarity.
12. **Milestone 12 — Documentation & Verification**: Complete final verification pass.
13. **Milestone 13 — Release Gate**: Verify release criteria and lock v0.9.0 planning.

---

## 16. Implementation Branch Strategy

The active planning branch must remain documentation-only. Once this planning document is merged into `main`, implementation will begin on a new dedicated branch:

`feature/phase-9-evaluation-framework`

The implementation will proceed milestone by milestone. After every completed milestone:
1.  Run targeted unit tests.
2.  Run the full offline test suite (`pytest`).
3.  Verify the git diff has zero code modifications outside `evals/` and `tests/`.
4.  Update the Phase 9 progress tracking documentation.
5.  Create a logical commit and push the feature branch to remote.
6.  Ensure the working tree is clean before starting the next milestone.
