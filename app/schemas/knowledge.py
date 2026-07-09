from pydantic import BaseModel, Field

class KnowledgeDocument(BaseModel):
    model_config = {"frozen": True}
    document_id: str
    document_type: str
    source_path: str
    version: str | None = None
    title: str
    section: str | None = None
    language: str = "en"
    last_updated: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    content: str

class RetrievalChannelProvenance(BaseModel):
    model_config = {"frozen": True}
    chunk_id: str
    dense_rank: int | None = None
    dense_score: float | None = None
    lexical_rank: int | None = None
    lexical_score: float | None = None
    fusion_score: float
    retrieval_channels: list[str] = Field(default_factory=list)

class KnowledgeChunk(BaseModel):
    model_config = {"frozen": True}
    chunk_id: str
    document_id: str
    section: str
    heading: str
    content: str
    metadata: dict = Field(default_factory=dict)
    provenance: RetrievalChannelProvenance | None = None

class RetrievalExecutionMetadata(BaseModel):
    model_config = {"frozen": True}
    vector_store_mode: str      # "qdrant" or "memory"
    embedding_mode: str         # "sentence-transformer" or "mock"
    reranker_mode: str          # "flashrank" or "lexical-fallback"
    degraded_mode: bool
    fallback_reasons: list[str] = Field(default_factory=list)

class KnowledgeBundle(BaseModel):
    model_config = {"frozen": True}
    chunks: tuple[KnowledgeChunk, ...] = Field(default_factory=tuple)
    metadata: dict = Field(default_factory=dict)
    retrieval_scores: dict[str, float] = Field(default_factory=dict)
    rerank_scores: dict[str, float] = Field(default_factory=dict)
    applied_filters: dict = Field(default_factory=dict)
    evidence_references: list[str] = Field(default_factory=list)
    search_summary: str
    execution_metadata: RetrievalExecutionMetadata
