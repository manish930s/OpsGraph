# OpsGraph AI — Phase Migration Report
**Document Status:** Finalized (Phase 5 Stabilization Complete)  
**Reporting Phase:** Phase 5: Enterprise Knowledge Layer (RAG)  
**Execution Date:** 2026-07-08  
**Lead Engineer:** Antigravity (AI Coding Assistant)  

---

## 1. Executive Summary

Phase 5 (Enterprise Knowledge Layer) of the OpsGraph AI migration is complete and stabilized. We implemented a genuine hybrid retrieval pipeline containing independent dense similarity search and lexical (BM25) search channels, fused candidate outputs using Reciprocal Rank Fusion (RRF), integrated FlashRank cross-encoders with a deterministic local Jaccard word-overlap fallback, and configured a `SentenceTransformerEmbeddingProvider` (with a local `MockEmbeddingProvider` fallback). The system dynamically evaluates and reports fallback transitions via typed execution metadata. The full test suite runs successfully with 50 passing tests.

---

## 2. File Modification Ledger

All file paths listed below are relative to the target codebase root `opsgraph-ai/`.

### 2.1 Files Created
*   `[NEW]` [app/schemas/knowledge.py](../opsgraph-ai/app/schemas/knowledge.py) - Frozen Pydantic schemas for `KnowledgeDocument`, `KnowledgeChunk`, `RetrievalChannelProvenance`, `RetrievalExecutionMetadata`, and `KnowledgeBundle`.
*   `[NEW]` [app/services/knowledge/base_embedding.py](../opsgraph-ai/app/services/knowledge/base_embedding.py) - Decoupled embedding interfaces, Mock generator, and the new `SentenceTransformerEmbeddingProvider`.
*   `[NEW]` [app/services/knowledge/vector_store_base.py](../opsgraph-ai/app/services/knowledge/vector_store_base.py) - Abstract vector store adapter interface.
*   `[NEW]` [app/services/knowledge/qdrant_adapter.py](../opsgraph-ai/app/services/knowledge/qdrant_adapter.py) - Qdrant adapter with transparent UUID mapping and local in-memory fallback.
*   `[NEW]` [app/services/knowledge/loader.py](../opsgraph-ai/app/services/knowledge/loader.py) - Yaml front-matter loader parsing operational guides and runbooks.
*   `[NEW]` [app/services/knowledge/chunker.py](../opsgraph-ai/app/services/knowledge/chunker.py) - Heading-aware structural splitted chunker.
*   `[NEW]` [app/services/knowledge/lexical.py](../opsgraph-ai/app/services/knowledge/lexical.py) - BM25 lexical search channel.
*   `[NEW]` [app/services/knowledge/fusion.py](../opsgraph-ai/app/services/knowledge/fusion.py) - Reciprocal Rank Fusion (RRF) deduplication and rank-merging step.
*   `[NEW]` [app/services/knowledge/reranker.py](../opsgraph-ai/app/services/knowledge/reranker.py) - FlashRank reranker with local Jaccard fallback.
*   `[NEW]` [app/services/knowledge/cache.py](../opsgraph-ai/app/services/knowledge/cache.py) - In-memory embedding and search result cacher.
*   `[NEW]` [app/services/knowledge/retriever.py](../opsgraph-ai/app/services/knowledge/retriever.py) - Hybrid search retrieval coordinator.
*   `[NEW]` [app/services/knowledge/__init__.py](../opsgraph-ai/app/services/knowledge/__init__.py) - Package exports.
*   `[NEW]` [PROJECT_CONTEXT/KNOWLEDGE_LAYER_ARCHITECTURE.md](../opsgraph-ai/PROJECT_CONTEXT/KNOWLEDGE_LAYER_ARCHITECTURE.md) - Design documentation of RAG workflows and contracts.
*   `[NEW]` [tests/unit/test_knowledge_layer.py](../opsgraph-ai/tests/unit/test_knowledge_layer.py) - Ingestion, chunking, filters, and retriever test suites.

### 2.2 Files Modified
*   `[MODIFY]` [app/schemas/__init__.py](../opsgraph-ai/app/schemas/__init__.py) - Exported knowledge schemas.
*   `[MODIFY]` [requirements.txt](../opsgraph-ai/requirements.txt) - Cleaned up compile-only vertexai/nemoguardrails/ragas packages to support Python 3.14 on Windows sandbox.

---

## 3. Knowledge Layer Components & Flow

The stabilized Knowledge Layer implements the following RAG sub-responsibilities:

### 3.1 loader & normalizer
Loads Markdown documents and extracts Yaml front matter containing document ID, tags, title, version, and type. It compiles it into a structured `KnowledgeDocument`.

### 3.2 Heading-Aware Chunker
Partitions documents based on markdown structural headings (like `# Symptoms`, `# Investigation Steps`), ensuring section context is preserved. Chunks inherit parent metadata.

### 3.3 Genuine Hybrid Search & Reciprocal Rank Fusion
1.  **Dense retrieval**: Cosine similarity vector search over the Qdrant database.
2.  **Lexical retrieval**: A local `BM25LexicalRetriever` scoring matching chunks based on term-frequency and inverse document frequency statistics, utilizing the same metadata scope filters.
3.  **Reciprocal Rank Fusion (RRF)**: Merges dense and lexical results using the rank-reciprocal algorithm:
    $$RRF(d) = \sum_{c \in C} \frac{1}{k + rank_c(d)}$$
    (with default constant $k = 60$). RRF deduplicates chunks by stable identity and stores explicit provenance tracking (original ranks, scores, and active channels).

