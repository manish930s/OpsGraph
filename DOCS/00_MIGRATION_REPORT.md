# OpsGraph AI — Phase Migration Report
**Document Status:** Finalized (Phase 6 Stabilization Complete)  
**Reporting Phase:** Phase 6: Deterministic Context Builder (Stabilized)  
**Execution Date:** 2026-07-08  
**Lead Engineer:** Antigravity (AI Coding Assistant)  

---

## 1. Executive Summary

Phase 6 (Deterministic Context Builder) of the OpsGraph AI migration has been stabilized, audited, and tested. We have strengthened cross-bundle scope validations, added knowledge reference validations, implemented a tiered deduplication policy (preserving content-equivalence items with unique citations/provenances), formalized a bidirectional budget redistribution mechanism, defined explicit oversized-item exclusions, integrated comprehensive citation and provenance integrity passes, and propagated all degraded-mode and contradiction warnings cleanly. The full test suite runs successfully with 66 passing tests (an addition of 8 new stabilization tests).

---

## 2. Repository Revision & Git Status
*   **Active Branch**: `feature/phase-6-context-builder` (Verified using Git CLI)
*   **Refactoring Date:** 2026-07-08
*   **Execution Workspace:** `opsgraph-ai/`
*   **Working Directory State:** Staged & Clean (except for migration report edits)

---

## 3. File Modification Ledger

All file paths listed below are relative to the target codebase root `opsgraph-ai/`.

### 3.1 Files Created
*   `[NEW]` [app/schemas/context.py](../opsgraph-ai/app/schemas/context.py) - Canonical ContextItem and InvestigationContext schemas.
*   `[NEW]` [app/services/context/exceptions.py](../opsgraph-ai/app/services/context/exceptions.py) - Domain exceptions (`ContextValidationError`, `ContextScopeMismatchError`, `ContextBudgetError`).
*   `[NEW]` [app/services/context/identity.py](../opsgraph-ai/app/services/context/identity.py) - Deterministic SHA-256 ID generator.
*   `[NEW]` [app/services/context/validator.py](../opsgraph-ai/app/services/context/validator.py) - Input bundle and knowledge evidence reference validation.
*   `[NEW]` [app/services/context/normalizer.py](../opsgraph-ai/app/services/context/normalizer.py) - Canonical parser methods.
*   `[NEW]` [app/services/context/deduplicator.py](../opsgraph-ai/app/services/context/deduplicator.py) - Tiered deduplication policy (Tiers 1, 2, and 3).
*   `[NEW]` [app/services/context/prioritizer.py](../opsgraph-ai/app/services/context/prioritizer.py) - Configurable prioritization policy and tie-breaking sorter.
*   `[NEW]` [app/services/context/budget.py](../opsgraph-ai/app/services/context/budget.py) - Bidirectional budget redistribution and oversized-item pruning policies.
*   `[NEW]` [app/services/context/coverage.py](../opsgraph-ai/app/services/context/coverage.py) - Telemetry coverage analysis and deterministic gap/oversized reporting.
*   `[NEW]` [app/services/context/builder.py](../opsgraph-ai/app/services/context/builder.py) - Orchestration pipeline and citation/provenance integrity verification.
*   `[NEW]` [app/services/context/__init__.py](../opsgraph-ai/app/services/context/__init__.py) - Package exports.
*   `[NEW]` [PROJECT_CONTEXT/CONTEXT_BUILDER_ARCHITECTURE.md](../opsgraph-ai/PROJECT_CONTEXT/CONTEXT_BUILDER_ARCHITECTURE.md) - Context builder architectural details and diagrams.
*   `[NEW]` [tests/unit/test_context_builder.py](../opsgraph-ai/tests/unit/test_context_builder.py) - Expanded edge-case and determinism test suite.

### 3.2 Files Modified
*   `[MODIFY]` [app/schemas/incident.py](../opsgraph-ai/app/schemas/incident.py) - Renamed old search-related `InvestigationContext` to `IncidentContext`.
*   `[MODIFY]` [app/schemas/__init__.py](../opsgraph-ai/app/schemas/__init__.py) - Exported context schemas.
*   `[MODIFY]` [README.md](../opsgraph-ai/README.md) - Updated Phase Roadmap Status.

---

## 4. Context Builder Stabilization Features

### 4.1 Cross-Bundle Scope Validation
Verifies consistency across scenario and incident scopes. Rejects mismatched metadata properties immediately with `ContextScopeMismatchError`.

### 4.2 Knowledge Evidence Reference Validation
Ensures every evidence item referred to by the `KnowledgeBundle` matches a valid ID in the `EvidenceBundle`. Orphan or duplicate references trigger `ContextValidationError`.

### 4.3 Tiered Deduplication Policy
*   **Tier 1 & Tier 2**: Deduplicates identical source keys and chunk IDs.
*   **Tier 3**: Treats content-equivalent items from different documents/versions/sections as separate items, linking them with `content_equivalence_group` and `content_equivalent_to` metadata lists.

### 4.4 Bidirectional Budget Redistribution Policy
*   *Pass 1*: Allocates candidates within initial category limits.
*   *Pass 2*: Offers unused evidence budget to remaining knowledge candidates AND unused knowledge budget to remaining evidence candidates.

### 4.5 Oversized-Item Exclusion
*   Items exceeding initial category limits or the total context budget are excluded entirely (no partial truncation).
*   Exclusions are recorded in `execution_metadata` and reported in `gap_summary` with the reason `OVERSIZED_ITEM_EXCLUDED`.

### 4.6 Citation & Provenance Integrity Verification
Validates maps to prevent orphan records or missing paths before packaging the final context model. Lineage traces are fully verified.

### 4.7 Degraded-Mode Propagation
Upstream execution state (mock embeddings, fallbacks, vector store mode) propagates to `InvestigationContext.execution_metadata` without mutation.

### 4.8 Contradictory Evidence Retention
Contradictory evidence is maintained in the `Contradictory Evidence` section. If budget limits force exclusion, a warning is added: `"Budget excluded contradictory evidence."`

---

## 5. Test & Verification Execution Ledger

*   **Test Command**: `.\venv\Scripts\python.exe -m pytest tests/`
*   **Total Tests Collected**: 66
*   **Total Tests Passed**: 66
*   **Total Tests Failed**: 0
*   **Total Tests Skipped**: 0

The 16 Context Builder unit tests verify valid/invalid input combinations, normalization, deterministic ID hashes, duplicate merges, priority scoring components, bidirectional budget redistributions, citation traces, and gap warnings.

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

### 7.1 Phase 7 Provider-Agnostic Gateway Boundary
Downstream prompt assembly and LLM execution will go through a provider-agnostic LLM Gateway interface with distinct model adapters:
*   *Groq Adapter*: Initial target implementation.
*   *Gemini, OpenAI, Local adapters*: Reserved as future extensions.
*   *Safety Rails*: NVIDIA NeMo Guardrails will handle input/output gating at a separate boundary.
*   *Notice*: Verify library compatibility under python standard environments (Python 3.11 recommended) before installation.

---

## 8. Exit Checklist

*   `[x]` **Branch Name Verified**: Active on `feature/phase-6-context-builder`.
*   `[x]` **InvestigationContext Immutable**: Enforced by frozen Pydantic models.
*   `[x]` **No LLM usage**: Builder is 100% deterministic.
*   `[x]` **All 66 Tests Pass**: Pytest suite reports 100% success.
*   `[x]` **No Phase 7 Leakage**: No gateway, guardrails, or prompt files created.
