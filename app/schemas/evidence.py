from pydantic import BaseModel, Field, field_validator
from app.common.enums import SourceType
from app.schemas.common import TimeWindow

class EvidenceProvenance(BaseModel):
    dataset: str
    generator_version: str | None = None
    record_reference: str | None = None
    query_reference: str | None = None

class EvidenceRetrievalMetadata(BaseModel):
    tool_name: str
    relevance_score: float

class Evidence(BaseModel):
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

