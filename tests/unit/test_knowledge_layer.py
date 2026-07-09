import pytest
import hashlib
from pathlib import Path
from pydantic import ValidationError as PydanticValidationError
from app.config import settings
from app.schemas.common import TimeWindow
from app.schemas.evidence import Evidence, EvidenceProvenance, EvidenceBundle, ConfidenceSummary, ConfidenceComponents
from app.common.enums import SourceType
from app.schemas.knowledge import KnowledgeChunk, RetrievalExecutionMetadata
from app.services.knowledge import (
    KnowledgeLoader,
    HeadingAwareChunker,
    MockEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
    QdrantVectorStoreAdapter,
    FlashRankReranker,
    KnowledgeCache,
    HybridRetriever,
)
from app.services.knowledge.lexical import BM25LexicalRetriever
from app.services.knowledge.fusion import ReciprocalRankFusion

@pytest.fixture
def runbook_path():
    return settings.GENERATED_DATA_DIR.parent / "knowledge" / "runbooks" / "RB-DB-001.md"

# --- 1. Loader & Normalizer Tests ---

def test_document_loader(runbook_path):
    loader = KnowledgeLoader()
    doc = loader.load_markdown(runbook_path)
    assert doc.document_id == "RB-DB-001"
    assert doc.document_type == "runbook"
    assert doc.title == "Database Connection Pool Exhaustion"
    assert "checkout-service" in doc.tags
    assert doc.metadata.get("fault_category") == "database_connection_pool"
    assert "Symptoms" in doc.content

# --- 2. Chunker Tests ---

def test_heading_aware_chunker(runbook_path):
    loader = KnowledgeLoader()
    doc = loader.load_markdown(runbook_path)
    chunker = HeadingAwareChunker(max_chunk_chars=500, overlap_chars=50)
    chunks = chunker.chunk_document(doc)

    assert len(chunks) > 0
    assert chunks[0].chunk_id == "RB-DB-001-CHUNK-001"
    assert "checkout-service" in chunks[0].metadata["service_scope"]
    assert chunks[0].metadata["version"] == "1.0"

# --- 3. Embedding Provider Tests ---

def test_mock_embedding_provider():
    provider = MockEmbeddingProvider(dimension=128)
    vec1 = provider.get_embedding("Database latency saturated")
    assert len(vec1) == 128
    vec2 = provider.get_embedding("Database latency saturated")
    assert vec1 == vec2

    import numpy as np
    norm = np.linalg.norm(vec1)
    assert pytest.approx(norm, abs=1e-5) == 1.0

def test_sentence_transformer_provider_mocked(monkeypatch):
    # Mock SentenceTransformer class to avoid network downloads in tests
    class MockST:
        def __init__(self, model_name, device=None):
            if "nonexistent" in model_name:
                raise ValueError("Model does not exist")
            self.model_name = model_name
            self.device = device
        def encode(self, texts, convert_to_numpy=True):
            import numpy as np
            if isinstance(texts, list):
                return np.random.randn(len(texts), 384)
            return np.random.randn(384)

    # Monkeypatch the import
    import sys
    import types
    st_module = types.ModuleType("sentence_transformers")
    st_module.SentenceTransformer = MockST
    sys.modules["sentence_transformers"] = st_module

    # Test initialization
    provider = SentenceTransformerEmbeddingProvider(model_name="all-MiniLM-L6-v2", device="cpu")
    vec = provider.get_embedding("test query")
    assert len(vec) == 384

    batch_vecs = provider.get_embeddings(["text1", "text2"])
    assert len(batch_vecs) == 2
    assert len(batch_vecs[0]) == 384

def test_sentence_transformer_provider_invalid_init():
    # Expect initialization failure on bad provider import / config
    with pytest.raises(RuntimeError):
        SentenceTransformerEmbeddingProvider(model_name="nonexistent-model-name-for-error", device="cuda-invalid")

# --- 4. Lexical Scorer & Fusion Tests ---

def test_bm25_lexical_retriever():
    retriever = BM25LexicalRetriever()
    chunks = [
        KnowledgeChunk(
            chunk_id="chunk1",
            document_id="doc1",
            section="Symptoms",
            heading="Database",
            content="Pool wait latency connection sat",
            metadata={"service_scope": ["checkout-service"]}
        ),
        KnowledgeChunk(
            chunk_id="chunk2",
            document_id="doc1",
            section="Remediation",
            heading="Rollback",
            content="Restore previous settings",
            metadata={"service_scope": ["payment-service"]}
        )
    ]
    retriever.index_chunks(chunks)

    # Term matches chunk1 content
    res = retriever.search("latency wait", limit=2)
    assert len(res) == 1
    assert res[0]["id"] == "chunk1"

    # Filter excludes chunk1
    res_filtered = retriever.search("latency", limit=2, filter_metadata={"service_scope": ["payment-service"]})
    assert len(res_filtered) == 0

