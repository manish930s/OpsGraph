# Enterprise Knowledge Layer Architecture (RAG)
**Document Status:** Finalized (Phase 5 Stabilization Complete)  
**Authoritative Reference:** Ingestion, Indexing, Hybrid Search, and Fusion Design  

---

## 1. Architecture Flow

### 1.1 Ingestion Flow
```
Knowledge Sources (Markdown, JSON, TXT)
          |
          v
    Document Loader (YAML parsing)
          |
          v
      Normalizer (Canonical Schema)
          |
          v
    Metadata Extraction (Tags, Category)
          |
          v
   Deterministic Chunker (Heading-aware)
          |
          v
   Embedding Provider (Mock / ST)
          |
          v
     Vector Store (Qdrant adapter)
```

### 1.2 Query Execution Flow
```
Validated EvidenceBundle
          |
          v
Retrieval Scope Builder (Service filters)
          |
    +-----+-----+
    |           |
    v           v
Dense Search   Lexical Search (BM25)
    |           |
    +-----+-----+
          |
          v
Deterministic Reciprocal Rank Fusion (RRF)
          |
          v
FlashRank Reranking (with Jaccard fallback)
          |
          v
  KnowledgeBundle (Immutable Output)
```

---

## 2. Ingestion & Document Normalization
Documents are ingested from Markdown formats with standard YAML front-matter headers. The parser (`KnowledgeLoader`):
1.  Extracts front-matter metadata parameters (`document_id`, `document_type`, `version`, `title`, `service_scope`, etc.) into a canonical schema.
2.  Normalizes content strings, eliminating raw platform dependencies or local file paths.
3.  Exposes clean `KnowledgeDocument` representations.

---

## 3. Chunking Strategy
To retain strict semantic limits and operational contexts:
*   **Heading-Aware Splitting**: The `HeadingAwareChunker` splits Markdown files by their heading levels (`# `, `## `, `### `). Sub-sections like `# Symptoms`, `# Investigation Steps`, and `# Remediation Options` become standalone chunks.
*   **Paragraph Preservation**: Paragraphs are not sliced randomly; splitting occurs cleanly at line breaks.
*   **Deterministic Chunk IDs**: Identifiers are assigned sequentially: `<DOCUMENT_ID>-CHUNK-<SEQ_NUM>` (e.g. `RB-DB-001-CHUNK-001`).
*   **Metadata Inheritance**: Every chunk inherits root front-matter attributes, such as `service_scope` and `version`, along with structural metadata like `section` name and `heading` line.

---

## 4. Embedding Strategy
The `BaseEmbeddingProvider` interface decouples vector generation from underlying provider clients:
*   **MockEmbeddingProvider**: Computes L2-normalized float vectors of configured dimensions (default: 3072) by seeding a pseudorandom number generator with the SHA-256 hash of the content. This yields deterministic, scale-invariant vectors that simulate cosine similarity calculations entirely offline.
*   **SentenceTransformerEmbeddingProvider**: Real local embedding provider using the `sentence_transformers` library. Generates normalized L2 unit vectors and supports configurable model names (default: `all-MiniLM-L6-v2`) and execution devices (`cpu` / `cuda`).

---

## 5. Vector Store Abstraction
Decouples vector operations from specific databases via `BaseVectorStore`:
*   **QdrantAdapter**: Instantiates `QdrantClient(location=":memory:")` for offline testing/containers or connects via hosts.
*   **UUID Mapping Constraint**: Qdrant requires string point IDs to be valid UUIDs. The adapter implements a transparent, deterministic mapping using `uuid.uuid5` on string chunk IDs, saving the original chunk ID in the payload. It automatically reconstructs the original chunk ID during query retrieval.
*   **Future Databases**: Pinecone, pgvector, Weaviate, or Milvus can be added by implementing `BaseVectorStore`.

---

## 6. Hybrid Retrieval Channel & Reciprocal Rank Fusion
To guarantee maximum production retrieval quality, the retrievals query two independent channels:
1.  **Dense Retrieval Channel**: Cosine similarity vector search over the Qdrant database.
2.  **Lexical Retrieval Channel**: A deterministic `BM25LexicalRetriever` scoring matching chunks based on term-frequency and inverse document frequency statistics, utilizing the same metadata scope filters.
3.  **Reciprocal Rank Fusion (RRF)**: Merges dense and lexical results using the rank-reciprocal algorithm:
    $$RRF(d) = \sum_{c \in C} \frac{1}{k + rank_c(d)}$$
    (with default constant $k = 60$). RRF deduplicates chunks by stable identity and stores explicit provenance tracking (original ranks, scores, and active channels).

---

## 7. Reranking & Fallback Behavior
Candidates fused via RRF are passed to the `FlashRankReranker`:
*   **FlashRank cross-encoder**: Scores fused documents using pre-trained transformer rankers.
*   **Jaccard Fallback**: If FlashRank is unavailable or throws execution exceptions, the system automatically falls back to a deterministic Jaccard word-overlap similarity score.
*   **No Silent Fallbacks**: Fallback states are logged as warnings and propagated inside the bundle execution metadata.

---

## 8. Degraded Mode & Runtime Signaling
To prevent silent runtime failures, the retriever attaches a `RetrievalExecutionMetadata` status report to each `KnowledgeBundle` containing:
*   `vector_store_mode`: `"qdrant"` or `"memory"`
*   `embedding_mode`: `"sentence-transformer"` or `"mock"`
*   `reranker_mode`: `"flashrank"` or `"lexical-fallback"`
*   `degraded_mode`: `True` if any fallback occurred (e.g. mock embedding or memory vector database)
*   `fallback_reasons`: Structured string warnings explaining why degraded status was engaged.

---

## 9. Caching Policy
Exposed via `KnowledgeCache`:
*   *Embeddings*: Caches text hashes to avoid redundant embedding model API calls.
*   *Retrieval results*: Caches vector query keys to speed up repeated queries.
*   **Immutability**: Cached objects are read-only.
*   **No Pickle Persistence**: Pickle-based serialization is prohibited. Caching is currently volatile in-memory. For future persistent caching, safe options like SQLite or JSON serialization will be implemented.
*   No caching of secrets, prompts, or LLM outputs is allowed.

---

## 10. Future Phase Boundaries

### 1.1 Architectural Boundary Diagram
```
EvidenceBundle ----+
                   |
KnowledgeBundle ---+
                   |
                   v
            Context Builder
                   |
                   v
          InvestigationContext
                   |
                   v
            Prompt Assembly
                   |
                   v
               Guardrails
                   |
                   v
              LLM Gateway
```

### 10.2 Context Builder Boundary
The future Context Builder (Phase 6+) will be responsible for:
*   Combining the validated `EvidenceBundle` (Phase 4) and the `KnowledgeBundle` (Phase 5).
*   Enforcing strict context budgets (token limit pruning).
*   Removing duplicate context items and prioritizing relevant evidence citations.
*   Compiling a structured `InvestigationContext`.
It must not implement LLM queries or prompt construction.

### 10.3 Prompt Assembly Boundary
The future Prompt Assembly (Phase 7+) will be responsible for:
*   Consuming `InvestigationContext` objects.
*   Applying versioned prompt templates (such as XML abstractions).
*   Producing model-ready system and user messages.
It remains completely separated from LangGraph routing or LLM Gateway transports. Large inline prompt strings are prohibited inside LangGraph nodes.
