from pydantic import BaseModel, Field, field_validator
from datetime import datetime

class PlanStep(BaseModel):
    tool: str
    reason: str

class InvestigationPlan(BaseModel):
    incident_id: str
    steps: list[PlanStep] = Field(default_factory=list)

class ToolFailure(BaseModel):
    tool_name: str
    error_message: str
    timestamp: str

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"Invalid timestamp format: {v}")
        return v