def test_reciprocal_rank_fusion():
    fuser = ReciprocalRankFusion(k=60)
    dense_results = [
        {"id": "chunk1", "score": 0.9, "payload": {"tag": "d"}},
        {"id": "chunk2", "score": 0.8, "payload": {"tag": "d"}}
    ]
    lexical_results = [
        {"id": "chunk2", "score": 12.0, "payload": {"tag": "d"}},
        {"id": "chunk3", "score": 8.0, "payload": {"tag": "d"}}
    ]

    fused = fuser.fuse(dense_results, lexical_results)
    
    # chunk2 was returned by both and should have high fusion score
    # RRF(chunk2) = 1/(60+2) [dense rank 2] + 1/(60+1) [lexical rank 1]
    assert len(fused) == 3
    assert fused[0]["id"] == "chunk2"
    
    # Inspect explicit provenance fields
    prov = fused[0]["payload"]["_provenance"]
    assert prov["chunk_id"] == "chunk2"
    assert "dense" in prov["retrieval_channels"]
    assert "lexical" in prov["retrieval_channels"]
    assert prov["dense_rank"] == 2
    assert prov["lexical_rank"] == 1

# --- 5. Qdrant Adapter Tests ---

def test_qdrant_adapter_in_memory():
    store = QdrantVectorStoreAdapter()
    assert store.health_check() is True
    assert store.mode == "memory"

    col_name = "test_collection"
    store.create_collection(col_name, vector_size=64)

    points = [
        {
            "id": "doc1-chunk1",
            "vector": [0.1] * 64,
            "payload": {"content": "Checkout latency is high", "service_scope": ["checkout-service"]}
        },
        {
            "id": "doc1-chunk2",
            "vector": [-0.9] * 64,
            "payload": {"content": "Payment database is healthy", "service_scope": ["payment-service"]}
        }
    ]
    store.upsert(col_name, points)

    res = store.search(col_name, vector=[0.1] * 64, limit=2)
    assert len(res) == 2
    assert res[0]["id"] == "doc1-chunk1"

    store.delete_collection(col_name)

# --- 6. Hybrid Retriever & Bundle Stabilization Tests ---

def test_hybrid_retriever(runbook_path):
    conf = ConfidenceSummary(
        score=0.9,
        band="HIGH",
        explanation=["Coverage is good"],
        components=ConfidenceComponents(
            source_reliability=1.0, cross_source_agreement=1.0, timeline_consistency=1.0,
            topology_consistency=1.0, evidence_coverage=1.0, deployment_consistency=1.0,
            observation_completeness=1.0, contradictions=0.0
        ),
        supporting_evidence_count=1,
        conflicting_evidence_count=0,
        missing_evidence_categories=[]
    )
    
    ev = Evidence(
        evidence_id="LOG-EV-SCN-0001",
        incident_id="INC-0042",
        scenario_id="SCN-001",
        source_type=SourceType.LOG,
        service="checkout-service",
        observation="Database pool exhaust",
        source_record_ids=["r1"],
        provenance=EvidenceProvenance(dataset="logs", record_reference="r1"),
        time_window=TimeWindow(start="2026-01-15T14:00:00Z", end="2026-01-15T14:00:00Z")
    )
    
    evidence_bundle = EvidenceBundle(
        evidence_list=(ev,),
        timeline=(ev,),
        confidence_summary=conf,
        validation_status="valid",
        coverage_summary={"checkout-service": ["log"]}
    )

    loader = KnowledgeLoader()
    doc = loader.load_markdown(runbook_path)
    chunker = HeadingAwareChunker()
    chunks = chunker.chunk_document(doc)

    store = QdrantVectorStoreAdapter()
    col_name = "test_runbooks"
    store.create_collection(col_name, vector_size=128)

    provider = MockEmbeddingProvider(dimension=128)
    
    points = []
    for c in chunks:
        points.append({
            "id": c.chunk_id,
            "vector": provider.get_embedding(c.content),
            "payload": {
                "document_id": c.document_id,
                "section": c.section,
                "heading": c.heading,
                "content": c.content,
                "service_scope": c.metadata["service_scope"],
                "version": c.metadata["version"]
            }
        })
    store.upsert(col_name, points)

    retriever = HybridRetriever(
        vector_store=store,
        embedding_provider=provider,
        reranker=FlashRankReranker(),
        cache=KnowledgeCache(),
        collection_name=col_name
    )
    
    # Index chunks in lexical index for hybrid search
    retriever.index_chunks(chunks)

    # Perform hybrid search
    bundle = retriever.retrieve(query="connection pool wait latency", evidence_bundle=evidence_bundle, limit=2)
    
    assert len(bundle.chunks) > 0
    assert bundle.applied_filters == {"service_scope": ["checkout-service"]}
    assert "LOG-EV-SCN-0001" in bundle.evidence_references

    # Check execution metadata degraded mode signaling
    assert bundle.execution_metadata.degraded_mode is True
    assert bundle.execution_metadata.vector_store_mode == "memory"
    assert bundle.execution_metadata.embedding_mode == "mock"
    assert bundle.execution_metadata.reranker_mode in ("flashrank", "lexical-fallback")
    assert len(bundle.execution_metadata.fallback_reasons) > 0

    # Check chunk retrieval channel provenance exists
    assert bundle.chunks[0].provenance is not None
    assert bundle.chunks[0].provenance.fusion_score > 0.0
    assert "dense" in bundle.chunks[0].provenance.retrieval_channels

    # Assert immutability
    with pytest.raises((PydanticValidationError, TypeError)):
        bundle.search_summary = "new summary"

    with pytest.raises((PydanticValidationError, TypeError)):
        bundle.chunks[0] = None

    store.delete_collection(col_name)
