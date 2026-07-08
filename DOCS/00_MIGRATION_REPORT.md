# OpsGraph AI — Phase Migration Report
**Document Status:** Finalized (Phase 3 Complete)  
**Reporting Phase:** Phase 3: Investigation Tool Layer  
**Execution Date:** 2026-07-08  
**Lead Engineer:** Antigravity (AI Coding Assistant)  

---

## 1. Executive Summary

Phase 3 (Investigation Tool Layer) of the OpsGraph AI migration is complete. We designed, implemented, and verified the deterministic, read-only investigation tool layer. Seven diagnostic tools have been built to expose and format telemetry data. A central `ToolRegistry` compiles the tools, exposing schemas for future LangGraph execution. All tools are decoupled from LLMs, routing, or agent orchestrations. The full test suite runs successfully with 34 passing tests.

---

## 2. File Modification Ledger

All file paths listed below are relative to the target codebase root `opsgraph-ai/`.

### 2.1 Files Created
*   `[NEW]` [app/tools/base.py](../opsgraph-ai/app/tools/base.py) - Abstract `BaseTool` class executing structured logging, duration measurement, and validation.
*   `[NEW]` [app/tools/registry.py](../opsgraph-ai/app/tools/registry.py) - Catalogs registered tools and exports JSON schemas.
*   `[NEW]` [app/tools/log_tool.py](../opsgraph-ai/app/tools/log_tool.py) - `LogSearchTool` querying and filtering log messages.
*   `[NEW]` [app/tools/metric_tool.py](../opsgraph-ai/app/tools/metric_tool.py) - `MetricAnalysisTool` managing metrics aggregations and temporal gaps.
*   `[NEW]` [app/tools/trace_tool.py](../opsgraph-ai/app/tools/trace_tool.py) - `TraceInspectionTool` building trace hierarchy dependency trees.
*   `[NEW]` [app/tools/deployment_tool.py](../opsgraph-ai/app/tools/deployment_tool.py) - `DeploymentHistoryTool` querying change history events.
*   `[NEW]` [app/tools/topology_tool.py](../opsgraph-ai/app/tools/topology_tool.py) - `ServiceDependencyTool` looking up upstream callers and downstream dependencies.
*   `[NEW]` [app/tools/incident_tool.py](../opsgraph-ai/app/tools/incident_tool.py) - `IncidentSummaryTool` fetching incident context.
*   `[NEW]` [app/tools/window_tool.py](../opsgraph-ai/app/tools/window_tool.py) - `TimeWindowTool` verifying and shifting chronological bounds.
*   `[NEW]` [app/tools/__init__.py](../opsgraph-ai/app/tools/__init__.py) - Package exports and registry bootstrap factory.
*   `[NEW]` [tests/unit/test_tools.py](../opsgraph-ai/tests/unit/test_tools.py) - Core tests for all diagnostic tools, schemas, registry, and execution logs.

---

## 3. Investigation Tools & API Contracts

All tools extend [BaseTool](../opsgraph-ai/app/tools/base.py) and expose their execution parameters through typed Pydantic request models:

### 3.1 IncidentSummaryTool (`incident_summary_lookup`)
*   **Request Model**: `IncidentSummaryInput`
    *   `incident_id`: Optional incident string to inspect.
*   **Response Model**: `IncidentSummaryResponse`
    *   Returns context including title, severity, environment, reported symptoms, and timestamps.

### 3.2 LogSearchTool (`log_pattern_search`)
*   **Request Model**: `LogSearchInput`
    *   `service`: Optional service filter.
    *   `pattern`: Optional regex pattern to query message content.
    *   `start` / `end`: Optional ISO-8601 window constraints.
*   **Response Model**: `LogSearchResponse`
    *   Returns list of matching `LogRecord` objects.

### 3.3 MetricAnalysisTool (`metric_window_analysis`)
*   **Request Model**: `MetricAnalysisInput`
    *   `metric_name`: Name of the metric series.
    *   `aggregator`: Optional operator (`avg`, `min`, `max`, `sum`).
    *   `start` / `end`: Optional ISO-8601 window constraints.
    *   `expected_interval_sec`: Optional frequency threshold for gap checking.
*   **Response Model**: `MetricAnalysisResponse`
    *   Returns list of points, aggregated value, and temporal gaps found.

### 3.4 TraceInspectionTool (`trace_dependency_analysis`)
*   **Request Model**: `TraceInspectionInput`
    *   `trace_id`: Unique ID of the trace.
    *   `service`: Optional service filter on spans.
*   **Response Model**: `TraceInspectionResponse`
    *   Returns tree representation mapping parent-child relations.

### 3.5 DeploymentHistoryTool (`deployment_event_search`)
*   **Request Model**: `DeploymentHistoryInput`
    *   `environment`: Target environment scope.
    *   `timestamp`: Optional ISO-8601 timestamp to resolve the latest deployment before.
