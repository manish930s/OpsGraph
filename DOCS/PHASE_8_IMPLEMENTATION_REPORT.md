# OpsGraph AI — Phase 8 Bounded LangGraph Investigation Report

**Release Status:** RELEASED — v0.8.0
**Merge Commit:** eef9690f30dc0037dcbafbb190a018c25d6f4d0c
**Tag:** v0.8.0
**Phase:** Phase 8 — Bounded LangGraph Investigation Engine
**Execution Date:** 2026-07-10  
**Python Runtime:** CPython 3.14.0 (Windows)  
**Verification Status:** PASSED — 116 offline unit tests successfully passed  

---

## 1. Executive Summary

Phase 8 implements a strongly-typed, bounded, and deterministic orchestration engine for incident investigation using LangGraph. The requesting SRE lifecycle is managed as a controlled state graph rather than a generic agent loop. 

Highlights of this release include:
*   **Bounded Iterations**: Rigid limits on iterations (3), tool calls (6), context rebuilds (3), and evidence items (100) to prevent infinite loops and runaway API costs.
*   **Comprehensive Failure Coverage**: Complete try-except wrappers on every single node (including terminal nodes) converting errors to state-held failures and routing them to the `failure` node (or transitioning directly to `END` for terminal nodes).
*   **Exact Counter Semantics**: Verified tracking of iterations, tool executions, and context rebuilds, with corresponding unit tests counting invocations.
*   **Deterministic Validation Policy**: Complete rejection of invalid evidence batches, intra-batch duplicate IDs, and cap-exceeding payloads.
*   **No Arbitrary Routing**: Hardcoded allowlists in conditional edges to prevent model decisions from triggering arbitrary nodes.

---

## 2. Iteration Count Semantics

*   **Initial Value**: `0`
*   **Node of Increment**: `generate_hypothesis` (incremented by 1 at each pass)
*   **Timing of Check**: Inside the conditional routing function `route_after_evaluation` immediately after `evaluate_hypothesis`.
*   **Hypothesis Generation Alignment**: The initial hypothesis is generated during the first iteration. A maximum of 3 hypotheses can be generated.
*   **Rebuild Counter vs. Iteration Counter**: The rebuild counter is incremented inside `rebuild_context`. Because context rebuilding occurs after tool execution (and before generating the next hypothesis), it naturally lags by 1. For a maximum budget of 3:
    *   Iteration 1: initial context (rebuild=0), hypothesis 1.
    *   Iteration 2: rebuild=1, hypothesis 2.
    *   Iteration 3: rebuild=2, hypothesis 3.
    *   If iteration budget is exhausted, it escalates to `human_review` without performing a 3rd rebuild.

---

## 3. Failure Routing & Exception Handling

All node executions in the graph conform to **Category A** exception handling:
*   **Category A**: The node wraps its entire logic in a try-except block. Any raised exception is caught, logged, and converted into a `FailureTerminalState` containing diagnostic details (excluding any secrets).
*   **Conditional Edge Enforcement**: For non-terminal nodes, every state transition checks `if state.get("failure") is not None` and immediately routes the graph execution to the `failure` node. Terminal nodes (`finalize_rca`, `human_review`) catch exceptions and transition directly to `END` via static edges (retaining the failure payload and setting a failed `termination_reason`).

| Node Name | Success Target(s) | Exception Behavior Category | Failure Target |
|---|---|---|---|
| `initialize` | `build_context` | A: Caught & converted to `FailureTerminalState` | `failure` |
| `build_context` | `generate_hypothesis` | A: Caught & converted to `FailureTerminalState` | `failure` |
| `generate_hypothesis` | `evaluate_hypothesis` | A: Caught & converted to `FailureTerminalState` | `failure` |
| `evaluate_hypothesis` | `finalize_rca`, `human_review`, `identify_evidence_gap` | A: Caught & converted to `FailureTerminalState` | `failure` |
| `identify_evidence_gap` | `select_tool` | A: Caught & converted to `FailureTerminalState` | `failure` |
| `select_tool` | `execute_tool` | A: Caught & converted to `FailureTerminalState` | `failure` |
| `execute_tool` | `validate_evidence` | A: Caught & converted to `FailureTerminalState` | `failure` |
| `validate_evidence` | `rebuild_context` | A: Caught & converted to `FailureTerminalState` | `failure` |
| `rebuild_context` | `generate_hypothesis` | A: Caught & converted to `FailureTerminalState` | `failure` |
| `finalize_rca` | `END` | A: Caught & converted to `FailureTerminalState` | `END` (sets failure payload) |
| `human_review` | `END` | A: Caught & converted to `FailureTerminalState` | `END` (sets failure payload) |
| `failure` | `END` | A: Logged & returned | `END` |

---

## 4. Evidence Validation & Cap Policies

To avoid silent data corruption and maintain context size constraints, a single deterministic policy is enforced:

1.  **Single Item Invalid**: Raises a `ValidationError` inside `execute_tool`. Caught and returned as `TOOL_EXECUTION_FAILURE` (routes to `failure`).
2.  **Intra-Batch Duplicate IDs**: If a single tool run returns duplicate IDs within the same batch, it raises `ValidationError` -> terminates in `failure`.
3.  **Inter-Batch Duplicate IDs**: If a duplicate ID matches an already collected item in the state, it is accepted and merged gracefully by `EvidenceDeduplicator` during context rebuild.
4.  **Cap Already Reached**: If the list already has 100 items, any attempt to run a tool raises `ValidationError` -> terminates in `failure`.
5.  **Adding Batch Exceeds Cap**: If adding the new batch of items would push the total above 100, the entire batch is rejected -> raises `ValidationError` -> terminates in `failure`.

---

## 5. Gateway Permanent Failure Routing

*   **Gateway Retries**: Transient errors (429, timeout, 503) are retried with exponential backoff inside `LLMGateway`.
*   **Permanent Failures**: Retries exhausted, authentication failure (401/403), or invalid API configurations raise a `GatewayError` immediately.
*   **Secret Safety**: Exception blocks catch `GatewayError` and extract only generic error descriptions. API keys or environment secrets are guaranteed to never be exposed in `FailureTerminalState` payloads.

---

## 6. Terminal Node Verification

By graph design and edge configuration:
*   `finalize_rca`, `human_review`, and `failure` have direct static transitions to `END`.
*   Unit tests verify that once these states are populated or node methods are triggered, no other subsequent diagnostic nodes or gateways are called.

---

## 7. Default Test Suite Results

**Command**: `.\venv\Scripts\python.exe -m pytest`

| Metric | Count (Offline Mode) | Count (Live-Enabled Mode) |
| :--- | :--- | :--- |
| Collected | 118 | 118 |
| Passed | 116 | 118 |
| Failed | 0 | 0 |
| Skipped | 2 (integration live tests) | 0 |
| Warnings | 3 | 3 |

All 20 orchestration-specific unit and integration tests passed successfully.

---

## 8. Exit Checklist

*   `[x]` Bounded LangGraph StateGraph implementation validated.
*   `[x]` Try-except wrappers added to all nodes in `nodes.py`.
*   `[x]` Complete deterministic failure propagation verified, including dedicated failure-node routing for non-terminal nodes and failed END states for terminal-node exceptions.
*   `[x]` Counter verification test cases written.
*   `[x]` Permanent gateway exception handling traced.
*   `[x]` Documentation in `PROJECT_CONTEXT/ORCHESTRATION_ARCHITECTURE.md` updated.
*   `[x]` Stale counts in `DOCS/00_MIGRATION_REPORT.md` reverted to Phase 7 release baseline.