### 3.4 Degraded Mode & Fallback Signaling
To prevent silent runtime failures, the retriever attaches a `RetrievalExecutionMetadata` status report to each `KnowledgeBundle` containing:
*   `vector_store_mode`: `"qdrant"` or `"memory"`
*   `embedding_mode`: `"sentence-transformer"` or `"mock"`
*   `reranker_mode`: `"flashrank"` or `"lexical-fallback"`
*   `degraded_mode`: `True` if any fallback occurred (e.g. mock embedding or memory vector database)
*   `fallback_reasons`: Structured string warnings explaining why degraded status was engaged.

---

## 4. Test & Verification Execution Ledger

We ran the test suite using `python -m pytest tests/` with the python environment inside the virtualenv `venv` directory.

### 4.1 Test Run Status
*   **Total Tests Executed**: 50
*   **Total Tests Passed**: 50
*   **Total Tests Failed**: 0

### 4.2 Executed Knowledge Test Categories
1.  **Document Loader Ingests**:
    *   `test_document_loader`: Validates Yaml parsing, front matter keys, and metadata.
2.  **Heading chunker splits**:
    *   `test_heading_aware_chunker`: Tests section partitioning and sequential ID tracking.
3.  **Embedding providers**:
    *   `test_mock_embedding_provider`: Asserts seed stability and vector normalization L2.
    *   `test_sentence_transformer_provider_mocked` & `test_sentence_transformer_provider_invalid_init`: Asserts sentence transformer interface compliance, vector dimensions (384), batch embedding, and invalid model initialization.
4.  **Qdrant Adapter memory**:
    *   `test_qdrant_adapter_in_memory`: Verifies collection creation, upserts, deletes, and service filter queries.
5.  **Rerank Fallbacks**:
    *   `test_reranker_fallback`: Validates Jaccard overlap and heading boosts.
6.  **Lexical & Fusion Channels**:
    *   `test_bm25_lexical_retriever`: BM25 term frequency matching.
    *   `test_reciprocal_rank_fusion`: Rank merging and provenance calculations.
7.  **Retriever Coordinate**:
    *   `test_hybrid_retriever`: Asserts hybrid queries with evidence filtering, degraded mode signaling, chunk channel provenances, and KnowledgeBundle immutability.

---

## 5. Architectural Decisions & Deviations

*   **Pydantic Immutability**: All Knowledge schemas enforce `model_config = {"frozen": True}` and collection fields are typed as `tuple` to ensure absolute immutability.
*   **No Pickle Persistence**: Cache is volatile in-memory. Persistent caching will utilize SQLite or JSON instead of pickle.
*   **ST Provider Mocks**: Implemented monkeypatched sentence-transformer providers to run the unit tests completely offline.

---

## 6. Technical Debt, Future Enhancements, and Constraints

### 6.1 Current Technical Debt
*   **Memory Cache Volatility**: Cache is currently volatile in-memory.

### 6.2 Future Enhancements
*   **Disk Cache Backing**: Add a persistent SQLite/JSON disk cache file for caching embeddings.

### 6.3 Known Constraints
*   **No LLM usage**: Reasoning, LLM queries, and prompt compilation are completely omitted.

---

## 7. Future Phase Boundaries

### 7.1 Context Builder Boundary (Phase 6+)
The future Context Builder will be responsible for:
*   Combining the validated `EvidenceBundle` (Phase 4) and the `KnowledgeBundle` (Phase 5).
*   Enforcing strict context budgets (token limit pruning).
*   Removing duplicate context items and prioritizing relevant evidence citations.
*   Compiling a structured `InvestigationContext`.
It must not implement LLM queries or prompt construction.

### 7.2 Prompt Assembly Boundary (Phase 7+)
The future Prompt Assembly will be responsible for:
*   Consuming `InvestigationContext` objects.
*   Applying versioned prompt templates (such as XML abstractions).
*   Producing model-ready system and user messages.
It remains completely separated from LangGraph routing or LLM Gateway transports. Large inline prompt strings are prohibited inside LangGraph nodes.
---

## 8. Repository Revision & Exit Ledger

### 8.1 Repository Revision
*   **Active Branch**: `feature/phase-5-knowledge-layer`
*   **Refactoring Date**: 2026-07-08
*   **Execution Workspace**: `opsgraph-ai/`

### 8.2 Phase 5 Exit Checklist

*   `[x]` **RAG Interfaces Compile**: Models compile and assert typed schemas.
*   `[x]` **Genuine Hybrid Search**: Dense vector + BM25 Lexical + Reciprocal Rank Fusion (RRF) are active.
*   `[x]` **Degraded Mode Visibility**: Execution metadata exposes degraded flags.
*   `[x]` **All 50 Tests Pass**: Pytest suite reports 100% success.
*   `[x]` **Feature Branch Created**: Active on `feature/feature/phase-5-knowledge-layer`.
*   `[x]` **No Phase 6 Leakage**: No gateway or routing code has been created.
