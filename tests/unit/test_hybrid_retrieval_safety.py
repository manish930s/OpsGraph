import pytest
from unittest.mock import MagicMock, patch
from app.services.knowledge.retriever import HybridRetriever
from app.services.knowledge.fusion import ReciprocalRankFusion
from app.services.knowledge.reranker import FlashRankReranker
from app.services.knowledge.cache import KnowledgeCache
from app.schemas.knowledge import KnowledgeChunk
from app.services.knowledge import SentenceTransformerEmbeddingProvider

def test_lexical_only_rrf_fusion():
    """Verify that RRF handles empty dense results and yields correct lexical-only scores and provenance."""
    fuser = ReciprocalRankFusion(k=60)
    
    lexical_results = [
        {"id": "chunk1", "score": 1.5, "payload": {"content": "text 1", "heading": "h1"}},
        {"id": "chunk2", "score": 0.8, "payload": {"content": "text 2", "heading": "h2"}}
    ]
    
    fused = fuser.fuse(dense_results=[], lexical_results=lexical_results)
    
    assert len(fused) == 2
    # chunk1 was rank 1 in lexical (idx 0), rrf = 1 / (60 + 1) = 0.016393
    # chunk2 was rank 2 in lexical (idx 1), rrf = 1 / (60 + 2) = 0.016129
    assert fused[0]["id"] == "chunk1"
    assert fused[0]["score"] == 0.016393
    assert fused[1]["id"] == "chunk2"
    assert fused[1]["score"] == 0.016129
    
    # Check provenance
    prov = fused[0]["payload"]["_provenance"]
    assert prov["dense_rank"] is None
    assert prov["dense_score"] is None
    assert prov["lexical_rank"] == 1
    assert prov["lexical_score"] == 1.5
    assert prov["retrieval_channels"] == ["lexical"]


def test_lexical_only_reranking():
    """Verify that FlashRankReranker can process lexical-only candidates using Jaccard fallback or FlashRank."""
    reranker = FlashRankReranker()
    
    # Candidates with provenance payload
    chunks = [
        {
            "id": "chunk1",
            "score": 0.016393,
            "payload": {
                "content": "the system database is online and running",
                "heading": "database info",
                "_provenance": {"retrieval_channels": ["lexical"]}
            }
        },
        {
            "id": "chunk2",
            "score": 0.016129,
            "payload": {
                "content": "random unmatched message here",
                "heading": "other log",
                "_provenance": {"retrieval_channels": ["lexical"]}
            }
        }
    ]
    
    # Force use of overlap reranker to keep tests offline and fast
    with patch.object(reranker, "has_flashrank", False):
        reranked = reranker.rerank(query="database online", chunks=chunks, limit=2)
        assert len(reranked) == 2
        # chunk1 should have higher overlap score
        assert reranked[0][1]["id"] == "chunk1"
        assert reranked[0][0] > reranked[1][0]


def test_empty_dense_plus_non_empty_lexical():
    """Verify that retrieval succeeds when dense search yields empty candidates but BM25 returns results."""
    store = MagicMock()
    store.mode = "qdrant"
    store.search.return_value = [] # empty dense results
    
    class GeminiEmbeddingProvider:
        def get_embedding(self, query):
            return [0.1] * 768
    provider = GeminiEmbeddingProvider()
    
    lexical = MagicMock()
    lexical.search.return_value = [
        {"id": "chunk1", "score": 2.0, "payload": {"content": "text 1", "heading": "h1", "service_scope": "billing"}}
    ]
    
    reranker = FlashRankReranker()
    
    retriever = HybridRetriever(
        vector_store=store,
        embedding_provider=provider,
        reranker=reranker,
        cache=KnowledgeCache(),
        collection_name="temp_col",
        lexical_retriever=lexical
    )
    
    bundle = retriever.retrieve("query", limit=1)
    
    # Assert retriever did not crash, and returned the lexical chunk
    assert len(bundle.chunks) == 1
    assert bundle.chunks[0].chunk_id == "chunk1"
    # Verify metadata
    assert bundle.execution_metadata.vector_store_mode == "qdrant"
    assert bundle.execution_metadata.degraded_mode is False


def test_missing_fallback_collection():
    """Verify that a missing fallback collection in Qdrant propagates as a hard failure."""
    store = MagicMock()
    store.mode = "qdrant"
    # Simulate missing collection error
    store.search.side_effect = Exception("Collection not found")
    
    provider = MagicMock()
    provider.get_embedding.return_value = [0.1] * 768
    
    retriever = HybridRetriever(
        vector_store=store,
        embedding_provider=provider,
        reranker=FlashRankReranker(),
        cache=KnowledgeCache(),
        collection_name="temp_col"
    )
    
    # Check that error is propagated (hard failure)
    with pytest.raises(Exception) as excinfo:
        retriever.retrieve("query")
    assert "Collection not found" in str(excinfo.value)


def test_embedding_fallback_metadata():
    """Verify metadata when Gemini embedding fails and SentenceTransformer MPNet fallback is engaged."""
    provider = SentenceTransformerEmbeddingProvider(model_name="all-mpnet-base-v2")
    
    store = MagicMock()
    store.mode = "memory" # forces degraded_mode=True
    store.search.return_value = []
    
    with patch.object(provider, "get_embedding", return_value=[0.1]*768):
        retriever = HybridRetriever(
            vector_store=store,
            embedding_provider=provider,
            reranker=FlashRankReranker(),
            cache=KnowledgeCache(),
            collection_name="temp_col"
        )
        bundle = retriever.retrieve("query")
        # Assert metadata
        meta = bundle.execution_metadata
        assert meta.embedding_mode == "sentence-transformer-fallback"
        assert meta.degraded_mode is True
        assert len(meta.fallback_reasons) > 0
        assert "local in-memory fallback" in meta.fallback_reasons[0]