*   **Response Model**: `DeploymentHistoryResponse`
    *   Returns history list and the resolved preceding deployment event.

### 3.6 ServiceDependencyTool (`service_topology_lookup`)
*   **Request Model**: `ServiceDependencyInput`
    *   `service_id`: Target service ID.
    *   `direction`: Relationships to return (`upstream`, `downstream`, `both`).
*   **Response Model**: `ServiceDependencyResponse`
    *   Returns list of connected service identifiers.

### 3.7 TimeWindowTool (`time_window_adjuster`)
*   **Request Model**: `TimeWindowInput`
    *   `start` / `end`: ISO-8601 start/end timestamps.
    *   `shift_minutes`: Minutes to expand boundaries.
*   **Response Model**: `TimeWindowResponse`
    *   Returns the shifted ISO-8601 window.

---

## 4. Test & Verification Execution Ledger

We ran the test suite using `python -m pytest tests/` with the python environment inside the virtualenv `venv` directory.

### 4.1 Test Run Status
*   **Total Tests Executed**: 34
*   **Total Tests Passed**: 34
*   **Total Tests Failed**: 0

### 4.2 Executed Tool Test Categories
1.  **Tool Registry Integrity (`test_tools.py`)**:
    *   `test_registry_lookup`: Asserts correct tool listing, retrieval, schema generations, and checks `ToolNotFoundError` handling.
2.  **Incident Inspection**:
    *   `test_incident_summary_tool`: Exercises loading standard incident cases and raises validation errors for mismatched IDs.
3.  **Log Queries**:
    *   `test_log_search_tool`: Exercises pattern filters, service scopes, and time window bounds on simulated log sets.
4.  **Metric Aggregation**:
    *   `test_metric_analysis_tool`: Checks interval gaps, aggregates values, and tests boundary window slicing.
5.  **Trace Analysis**:
    *   `test_trace_inspection_tool`: Generates parenting trees and asserts span counts.
6.  **Deployments & Environments**:
    *   `test_deployment_history_tool`: Validates latest-before timelines and environment filtering.
7.  **Topology Relations**:
    *   `test_service_dependency_tool`: Resolves caller/called components and handles invalid names.
8.  **Window Calculations**:
    *   `test_time_window_tool`: Calculates offset window shifts.

---

## 5. Architectural Decisions & Deviations

*   **Registry Factory**: Defined `create_default_registry()` in `app/tools/__init__.py` to act as the primary bootstrapper, allowing runtime instances to compile all tools with explicit repository dependencies.
*   **Structured Invocation Logging**: Embedded automatic duration parsing and output status logging directly inside `BaseTool.execute()`. This ensures that all future tool invocations are audited uniformly for latency and outcomes.

---

## 6. Technical Debt, Future Enhancements, and Constraints

### 6.1 Current Technical Debt
*   **Sequential Metric Processing**: The gap detection in `MetricAnalysisTool` processes points sequentially in Python memory, which is inefficient for large datasets.

### 6.2 Future Enhancements
*   **Concurrency Support**: Support parallel tool executions inside the LangGraph orchestrator to run multiple log and metric analysis tools asynchronously.

### 6.3 Known Constraints
*   **Stateless Execution**: Tools do not persist observations or maintain state. Conversation-level memory must be managed externally by the orchestrator.

---

## 7. Execution Roadmap (Phases 4 to 10)

1.  **Phase 4**: Evidence Grounding Layer (evidence aggregation and deterministic validator)
2.  **Phase 5**: Knowledge Ingestion + Qdrant + FlashRank (RAG vector pipeline and reranker)
3.  **Phase 6**: LLM Gateway + NeMo Guardrails (Centralized model routing and input/output safety)
4.  **Phase 7**: LangGraph Investigation Engine (10-node state machine and routing paths)
5.  **Phase 8**: FastAPI Endpoints (FASTAPI routes and incident POST handlers)
6.  **Phase 9**: Streamlit Dashboard UI (Diagnostic interface and latency stats)
7.  **Phase 10**: Evaluation + Docker + Portfolio Release (30 scenario bench tests and docker orchestration)

---

## 8. Repository Revision & Exit Ledger

### 8.1 Repository Revision
*   **Active Branch**: `feature/phase-3-investigation-tools`
*   **Refactoring Date**: 2026-07-08
*   **Execution Workspace**: `d:/Advance RAG`

### 8.2 Phase 3 Exit Checklist

*   `[x]` **Tool Interfaces Compile**: Interfaces compile and assert typed schemas.
*   `[x]` **No Business RCA Logic in Tools**: Tools are strictly deterministic queries.
*   `[x]` **Structured Logging Verified**: execution times and outcomes are logged.
*   `[x]` **All 34 Tests Pass**: Pytest suite reports 100% success.
*   `[x]` **Feature Branch Created**: Active on `feature/phase-3-investigation-tools`.
*   `[x]` **No Phase 4 Leakage**: No vector database or model gateway code has been created.
