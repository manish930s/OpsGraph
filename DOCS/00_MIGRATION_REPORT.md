# OpsGraph AI — Phase Migration Report
**Document Status:** Finalized (Phase 6 Complete)  
**Reporting Phase:** Phase 6: Deterministic Context Builder  
**Execution Date:** 2026-07-08  
**Lead Engineer:** Antigravity (AI Coding Assistant)  

---

## 1. Executive Summary

Phase 6 (Deterministic Context Builder) of the OpsGraph AI migration is complete and verified. We built the Context Builder service, which deterministically validates, normalizes, deduplicates, prioritizes, budgets, and packages evidence and knowledge bundles into a canonical, immutable `InvestigationContext`. All scoring, selection, and limit checks are 100% deterministic and execute without LLM calls or prompt templates. The full test suite runs successfully with 58 passing tests.

---

## 2. Repository Revision & Git Status
*   **Active Branch**: `feature/phase-6-context-builder` (Verified using Git CLI)
*   **Refactoring Date**: 2026-07-08
*   **Execution Workspace**: `opsgraph-ai/`
*   **Working Directory State**: Clean (nothing to commit, working tree clean)

---

## 3. File Modification Ledger

All file paths listed below are relative to the target codebase root `opsgraph-ai/`.

### 3.1 Files Created
*   `[NEW]` [app/schemas/context.py](../opsgraph-ai/app/schemas/context.py) - Canonical ContextItem and InvestigationContext schemas.
*   `[NEW]` [app/services/context/exceptions.py](../opsgraph-ai/app/services/context/exceptions.py) - Domain exceptions (`ContextValidationError`, `ContextScopeMismatchError`, `ContextBudgetError`).
*   `[NEW]` [app/services/context/identity.py](../opsgraph-ai/app/services/context/identity.py) - Deterministic SHA-256 ID generator.
*   `[NEW]` [app/services/context/validator.py](../opsgraph-ai/app/services/context/validator.py) - Input bundle verification layer.
*   `[NEW]` [app/services/context/normalizer.py](../opsgraph-ai/app/services/context/normalizer.py) - Canonical parser methods.
*   `[NEW]` [app/services/context/deduplicator.py](../opsgraph-ai/app/services/context/deduplicator.py) - Alphanumeric and content-hash duplicate merger.
*   `[NEW]` [app/services/context/prioritizer.py](../opsgraph-ai/app/services/context/prioritizer.py) - Configurable prioritization policy and tie-breaking sorter.
*   `[NEW]` [app/services/context/budget.py](../opsgraph-ai/app/services/context/budget.py) - Budget estimators and unused allocation redistributors.
*   `[NEW]` [app/services/context/coverage.py](../opsgraph-ai/app/services/context/coverage.py) - Telemetry coverage analysis and deterministic gap reporting.
*   `[NEW]` [app/services/context/builder.py](../opsgraph-ai/app/services/context/builder.py) - Main orchestrator pipeline.
*   `[NEW]` [app/services/context/__init__.py](../opsgraph-ai/app/services/context/__init__.py) - Package exports.
*   `[NEW]` [PROJECT_CONTEXT/CONTEXT_BUILDER_ARCHITECTURE.md](../opsgraph-ai/PROJECT_CONTEXT/CONTEXT_BUILDER_ARCHITECTURE.md) - Context builder architectural details and diagrams.
*   `[NEW]` [tests/unit/test_context_builder.py](../opsgraph-ai/tests/unit/test_context_builder.py) - Validation, normalization, scoring, budgeting, and coverage test suite.

### 3.2 Files Modified
*   `[MODIFY]` [app/schemas/incident.py](../opsgraph-ai/app/schemas/incident.py) - Renamed old search-related `InvestigationContext` to `IncidentContext` to free the namespace.
*   `[MODIFY]` [app/schemas/__init__.py](../opsgraph-ai/app/schemas/__init__.py) - Exported all new context schemas.
*   `[MODIFY]` [README.md](../opsgraph-ai/README.md) - Updated with Phase 6 implementation status.

