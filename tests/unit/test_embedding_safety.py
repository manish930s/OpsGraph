import pytest
import sys
import types
from unittest.mock import MagicMock, patch
from pydantic import ValidationError
from app.config import Settings, settings

# Mock sentence_transformers module globally before any imports that might trigger it
mock_st_module = types.ModuleType("sentence_transformers")
class MockSentenceTransformer:
    def __init__(self, model_name=None, device=None):
        self.model_name = model_name
        self.device = device
    def encode(self, texts, show_progress_bar=False, convert_to_numpy=True):
        import numpy as np
        if isinstance(texts, list):
            return np.random.randn(len(texts), 768)
        return np.random.randn(768)
mock_st_module.SentenceTransformer = MockSentenceTransformer
sys.modules["sentence_transformers"] = mock_st_module

from app.services.retrieval.embedding import (
    _init,
    _probe_gemini,
    _load_fallback,
    get_embedding_dim,
    get_active_collection_name
)

@pytest.fixture(autouse=True)
def reset_embedding_state():
    """Reset the global singleton state in embedding.py between tests."""
    import app.services.retrieval.embedding as emb
    emb._active_model = None
    emb._model_type = None

def test_settings_separation_validation():
    """Verify that pydantic settings validates model separation and dimensions."""
    # 1. Collision between embedding model and gateway model
    with pytest.raises(ValidationError) as exc:
        Settings(
            GEMINI_EMBEDDING_MODEL="gemini-2.5-flash",
            GEMINI_MODEL="gemini-2.5-flash"
        )
    assert "cannot be the same as Gemini LLM generation model" in str(exc.value)

    # 2. Non-positive dimensions
    with pytest.raises(ValidationError) as exc:
        Settings(GEMINI_EMBEDDING_DIMENSION=-10)
    assert "GEMINI_EMBEDDING_DIMENSION must be positive" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        Settings(LOCAL_EMBEDDING_DIMENSION=0)
    assert "LOCAL_EMBEDDING_DIMENSION must be positive" in str(exc.value)

@patch("app.services.retrieval.embedding.GoogleGenerativeAIEmbeddings")
def test_gemini_embedding_probe_success(mock_embeddings_class):
    """Verify that successful Gemini probe configures gemini mode and dimension."""
    mock_model = MagicMock()
    mock_model.embed_query.return_value = [0.1] * 3072
    mock_embeddings_class.return_value = mock_model

    with patch("app.config.settings.GEMINI_API_KEY", "dummy-key"), \
         patch("app.config.settings.GEMINI_EMBEDDING_DIMENSION", 3072):
        
        dim = get_embedding_dim()
        assert dim == 3072
        
        col = get_active_collection_name()
        assert "models_gemini-embedding-2-preview_3072" in col

@patch("app.services.retrieval.embedding.GoogleGenerativeAIEmbeddings")
def test_fallback_embedding_on_gemini_failure(mock_embeddings_class):
    """Verify that a failed Gemini probe falls back to local sentence-transformers."""
    # Gemini throws exception
    mock_embeddings_class.side_effect = Exception("API Key invalid or quota exceeded")

    with patch("app.config.settings.LOCAL_EMBEDDING_DIMENSION", 768), \
         patch("app.config.settings.LOCAL_EMBEDDING_MODEL", "all-mpnet-base-v2"):
        
        dim = get_embedding_dim()
        assert dim == 768
        
        col = get_active_collection_name()
        assert "all-mpnet-base-v2_768" in col


from app.services.knowledge import GeminiEmbeddingProvider, HybridRetriever, KnowledgeCache, FlashRankReranker, QdrantVectorStoreAdapter
from app.schemas.evidence import EvidenceBundle, ConfidenceSummary, ConfidenceComponents
from app.schemas.knowledge import KnowledgeChunk

@patch("langchain_google_genai.GoogleGenerativeAIEmbeddings")
def test_gemini_embedding_provider_retriever_metadata(mock_genai_embeddings):
    """Verify that GeminiEmbeddingProvider maps correctly to 'gemini' in RetrievalExecutionMetadata."""
    mock_model = MagicMock()
    mock_model.embed_query.return_value = [0.5] * 3072
    mock_genai_embeddings.return_value = mock_model

    with patch("app.config.settings.GEMINI_API_KEY", "valid-fake-key"):
        provider = GeminiEmbeddingProvider(model_name="models/gemini-embedding-2-preview")
        
        # Test vector dimension and query embedding
        vec = provider.get_embedding("query")
        assert len(vec) == 3072
        assert mock_model.embed_query.call_count == 1

        # Test retriever metadata embedding_mode reporting
        store = QdrantVectorStoreAdapter()
        store.create_collection("temp_col", 3072)
        
        # Mock Reranker to avoid complex model loads
        mock_reranker = MagicMock(spec=FlashRankReranker)
        mock_reranker.mode = "flashrank"
        mock_reranker.rerank.return_value = []

        retriever = HybridRetriever(
            vector_store=store,
            embedding_provider=provider,
            reranker=mock_reranker,
            cache=KnowledgeCache(),
            collection_name="temp_col"
        )
        
        bundle = retriever.retrieve("search query", limit=1)
        assert bundle.execution_metadata.embedding_mode == "gemini"
        
        store.delete_collection("temp_col")


from app.services.knowledge import SentenceTransformerEmbeddingProvider

def test_sentence_transformer_metadata_mapping():
    """Verify that SentenceTransformerEmbeddingProvider maps model names to correct modes."""
    # 1. Dev Model (all-MiniLM-L6-v2)
    provider = SentenceTransformerEmbeddingProvider(model_name="all-MiniLM-L6-v2")
    with patch.object(provider, "get_embedding", return_value=[0.1]*384):
        store = MagicMock()
        store.mode = "qdrant"
        store.search.return_value = []
        
        mock_reranker = MagicMock(spec=FlashRankReranker)
        mock_reranker.mode = "flashrank"
        mock_reranker.rerank.return_value = []

        retriever = HybridRetriever(
            vector_store=store,
            embedding_provider=provider,
            reranker=mock_reranker,
            cache=KnowledgeCache(),
            collection_name="temp_col"
        )
        bundle = retriever.retrieve("query", limit=1)
        assert bundle.execution_metadata.embedding_mode == "sentence-transformer"

    # 2. Fallback Model (all-mpnet-base-v2)
    provider = SentenceTransformerEmbeddingProvider(model_name="all-mpnet-base-v2")
    with patch.object(provider, "get_embedding", return_value=[0.1]*768):
        store = MagicMock()
        store.mode = "qdrant"
        store.search.return_value = []
        
        mock_reranker = MagicMock(spec=FlashRankReranker)
        mock_reranker.mode = "flashrank"
        mock_reranker.rerank.return_value = []

        retriever = HybridRetriever(
            vector_store=store,
            embedding_provider=provider,
            reranker=mock_reranker,
            cache=KnowledgeCache(),
            collection_name="temp_col"
        )
        bundle = retriever.retrieve("query", limit=1)
        assert bundle.execution_metadata.embedding_mode == "sentence-transformer-fallback"
