# OpsGraph AI — Phase Migration Report
**Document Status:** Finalized (Phase 5 Complete)  
**Reporting Phase:** Phase 5: Enterprise Knowledge Layer  
**Execution Date:** 2026-07-08  
**Lead Engineer:** Antigravity (AI Coding Assistant)  

---

## 1. Executive Summary

Phase 5 (Enterprise Knowledge Layer) of the OpsGraph AI migration is complete and verified. We built the complete Enterprise Knowledge Layer implementing loader, normalizer, chunker, embedding, vector store (Qdrant), hybrid search, rerank, and cache services. All schemas are strictly typed and immutable, using frozen Pydantic models. Vector search is offline-capable with local memory fallback. Reranking leverages FlashRank with a local Jaccard word-overlap fallback. The full test suite runs successfully with 49 passing tests.

---

## 2. File Modification Ledger

All file paths listed below are relative to the target codebase root `opsgraph-ai/`.

### 2.1 Files Created
*   `[NEW]` [app/schemas/knowledge.py](../opsgraph-ai/app/schemas/knowledge.py) - Frozen Pydantic schemas for `KnowledgeDocument`, `KnowledgeChunk`, and `KnowledgeBundle`.
*   `[NEW]` [app/services/knowledge/base_embedding.py](../opsgraph-ai/app/services/knowledge/base_embedding.py) - Decoupled embedding interfaces and deterministic Mock generator.
*   `[NEW]` [app/services/knowledge/vector_store_base.py](../opsgraph-ai/app/services/knowledge/vector_store_base.py) - Abstract vector store adapter interface.
*   `[NEW]` [app/services/knowledge/qdrant_adapter.py](../opsgraph-ai/app/services/knowledge/qdrant_adapter.py) - Qdrant adapter with transparent UUID mapping and local in-memory fallback.
*   `[NEW]` [app/services/knowledge/loader.py](../opsgraph-ai/app/services/knowledge/loader.py) - Yaml front-matter loader parsing operational guides and runbooks.
*   `[NEW]` [app/services/knowledge/chunker.py](../opsgraph-ai/app/services/knowledge/chunker.py) - Heading-aware structural splitted chunker.
*   `[NEW]` [app/services/knowledge/reranker.py](../opsgraph-ai/app/services/knowledge/reranker.py) - FlashRank reranker with local Jaccard fallback.
*   `[NEW]` [app/services/knowledge/cache.py](../opsgraph-ai/app/services/knowledge/cache.py) - In-memory embedding and search result cacher.
*   `[NEW]` [app/services/knowledge/retriever.py](../opsgraph-ai/app/services/knowledge/retriever.py) - Coordinator executing hybrid search with evidence filters.
*   `[NEW]` [app/services/knowledge/__init__.py](../opsgraph-ai/app/services/knowledge/__init__.py) - Package exports.
*   `[NEW]` [PROJECT_CONTEXT/KNOWLEDGE_LAYER_ARCHITECTURE.md](../opsgraph-ai/PROJECT_CONTEXT/KNOWLEDGE_LAYER_ARCHITECTURE.md) - Design documentation of RAG workflows and contracts.
*   `[NEW]` [tests/unit/test_knowledge_layer.py](../opsgraph-ai/tests/unit/test_knowledge_layer.py) - Ingestion, chunking, filters, and retriever test suites.

### 2.2 Files Modified
*   `[MODIFY]` [app/schemas/__init__.py](../opsgraph-ai/app/schemas/__init__.py) - Exported knowledge schemas.
*   `[MODIFY]` [requirements.txt](../opsgraph-ai/requirements.txt) - Cleaned up compile-only vertexai/nemoguardrails/ragas packages to support Python 3.14 on Windows sandbox.

---

## 3. Knowledge Layer Components & Flow

The Knowledge Layer implements the following RAG sub-responsibilities:

### 3.1 loader & normalizer
Loads Markdown documents and extracts Yaml front matter containing document ID, tags, title, version, and type. It compiles it into a structured `KnowledgeDocument`.

### 3.2 Heading-Aware Chunker
Partitions documents based on markdown structural headings (like `# Symptoms`, `# Investigation Steps`), ensuring section context is preserved. Chunks inherit parent metadata.