---

## 4. Context Builder Components & Flow

The Context Builder implements the following sub-responsibilities:

### 4.1 Input Validation
Verifies scenario and incident ID consistency across the `EvidenceBundle`. Rejects cross-scenario requests or incompatible incidents by raising `ContextScopeMismatchError`.

### 4.2 Deterministic Identity & Normalizer
Converts evidence and knowledge items to canonical `ContextItem` models. Assigns deterministic SHA-256 item IDs computed on the scope and source ID to prevent random UUID generation.

### 4.3 Deduplication Strategy
Aggregates duplicate items by stable source keys `(source_kind, source_id)` and content text hashes. Merges metadata and records the highest priority and retrieval scores.

### 4.4 Configurable Priority Scoring
Calculates priorities using a weight-based policy:
*   *Evidence*: Computes scores based on confidence, source reliability, and contradiction penalties.
*   *Knowledge*: Computes scores based on rerank relevance, fusion scores, and service scope alignment.
Stable tie-breaker: descending priority score, then ascending source ID.

### 4.5 Budget Management & Allocation
Partitions the total budget into evidence, knowledge, and reserved overhead limits. Processes evidence first, and **automatically redistributes unused evidence allocation to the knowledge allocation** for sparse incidents. Prunes low-priority candidates that exceed the limits.

### 4.6 Citation & Provenance Preservations
*   *Citations*: Maps selected items to their source origin parameters (telemetry records for evidence, document paths/sections/versions for runbooks).
*   *Provenance*: Traces the complete dataflow lineage from raw files/events down to the finalized context item.

### 4.7 Section Organization
Groups items into typed lists: `Critical Evidence`, `Supporting Evidence`, `Contradictory Evidence`, `Relevant Runbooks`, `Relevant Operational Knowledge`, `Topology Context`, and `Deployment Context`.

### 4.8 Coverage & Gap Analysis
Computes coverage across 8 telemetry/knowledge categories. Dynamically reports gaps (like missing trace evidence, empty runbooks, or degraded retrievals) using rule-based metrics.

---

## 5. Test & Verification Execution Ledger

*   **Test Command**: `.\venv\Scripts\python.exe -m pytest tests/`
*   **Total Tests Collected**: 58
*   **Total Tests Passed**: 58
*   **Total Tests Failed**: 0
*   **Total Tests Skipped**: 0

The 8 new Context Builder unit tests verify valid/invalid input combinations, normalization, deterministic ID hashes, duplicate merges, priority scoring components, unused budget redistributions, citation traces, and gap warnings.

---

## 6. Technical Debt, Future Enhancements, and Constraints

### 6.1 Current Technical Debt
*   **Word-Count Estimations**: Budget cost is approximated using word counts.

### 6.2 Future Enhancements
*   **Tiktoken Integration**: Standardize on a tokenizer (such as tiktoken) for exact token counts once downstream LLM models are selected in Phase 7.

### 6.3 Known Constraints
*   **Deterministic Only**: The builder performs zero LLM, template parsing, or routing operations.

---

## 7. Future Phase Boundaries

### 7.1 Phase 7 Boundary
The future Phase 7 layer will consume the immutable `InvestigationContext` to perform Prompt Assembly, configure input/output NVIDIA NeMo Guardrails, and configure unified Groq model routes via the LLM Gateway. Large inline prompts are prohibited inside LangGraph nodes.

---

## 8. Exit Checklist

*   `[x]` **Branch Name Verified**: Active on `feature/phase-6-context-builder`.
*   `[x]` **InvestigationContext Immutable**: Frozen models enforce immutability.
*   `[x]` **No LLM usage**: Builder is 100% deterministic.
*   `[x]` **All 58 Tests Pass**: Pytest suite reports 100% success.
*   `[x]` **No Phase 7 Leakage**: No gateway, guardrails, or prompt files created.
