from pydantic import BaseModel, Field, field_validator
from app.common.enums import SourceType
from app.schemas.common import TimeWindow

class EvidenceProvenance(BaseModel):
    model_config = {"frozen": True}
    dataset: str
    generator_version: str | None = None
    record_reference: str | None = None
    query_reference: str | None = None

class EvidenceRetrievalMetadata(BaseModel):
    model_config = {"frozen": True}
    tool_name: str
    relevance_score: float

class Evidence(BaseModel):
    model_config = {"frozen": True}
    schema_version: str = Field(default="1.0")
    evidence_id: str
    incident_id: str
    scenario_id: str
    source_type: SourceType
    source_name: str | None = None
    service: str
    time_window: TimeWindow | None = None
    observation: str
    source_record_ids: list[str] = Field(default_factory=list)
    provenance: EvidenceProvenance
    retrieval: EvidenceRetrievalMetadata | None = None

    @field_validator("evidence_id")
    @classmethod
    def validate_id_format(cls, v: str) -> str:
        if "-EV-" not in v:
            raise ValueError(f"Evidence ID must follow the standard <SOURCE>-EV-<SCENARIO>-<SEQ> format: {v}")
        return v

class ConfidenceComponents(BaseModel):
    model_config = {"frozen": True}
    source_reliability: float
    cross_source_agreement: float
    timeline_consistency: float
    topology_consistency: float
    evidence_coverage: float
    deployment_consistency: float
    observation_completeness: float
    contradictions: float

class ConfidenceSummary(BaseModel):
    model_config = {"frozen": True}
    score: float
    band: str
    explanation: list[str] = Field(default_factory=list)
    components: ConfidenceComponents
    supporting_evidence_count: int
    conflicting_evidence_count: int
    missing_evidence_categories: list[str] = Field(default_factory=list)

class EvidenceBundle(BaseModel):
    model_config = {"frozen": True}
    schema_version: str = Field(default="1.0")
    evidence_list: tuple[Evidence, ...] = Field(default_factory=tuple)
    timeline: tuple[Evidence, ...] = Field(default_factory=tuple)
    confidence_summary: ConfidenceSummary
    validation_status: str
    coverage_summary: dict[str, list[str]] = Field(default_factory=dict)
