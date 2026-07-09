from pydantic import BaseModel, Field
from typing import Any
from app.schemas.model_response import RCADecisionResponse

class ToolSelectionDecision(BaseModel):
    model_config = {"frozen": True, "extra": "forbid"}
    response_id: str
    task_type: str = Field(default="tool_selection")
    tool_name: str
    reason: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    expected_evidence_type: str

class HumanReviewTerminalState(BaseModel):
    model_config = {"frozen": True}
    incident_id: str
    current_rca: RCADecisionResponse | None = None
    gaps: tuple[str, ...] = Field(default_factory=tuple)
    reason: str
    recommended_actions: tuple[str, ...] = Field(default_factory=tuple)

class FailureTerminalState(BaseModel):
    model_config = {"frozen": True}
    incident_id: str
    failure_type: str
    error_message: str
    details: dict[str, Any] = Field(default_factory=dict)
