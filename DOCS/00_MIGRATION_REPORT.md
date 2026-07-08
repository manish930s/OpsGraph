# OpsGraph AI — Phase Migration Report
**Document Status:** Finalized (Phase 4 Complete)  
**Reporting Phase:** Phase 4: Evidence Grounding Layer  
**Execution Date:** 2026-07-08  
**Lead Engineer:** Antigravity (AI Coding Assistant)  

---

## 1. Executive Summary

Phase 4 (Evidence Grounding Layer) of the OpsGraph AI migration is complete. We designed, implemented, and verified the deterministic Evidence Grounding Layer. This layer normalizes diagnostic tool observations into canonical `Evidence` structures, aggregates multiple telemetry streams, performs de-duplication with MD5 content hashing, evaluates heuristic confidence scores/bands, and packages validated timeline items into an immutable `EvidenceBundle`. All evaluations are isolated from LLMs and routing. The full test suite runs successfully with 41 passing tests.

---

## 2. File Modification Ledger

All file paths listed below are relative to the target codebase root `opsgraph-ai/`.

### 2.1 Files Created
*   `[NEW]` [app/services/evidence/identity.py](../opsgraph-ai/app/services/evidence/identity.py) - Utilities generating deterministic IDs and content MD5 hashes.
*   `[NEW]` [app/services/evidence/normalizer.py](../opsgraph-ai/app/services/evidence/normalizer.py) - Converts tool responses to standard Pydantic `Evidence` records.
*   `[NEW]` [app/services/evidence/aggregator.py](../opsgraph-ai/app/services/evidence/aggregator.py) - Aggregates multiple evidence collections.
*   `[NEW]` [app/services/evidence/deduplicator.py](../opsgraph-ai/app/services/evidence/deduplicator.py) - Merges matching observations and accumulates metadata.
*   `[NEW]` [app/services/evidence/confidence.py](../opsgraph-ai/app/services/evidence/confidence.py) - Assigns confidence scoring bands (LOW, MEDIUM, HIGH).
*   `[NEW]` [app/services/evidence/timeline.py](../opsgraph-ai/app/services/evidence/timeline.py) - Builds chronologically sequenced timelines.
*   `[NEW]` [app/services/evidence/packager.py](../opsgraph-ai/app/services/evidence/packager.py) - Packages validated items into an immutable `EvidenceBundle`.
*   `[NEW]` [app/services/evidence/query.py](../opsgraph-ai/app/services/evidence/query.py) - Search and filter APIs on top of `EvidenceBundle`.
*   `[NEW]` [tests/unit/test_evidence_grounding.py](../opsgraph-ai/tests/unit/test_evidence_grounding.py) - Grounding validations, normalizers, deduplications, and rejections.

### 2.2 Files Modified
*   `[MODIFY]` [app/schemas/evidence.py](../opsgraph-ai/app/schemas/evidence.py) - Added Pydantic model schemas for `ConfidenceSummary` and `EvidenceBundle`.
*   `[MODIFY]` [app/schemas/__init__.py](../opsgraph-ai/app/schemas/__init__.py) - Exported the new schema models.
*   `[MODIFY]` [app/services/evidence/validator.py](../opsgraph-ai/app/services/evidence/validator.py) - Implemented `validate_evidence()` checking scenario, incident, and topology boundaries.
*   `[MODIFY]` [app/services/evidence/__init__.py](../opsgraph-ai/app/services/evidence/__init__.py) - Package exports updated to expose the 8 new services.

---

## 3. Evidence Grounding API & Package Structures

The layer implements the following deterministic sub-responsibilities:

### 3.1 Normalization
Converts log, metric, trace, deployment, topology, and active incident context outputs into canonical Pydantic `Evidence` records. Every item contains an MD5 content signature and deterministic identifier.

### 3.2 Aggregation & Deduplication
Combines multiple tool streams, deduplicates observations matching the same source identifiers or contents, and merges metadata query parameters without dropping any provenance history.

### 3.3 Validation
A single validation gate checking:
1.  *Scenario Match*: Rejects cross-scenario telemetry.
2.  *Incident Match*: Rejects cross-incident observations.
3.  *Timestamp Check*: Rejects timestamps occurring beyond the investigation window end.
4.  *Topology check*: Rejects observations referencing services absent from the topology nodes mapping.

