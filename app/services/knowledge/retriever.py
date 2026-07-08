import logging
from app.schemas.evidence import EvidenceBundle
from app.schemas.knowledge import KnowledgeChunk, KnowledgeBundle
from app.services.knowledge.base_embedding import BaseEmbeddingProvider
from app.services.knowledge.vector_store_base import BaseVectorStore
from app.services.knowledge.reranker import FlashRankReranker
from app.services.knowledge.cache import KnowledgeCache

logger = logging.getLogger("opsgraph.knowledge.retriever")

class HybridRetriever:
    """
    Coordinating retriever that executes hybrid search, applying metadata filters
    informed by EvidenceBundles, caching embeddings, and reranking outputs.
    """
    def __init__(
        self,
        vector_store: BaseVectorStore,
        embedding_provider: BaseEmbeddingProvider,
        reranker: FlashRankReranker,
        cache: KnowledgeCache,
        collection_name: str = "knowledge_base"
    ):
        self.vector_store = vector_store
        self.embedding_provider = embedding_provider
        self.reranker = reranker
        self.cache = cache
        self.collection_name = collection_name

    def retrieve(
        self,
        query: str,
        evidence_bundle: EvidenceBundle | None = None,
        limit: int = 5
    ) -> KnowledgeBundle:
        """
        Executes cached vector similarity lookup with evidence filters, followed by FlashRank reranking.
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

        # 3. Resolve search results (cached)
        # Create a unique key combining query text and filters
        cache_key = f"{query}|filter={str(filter_metadata)}"
        search_results = self.cache.get_retrieval(cache_key)
        
        if search_results is None:
            logger.info("Search result cache miss. Querying vector store.")
            search_results = self.vector_store.search(
                collection_name=self.collection_name,
                vector=vector,
                limit=limit * 3,  # Retrieve more candidates for reranking
                filter_metadata=filter_metadata
            )
            self.cache.set_retrieval(cache_key, search_results)

        # 4. FlashRank Rerank
        reranked_tuples = self.reranker.rerank(query, search_results, limit=limit)

        # 5. Package into KnowledgeBundle
        chunks_list = []
        retrieval_scores = {}
        rerank_scores = {}

        # Build mapping dictionaries
        search_results_map = {item["id"]: item["score"] for item in search_results}

        for score, candidate in reranked_tuples:
            c_id = candidate["id"]
            payload = candidate.get("payload", {})
            
            # Map retrieval score
            retrieval_scores[c_id] = float(search_results_map.get(c_id, 0.0))
            rerank_scores[c_id] = float(score)

            chunk = KnowledgeChunk(
                chunk_id=c_id,
                document_id=payload.get("document_id", ""),
                section=payload.get("section", ""),
                heading=payload.get("heading", ""),
                content=payload.get("content", ""),
                metadata=payload
            )
            chunks_list.append(chunk)

        summary = (
            f"Retrieved {len(chunks_list)} chunks from query '{query}'. "
            f"Applied filters: {filter_metadata}. Cited evidence references: {evidence_references}."
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
            search_summary=summary
        )
