from pydantic import BaseModel, Field, field_validator
from typing import Literal
from app.common.enums import ActionType, RiskLevel

class Hypothesis(BaseModel):
    cause: str
    affected_service: str
    evidence_ids: list[str] = Field(default_factory=list)

class Confidence(BaseModel):
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    band: Literal["low", "moderate", "strong"]
    basis: list[str] = Field(default_factory=list)

class RecommendedAction(BaseModel):
    type: ActionType
    action: str
    risk: RiskLevel
    requires_approval: bool

class RCAResponse(BaseModel):
    incident_id: str
    summary: str
    primary_hypothesis: Hypothesis | None = None
    alternative_hypotheses: list[Hypothesis] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    confidence: Confidence
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    validation_status: str

class GroundTruthLabels(BaseModel):
    affected_service: str
    fault_category: str
    root_cause_code: str
    root_cause_summary: str

class GoldenCase(BaseModel):
    schema_version: str = Field(default="1.0")
    scenario_id: str
    incident_id: str
    split: str
    labels: GroundTruthLabels
    required_evidence_ids: list[str] = Field(default_factory=list)
    expected_tools: list[str] = Field(default_factory=list)
    acceptable_remediation_codes: list[str] = Field(default_factory=list)
    forbidden_unsupported_causes: list[str] = Field(default_factory=list)

