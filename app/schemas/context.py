from pydantic import BaseModel, Field

class ContextItem(BaseModel):
    model_config = {"frozen": True}
    item_id: str
    source_kind: str  # "evidence" or "knowledge"
    source_id: str    # evidence_id or chunk_id
    source_bundle_id: str | None = None
    scenario_id: str
    incident_id: str | None = None
    service: str | None = None
    component: str | None = None
    timestamp: str | None = None
    category: str | None = None
    content: str
    priority_score: float
    citation_reference: str
    provenance_reference: str
    estimated_budget_cost: int
    selection_reason: str
    metadata: dict = Field(default_factory=dict)

class CitationInfo(BaseModel):
    model_config = {"frozen": True}
    source_kind: str  # "evidence" or "knowledge"
    id: str           # evidence_id or chunk_id
    
    # Evidence specific citation details
    source_type: str | None = None
    source_record_ids: tuple[str, ...] = Field(default_factory=tuple)
    evidence_provenance: dict | None = None
    
    # Knowledge specific citation details
    document_id: str | None = None
    chunk_id: str | None = None
    source_path: str | None = None
    section: str | None = None
    heading: str | None = None
    version: str | None = None

class ProvenanceInfo(BaseModel):
    model_config = {"frozen": True}
    source_kind: str  # "evidence" or "knowledge"
    lineage: tuple[str, ...]
    details: dict = Field(default_factory=dict)

class ContextBudgetSummary(BaseModel):
    model_config = {"frozen": True}
    total_budget: int
    evidence_budget: int
    knowledge_budget: int
    evidence_cost: int
    knowledge_cost: int
    remaining_budget: int
    dropped_by_budget_count: int

class ContextCoverageSummary(BaseModel):
    model_config = {"frozen": True}
    covered_categories: tuple[str, ...] = Field(default_factory=tuple)
    missing_categories: tuple[str, ...] = Field(default_factory=tuple)
    selected_item_counts: dict[str, int] = Field(default_factory=dict)
    candidate_item_counts: dict[str, int] = Field(default_factory=dict)
    dropped_item_counts: dict[str, int] = Field(default_factory=dict)
    dropped_duplicate_counts: dict[str, int] = Field(default_factory=dict)

class ContextGapSummary(BaseModel):
    model_config = {"frozen": True}
    gaps: tuple[str, ...] = Field(default_factory=tuple)
    warnings: tuple[str, ...] = Field(default_factory=tuple)

class ContextExecutionMetadata(BaseModel):
    model_config = {"frozen": True}
    candidates_received: int
    duplicates_removed: int
    items_selected: int
    items_dropped_by_budget: int
    estimated_budget_used: int
    build_duration_ms: float
    validation_status: str
    upstream_degraded_mode: bool
    upstream_fallback_reasons: tuple[str, ...] = Field(default_factory=tuple)
    excluded_oversized_items: tuple[str, ...] = Field(default_factory=tuple)

class ContextSection(BaseModel):
    model_config = {"frozen": True}
    name: str  # e.g., "Incident Overview", "Critical Evidence", "Supporting Evidence", "Contradictory Evidence", "Relevant Runbooks", "Relevant Operational Knowledge", "Topology Context", "Deployment Context", "Known Gaps"
    items: tuple[ContextItem, ...] = Field(default_factory=tuple)

class InvestigationContext(BaseModel):
    model_config = {"frozen": True}
    context_id: str
    scenario_id: str
    incident_id: str
    build_timestamp: str
    selected_evidence_ids: tuple[str, ...] = Field(default_factory=tuple)
    selected_knowledge_ids: tuple[str, ...] = Field(default_factory=tuple)
    sections: tuple[ContextSection, ...] = Field(default_factory=tuple)
    citation_map: dict[str, CitationInfo] = Field(default_factory=dict)
    provenance_map: dict[str, ProvenanceInfo] = Field(default_factory=dict)
    budget_summary: ContextBudgetSummary
    coverage_summary: ContextCoverageSummary
    gap_summary: ContextGapSummary
    execution_metadata: ContextExecutionMetadata
