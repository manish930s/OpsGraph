# OpsGraph AI — Phase Migration Report
**Document Status:** Finalized (Phase 4 Stabilization Complete)  
**Reporting Phase:** Phase 4: Evidence Grounding Layer  
**Execution Date:** 2026-07-08  
**Lead Engineer:** Antigravity (AI Coding Assistant)  

---

## 1. Executive Summary

Phase 4 (Evidence Grounding Layer) of the OpsGraph AI migration is complete and stabilized. We designed, implemented, and verified the deterministic Evidence Grounding Layer. This layer normalizes diagnostic tool observations into canonical `Evidence` structures, aggregates multiple telemetry streams, performs de-duplication with SHA-256 content hashing, evaluates heuristic confidence scores/bands across explicit components, and packages validated timeline items into an immutable `EvidenceBundle`. All evaluations are isolated from LLMs and routing. The full test suite runs successfully with 41 passing tests.

---

## 2. File Modification Ledger

All file paths listed below are relative to the target codebase root `opsgraph-ai/`.

### 2.1 Files Created
*   `[NEW]` [app/services/evidence/identity.py](../opsgraph-ai/app/services/evidence/identity.py) - Utilities generating deterministic IDs and content SHA-256 hashes.
*   `[NEW]` [app/services/evidence/normalizer.py](../opsgraph-ai/app/services/evidence/normalizer.py) - Converts tool responses to standard Pydantic `Evidence` records.
*   `[NEW]` [app/services/evidence/aggregator.py](../opsgraph-ai/app/services/evidence/aggregator.py) - Aggregates multiple evidence collections.
*   `[NEW]` [app/services/evidence/deduplicator.py](../opsgraph-ai/app/services/evidence/deduplicator.py) - Merges matching observations and accumulates metadata.
*   `[NEW]` [app/services/evidence/confidence.py](../opsgraph-ai/app/services/evidence/confidence.py) - Assigns confidence scoring bands (LOW, MEDIUM, HIGH) over structured components.
*   `[NEW]` [app/services/evidence/timeline.py](../opsgraph-ai/app/services/evidence/timeline.py) - Builds chronologically sequenced timelines using stable index sorting.
*   `[NEW]` [app/services/evidence/packager.py](../opsgraph-ai/app/services/evidence/packager.py) - Packages validated items into an immutable `EvidenceBundle`.
*   `[NEW]` [app/services/evidence/query.py](../opsgraph-ai/app/services/evidence/query.py) - Search and filter APIs on top of `EvidenceBundle`.
*   `[NEW]` [tests/unit/test_evidence_grounding.py](../opsgraph-ai/tests/unit/test_evidence_grounding.py) - Grounding validations, normalizers, deduplications, and rejections.

### 2.2 Files Modified
*   `[MODIFY]` [app/schemas/evidence.py](../opsgraph-ai/app/schemas/evidence.py) - Added Pydantic model schemas for `ConfidenceComponents`, `ConfidenceSummary` and `EvidenceBundle`, configured as frozen.
*   `[MODIFY]` [app/schemas/__init__.py](../opsgraph-ai/app/schemas/__init__.py) - Exported the new schema models.
*   `[MODIFY]` [app/services/evidence/validator.py](../opsgraph-ai/app/services/evidence/validator.py) - Implemented `validate_evidence()` checking scenario, incident, and topology boundaries.
*   `[MODIFY]` [app/services/evidence/__init__.py](../opsgraph-ai/app/services/evidence/__init__.py) - Package exports updated to expose the 8 new services.

---

## 3. Evidence Grounding API & Package Structures

The layer implements the following deterministic sub-responsibilities:

### 3.1 Normalization & SHA-256
Converts log, metric, trace, deployment, topology, and active incident context outputs into canonical Pydantic `Evidence` records. Every item contains a SHA-256 content signature and deterministic identifier. SHA-256 replaced MD5 to provide a stronger, modern hashing standard for cryptographic content integrity verification.

### 3.2 Immutability Enforcement
All evidence schemas and bundles in [app/schemas/evidence.py](../opsgraph-ai/app/schemas/evidence.py) enforce strict Pydantic immutability with `model_config = {"frozen": True}`. Additionally, the collection fields `evidence_list` and `timeline` in `EvidenceBundle` are typed as `tuple[Evidence, ...]` instead of `list[Evidence]`. This blocks in-place array modifications (e.g. index assignments), guaranteeing absolute mutability protection at runtime.

### 3.3 Explicit Confidence Components
Confidence calculations are separated into structured components in `ConfidenceComponents`:
*   *Source Reliability* (data accuracy metrics)
*   *Cross-Source Agreement* (consensus across telemetry streams)
*   *Timeline Consistency* (symptom onset proximity)
*   *Topology Consistency* (service mesh registration validity)
*   *Evidence Coverage* (ratio of reported service metrics gathered)
*   *Deployment Consistency* (preceding deployment event tracking)
*   *Observation Completeness* (telemetry type checklist)
*   *Contradictions* (conflicting message statuses)

These components roll up into the overall confidence score, band, and reasons without using guessing or LLM reasoning.

### 3.4 Stable Timeline Sequencing
The timeline builder in [app/services/evidence/timeline.py](../opsgraph-ai/app/services/evidence/timeline.py) sorts items using a two-element sorting key `(timestamp, original_index)`. If multiple telemetry events share the exact same timestamp, the timeline retains their original ingestion sequence order deterministically.

---

## 4. Test & Verification Execution Ledger

We ran the test suite using `python -m pytest tests/` with the python environment inside the virtualenv `venv` directory.

### 4.1 Test Run Status
*   **Total Tests Executed**: 41
*   **Total Tests Passed**: 41
*   **Total Tests Failed**: 0

### 4.2 Executed Grounding Test Categories
1.  **SHA-256 Content Hashing**:
    *   `test_normalization_and_sha256`: Asserts SHA-256 hash generation on normalized records.
2.  **Immutability Gates**:
    *   `test_evidence_bundle_immutability`: Verifies mutating frozen attributes or tuple items raises Pydantic `ValidationError` or Python `TypeError`.
3.  **Ingestion Stable Timelines**:
    *   `test_stable_timeline_sorting`: Checks that items with identical timestamps retain ingestion sequence order.
4.  **Confidence Scoring Components**:
    *   `test_confidence_components_scorer`: Asserts score components and category trackers.
5.  **Validator Rejections**:
    *   `test_validator_rejections`: Verifies rejections for missing scenario IDs, mismatched incident IDs, future timestamps, and invalid services.
6.  **Query Filtering**:
    *   `test_packager_and_query_api`: Evaluates packaging and querying by service, type, or windows.

---

## 5. Architectural Decisions & Deviations

*   **Frozen Tuple Collections**: Selected `tuple` over `list` inside the packaged bundle schema to ensure that list mutability traps are mitigated.
*   **Evaluation Isolation**: Ensured that the runtime directory is strictly partitioned from evaluation metrics data (`golden.json`). Added explicit unit tests to assert that `golden.json` is not queried during normal tool executions.

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