### 3.3 Vector Store UUID Adapter
Encapsulates Qdrant Client (in-memory mode for offline unit testing). Since Qdrant enforces string IDs to be valid UUIDs, the adapter implements a deterministic `uuid.uuid5` generator mapping chunk strings, storing original IDs inside payload maps.

### 3.4 Hybrid search & Rerank
Queries vectors applying evidence-driven scope filters (e.g. searching only runbooks related to services coverage summary of `EvidenceBundle`). Executes FlashRank cross-encoder rerank with a fallback word-overlap matcher for safety.

---

## 4. Test & Verification Execution Ledger

We ran the test suite using `python -m pytest tests/` with the python environment inside the virtualenv `venv` directory.

### 4.1 Test Run Status
*   **Total Tests Executed**: 49
*   **Total Tests Passed**: 49
*   **Total Tests Failed**: 0

### 4.2 Executed Knowledge Test Categories
1.  **Document Loader Ingests**:
    *   `test_document_loader`: Validates Yaml parsing, front matter keys, and metadata.
2.  **Heading chunker splits**:
    *   `test_heading_aware_chunker`: Tests section partitioning and sequential ID tracking.
3.  **Embedding providers**:
    *   `test_embedding_provider`: Asserts seed stability and vector normalization L2.
4.  **Qdrant Adapter memory**:
    *   `test_qdrant_adapter_in_memory`: Verifies collection creation, upserts, deletes, and service filter queries.
5.  **Rerank Fallbacks**:
    *   `test_reranker_fallback`: Validates Jaccard overlap and heading boosts.
6.  **Retriever Coordinate**:
    *   `test_hybrid_retriever`: Asserts hybrid queries with evidence filtering and KnowledgeBundle immutability.

---

## 5. Architectural Decisions & Deviations

*   **Pydantic Immutability**: All Knowledge schemas enforce `model_config = {"frozen": True}` and collection fields are typed as `tuple` to ensure absolute immutability.
*   **Fallback Reranker**: Designed a fallback overlap-scorer using token intersection when FlashRank model binaries cannot download offline.
*   **Qdrant UUID Transposition**: Implemented transparent UUIDv5 mapping to make chunk IDs compatible with Qdrant string rules.

---

## 6. Technical Debt, Future Enhancements, and Constraints

### 6.1 Current Technical Debt
*   **Memory Cache Volatility**: Cache is currently volatile in-memory.

### 6.2 Future Enhancements
*   **Disk Cache Backing**: Add a persistent pickle/json disk cache file for caching embeddings.

### 6.3 Known Constraints
*   **No LLM usage**: Reasoning, LLM queries, and prompt compilation are completely omitted.

---

## 7. Execution Roadmap (Phases 6 to 10)

1.  **Phase 6**: LLM Gateway + NeMo Guardrails (Centralized model routing and input/output safety)
2.  **Phase 7**: LangGraph Investigation Engine (10-node state machine and routing paths)
3.  **Phase 8**: FastAPI Endpoints (FASTAPI routes and incident POST handlers)
4.  **Phase 9**: Streamlit Dashboard UI (Diagnostic interface and latency stats)
5.  **Phase 10**: Evaluation + Docker + Portfolio Release (30 scenario bench tests and docker orchestration)

---

## 8. Repository Revision & Exit Ledger

### 8.1 Repository Revision
*   **Active Branch**: `feature/phase-5-knowledge-layer`
*   **Refactoring Date**: 2026-07-08
*   **Execution Workspace**: `opsgraph-ai/`

### 8.2 Phase 5 Exit Checklist

*   `[x]` **RAG Interfaces Compile**: Models compile and assert typed schemas.
*   `[x]` **No LLM Queries**: Execution contains zero LLM operations.
*   `[x]` **Qdrant Adapter verified**: memory tests pass.
*   `[x]` **All 49 Tests Pass**: Pytest suite reports 100% success.
*   `[x]` **Feature Branch Created**: Active on `feature/phase-5-knowledge-layer`.
*   `[x]` **No Phase 6 Leakage**: No gateway or routing code has been created.