### 3.4 Scorer & Packager
Evaluates heuristic confidence indicators (coverage ratio, consensus count, timeline intervals, no-deployment penalties), maps them to scoring bands (LOW, MEDIUM, HIGH), and wraps them inside the immutable `EvidenceBundle` structure.

---

## 4. Test & Verification Execution Ledger

We ran the test suite using `python -m pytest tests/` with the python environment inside the virtualenv `venv` directory.

### 4.1 Test Run Status
*   **Total Tests Executed**: 41
*   **Total Tests Passed**: 41
*   **Total Tests Failed**: 0

### 4.2 Executed Grounding Test Categories
1.  **Normalizer Conversions**:
    *   `test_normalization`: Asserts conversions for logs, metrics, trace spans, topology directions, and active incident details.
2.  **Aggregation & Timeline Sorting**:
    *   `test_aggregation_and_timeline`: Merges lists and checks chronological sorting keys and time-slice filters.
3.  **Deduplication Merges**:
    *   `test_deduplicator`: Asserts merging identical source IDs combines query references without loss.
4.  **Confidence Scoring**:
    *   `test_confidence_scorer`: Asserts score increments and band assignments (LOW vs HIGH).
5.  **Validator Rejections**:
    *   `test_validator_rejections`: Verifies rejections for missing IDs, scenario mismatches, incident mismatches, future timestamps, and non-topology services.
6.  **Query Filtering**:
    *   `test_packager_and_query_api`: Evaluates packaging bundles and querying by service, type, or windows.

---

## 5. Architectural Decisions & Deviations

*   **Pydantic model_copy Update**: When creating invalid test evidence with `model_copy(update=...)`, Pydantic does not execute nested type validation. We standardized tests to pass instantiated Pydantic models (like `TimeWindow`) directly to avoid attributes retaining raw dictionary types.
*   **Heuristic Confidence Metrics**: Designed a multi-layered confidence summary incorporating coverage, consensus, timeline proximity, and deployment penalties.

---

## 6. Technical Debt, Future Enhancements, and Constraints

### 6.1 Current Technical Debt
*   **Deduplication Key Collisions**: If duplicate telemetry has conflicting observations, deduplication resolves based on first-in keys, keeping first message details.

### 6.2 Future Enhancements
*   **Graph Dependency Scopes**: Incorporate topology path distance metrics in confidence calculations (e.g. penalizing disconnected evidence chains).

### 6.3 Known Constraints
*   **Deterministic Only**: The layer contains no LLM operations or prompt constructions, ensuring that reasoning remains decoupled.

---

## 7. Execution Roadmap (Phases 5 to 10)

1.  **Phase 5**: Knowledge Ingestion + Qdrant + FlashRank (RAG vector pipeline and reranker)
2.  **Phase 6**: LLM Gateway + NeMo Guardrails (Centralized model routing and input/output safety)
3.  **Phase 7**: LangGraph Investigation Engine (10-node state machine and routing paths)
4.  **Phase 8**: FastAPI Endpoints (FASTAPI routes and incident POST handlers)
5.  **Phase 9**: Streamlit Dashboard UI (Diagnostic interface and latency stats)
6.  **Phase 10**: Evaluation + Docker + Portfolio Release (30 scenario bench tests and docker orchestration)

---

## 8. Repository Revision & Exit Ledger

### 8.1 Repository Revision
*   **Active Branch**: `feature/phase-4-evidence-grounding`
*   **Refactoring Date**: 2026-07-08
*   **Execution Workspace**: `opsgraph-ai/`

### 8.2 Phase 4 Exit Checklist

*   `[x]` **Grounding Interfaces Compile**: Models compile and assert typed schemas.
*   `[x]` **No LLM Creation of Evidence**: All normalization is programmatically deterministic.
*   `[x]` **Rejections Verified**: Cross-scenario, future times, and topology rejections pass.
*   `[x]` **All 41 Tests Pass**: Pytest suite reports 100% success.
*   `[x]` **Feature Branch Created**: Active on `feature/phase-4-evidence-grounding`.
*   `[x]` **No Phase 5 Leakage**: No vector database or Qdrant/embedding code has been created.
