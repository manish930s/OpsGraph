import pytest
from pathlib import Path
from pydantic import ValidationError as PydanticValidationError
from app.config import settings
from app.schemas.common import TimeWindow
from app.schemas.evidence import Evidence, EvidenceProvenance, EvidenceBundle, ConfidenceSummary, ConfidenceComponents
from app.common.enums import SourceType
from app.services.knowledge import (
    KnowledgeLoader,
    HeadingAwareChunker,
    MockEmbeddingProvider,
    QdrantVectorStoreAdapter,
    FlashRankReranker,
    KnowledgeCache,
    HybridRetriever,
)

@pytest.fixture
def runbook_path():
    # Runbook path is relative to the workspace data folder
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

def test_load_directory_missing():
    loader = KnowledgeLoader()
    docs = loader.load_directory(Path("nonexistent/knowledge/base"))
    assert docs == []

# --- 2. Chunker Tests ---

def test_heading_aware_chunker(runbook_path):
    loader = KnowledgeLoader()
    doc = loader.load_markdown(runbook_path)

    chunker = HeadingAwareChunker(max_chunk_chars=500, overlap_chars=50)
    chunks = chunker.chunk_document(doc)

    assert len(chunks) > 0
    assert chunks[0].chunk_id == "RB-DB-001-CHUNK-001"
    assert chunks[0].document_id == "RB-DB-001"
    
    # Assert tag and metadata inheritance
    assert "checkout-service" in chunks[0].metadata["service_scope"]
    assert chunks[0].metadata["version"] == "1.0"
    
    # Assert section categorization
    sections = {c.section for c in chunks}
    assert "Symptoms" in sections
    assert "Investigation Steps" in sections

# --- 3. Embedding Interface Tests ---

def test_embedding_provider():
    provider = MockEmbeddingProvider(dimension=128)
    
    # Vector generation check
    vec1 = provider.get_embedding("Database latency saturated")
    assert len(vec1) == 128
    
    # Verify seed stability (identical text yields identical vector)
    vec2 = provider.get_embedding("Database latency saturated")
    assert vec1 == vec2

    # Check vector normalization (L2 norm should be close to 1.0)
    import numpy as np
    norm = np.linalg.norm(vec1)
    assert pytest.approx(norm, abs=1e-5) == 1.0

# --- 4. Qdrant Adapter Tests ---

def test_qdrant_adapter_in_memory():
    # Use memory adapter fallback
    store = QdrantVectorStoreAdapter()
    assert store.health_check() is True

    col_name = "test_collection"
    store.create_collection(col_name, vector_size=64)

    # Upsert points
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

    # Search without filter
    res = store.search(col_name, vector=[0.1] * 64, limit=2)
    assert len(res) == 2
    assert res[0]["id"] == "doc1-chunk1"

    # Search with service filter
    res_filtered = store.search(
        col_name,
        vector=[0.1] * 64,
        limit=2,
        filter_metadata={"service_scope": "payment-service"}
    )
    assert len(res_filtered) == 1
    assert res_filtered[0]["id"] == "doc1-chunk2"

    store.delete_collection(col_name)

# --- 5. Reranker Tests ---

def test_reranker_fallback():
    reranker = FlashRankReranker()
    
    query = "database pool saturated"
    candidates = [
        {
            "id": "chunk1",
            "payload": {"content": "This runs database commands", "heading": "# Description"},
            "score": 0.5
        },
        {
            "id": "chunk2",
            "payload": {"content": "Checkout service handles queries", "heading": "# Overview"},
            "score": 0.4
        },
        {
            "id": "chunk3",
            "payload": {"content": "Database pool saturation causes wait exceptions", "heading": "# Database Connection Pool Exhaustion"},
            "score": 0.3
        }
    ]

    res = reranker.rerank(query, candidates, limit=2)
    assert len(res) == 2
    
    # Fallback overlap + heading boost should elevate chunk3 containing "database pool" and "Database Connection Pool"
    assert res[0][1]["id"] == "chunk3"
    assert res[0][0] > res[1][0]

# --- 6. Caching Tests ---

def test_knowledge_cache():
    cache = KnowledgeCache()
    assert cache.get_embedding("test") is None

    vec = [0.1, 0.2, 0.3]
    cache.set_embedding("test", vec)
    assert cache.get_embedding("test") == vec

    assert cache.get_retrieval("q1") is None
    results = [{"id": "chunk1", "score": 0.9}]
    cache.set_retrieval("q1", results)
    assert cache.get_retrieval("q1") == results

    cache.clear()
    assert cache.get_embedding("test") is None

# --- 7. Hybrid Retriever & Bundle Immutability Tests ---

def test_hybrid_retriever(runbook_path):
    # Setup bundle context
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

    # Setup RAG index
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

    # Retriever instance
    retriever = HybridRetriever(
        vector_store=store,
        embedding_provider=provider,
        reranker=FlashRankReranker(),
        cache=KnowledgeCache(),
        collection_name=col_name
    )

    # Perform hybrid search
    bundle = retriever.retrieve(query="connection timeout wait latency", evidence_bundle=evidence_bundle, limit=2)
    
    assert len(bundle.chunks) > 0
    assert bundle.applied_filters == {"service_scope": ["checkout-service"]}
    assert "LOG-EV-SCN-0001" in bundle.evidence_references

    # Assert immutability of KnowledgeBundle
    with pytest.raises((PydanticValidationError, TypeError)):
        bundle.search_summary = "new summary"

    with pytest.raises((PydanticValidationError, TypeError)):
        bundle.chunks[0] = None

    store.delete_collection(col_name)
