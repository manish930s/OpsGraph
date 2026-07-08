import logging
from app.schemas.evidence import EvidenceBundle
from app.schemas.knowledge import KnowledgeChunk, KnowledgeBundle, RetrievalChannelProvenance, RetrievalExecutionMetadata
from app.services.knowledge.base_embedding import BaseEmbeddingProvider, SentenceTransformerEmbeddingProvider
from app.services.knowledge.vector_store_base import BaseVectorStore
from app.services.knowledge.reranker import FlashRankReranker
from app.services.knowledge.cache import KnowledgeCache
from app.services.knowledge.lexical import BM25LexicalRetriever
from app.services.knowledge.fusion import ReciprocalRankFusion

logger = logging.getLogger("opsgraph.knowledge.retriever")

class HybridRetriever:
    """
    Coordinating retriever executing genuine hybrid retrieval (Dense + Lexical channels),
    applying Reciprocal Rank Fusion, running cross-encoder reranking, and signaling runtime status.
    """
    def __init__(
        self,
        vector_store: BaseVectorStore,
        embedding_provider: BaseEmbeddingProvider,
        reranker: FlashRankReranker,
        cache: KnowledgeCache,
        collection_name: str = "knowledge_base",
        lexical_retriever: BM25LexicalRetriever | None = None
    ):
        self.vector_store = vector_store
        self.embedding_provider = embedding_provider
        self.reranker = reranker
        self.cache = cache
        self.collection_name = collection_name
        self.lexical_retriever = lexical_retriever or BM25LexicalRetriever()
        self.fuser = ReciprocalRankFusion()

    def index_chunks(self, chunks: list[KnowledgeChunk]) -> None:
        """
        Indexes chunks in the local lexical retrieval index.
        """
        self.lexical_retriever.index_chunks(chunks)

    def retrieve(
        self,
        query: str,
        evidence_bundle: EvidenceBundle | None = None,
        limit: int = 5
    ) -> KnowledgeBundle:
        """
        Executes hybrid search combining dense similarity and lexical channels,
        fuses candidates using RRF, reranks results, and returns an immutable KnowledgeBundle.
        """
        logger.info(f"Retrieval request query: '{query}'")
        
        # 1. Build metadata filter using evidence coverage
        filter_metadata = {}
        evidence_references = []
        if evidence_bundle:
            # Extract covered services
            covered_services = list(evidence_bundle.coverage_summary.keys())
            if covered_services:
                filter_metadata["service_scope"] = covered_services
            
            # Map evidence references
            evidence_references = [ev.evidence_id for ev in evidence_bundle.evidence_list]

        # 2. Resolve embedding (cached)
        vector = self.cache.get_embedding(query)
        if vector is None:
            logger.info("Embedding cache miss. Invoking provider.")
            vector = self.embedding_provider.get_embedding(query)
            self.cache.set_embedding(query, vector)

        # 3. Dense Retrieval Channel (cached)
        cache_key_dense = f"dense|{query}|filter={str(filter_metadata)}"
        dense_results = self.cache.get_retrieval(cache_key_dense)
        if dense_results is None:
            logger.info("Dense search cache miss. Querying vector store.")
            dense_results = self.vector_store.search(
                collection_name=self.collection_name,
                vector=vector,
                limit=limit * 3,  # Retrieve candidate set
                filter_metadata=filter_metadata
            )
            self.cache.set_retrieval(cache_key_dense, dense_results)

        # 4. Lexical Retrieval Channel (cached)
        cache_key_lexical = f"lexical|{query}|filter={str(filter_metadata)}"
        lexical_results = self.cache.get_retrieval(cache_key_lexical)
        if lexical_results is None:
            logger.info("Lexical search cache miss. Querying BM25 index.")
            lexical_results = self.lexical_retriever.search(
                query=query,
                limit=limit * 3,
                filter_metadata=filter_metadata
            )
            self.cache.set_retrieval(cache_key_lexical, lexical_results)

        # 5. Deterministic Reciprocal Rank Fusion
        fused_candidates = self.fuser.fuse(dense_results, lexical_results)

        # 6. Reranking on fused candidate set
        reranked_tuples = self.reranker.rerank(query, fused_candidates, limit=limit)

        # 7. Package into KnowledgeBundle Chunks
        chunks_list = []
        retrieval_scores = {}
        rerank_scores = {}

        # Mapping dictionary to find fusion scores
        fused_map = {item["id"]: item["score"] for item in fused_candidates}

        for score, candidate in reranked_tuples:
            c_id = candidate["id"]
            payload = candidate.get("payload", {})
            
            # Map fusion retrieval score and final rerank score
            retrieval_scores[c_id] = float(fused_map.get(c_id, 0.0))
            rerank_scores[c_id] = float(score)

            # Rebuild channel provenance from payload
            prov_dict = payload.pop("_provenance", None)
            provenance = None
            if prov_dict:
                provenance = RetrievalChannelProvenance(
                    chunk_id=prov_dict.get("chunk_id", c_id),
                    dense_rank=prov_dict.get("dense_rank"),
                    dense_score=prov_dict.get("dense_score"),
                    lexical_rank=prov_dict.get("lexical_rank"),
                    lexical_score=prov_dict.get("lexical_score"),
                    fusion_score=prov_dict.get("fusion_score", 0.0),
                    retrieval_channels=prov_dict.get("retrieval_channels", [])
                )

            chunk = KnowledgeChunk(
                chunk_id=c_id,
                document_id=payload.get("document_id", ""),
                section=payload.get("section", ""),
                heading=payload.get("heading", ""),
                content=payload.get("content", ""),
                metadata=payload,
                provenance=provenance
            )
            chunks_list.append(chunk)

        # 8. Degraded Mode & Fallback Signaling
        vector_store_mode = getattr(self.vector_store, "mode", "qdrant")
        
        embedding_mode = "mock"
        if isinstance(self.embedding_provider, SentenceTransformerEmbeddingProvider):
            embedding_mode = "sentence-transformer"
            
        reranker_mode = self.reranker.mode

        fallback_reasons = []
        if vector_store_mode == "memory":
            fallback_reasons.append("Vector store is running in local in-memory fallback mode.")
        if embedding_mode == "mock":
            fallback_reasons.append("Embeddings generated via deterministic Mock provider.")
        if reranker_mode == "lexical-fallback":
            fallback_reasons.append("Reranking utilizing word-overlap Jaccard similarity fallback.")

        degraded_mode = len(fallback_reasons) > 0

        execution_metadata = RetrievalExecutionMetadata(
            vector_store_mode=vector_store_mode,
            embedding_mode=embedding_mode,
            reranker_mode=reranker_mode,
            degraded_mode=degraded_mode,
            fallback_reasons=fallback_reasons
        )

        summary = (
            f"Retrieved {len(chunks_list)} chunks from query '{query}' using hybrid search. "
            f"Applied filters: {filter_metadata}. Cited evidence references: {evidence_references}. "
            f"Degraded Mode: {degraded_mode}."
        )

        return KnowledgeBundle(
            chunks=tuple(chunks_list),
            metadata={
                "collection": self.collection_name,
                "query": query
            },
            retrieval_scores=retrieval_scores,
            rerank_scores=rerank_scores,
            applied_filters=filter_metadata,
            evidence_references=evidence_references,
            search_summary=summary,
            execution_metadata=execution_metadata
        )
