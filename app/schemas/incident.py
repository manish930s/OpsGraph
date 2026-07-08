from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from app.common.enums import Severity, EnvironmentName
from app.schemas.common import TimeWindow

class IncidentCreate(BaseModel):
    description: str
    environment: EnvironmentName
    reported_services: list[str] = Field(default_factory=list)
    reported_symptoms: list[str] = Field(default_factory=list)

class IncidentRecord(BaseModel):
    schema_version: str = Field(default="1.0")
    incident_id: str
    scenario_id: str
    title: str
    description: str
    environment: EnvironmentName
    severity: Severity
    reported_services: list[str]
    reported_symptoms: list[str]
    reported_at: str
    investigation_window: TimeWindow
    status: str

    @field_validator("reported_at")
    @classmethod
    def validate_reported_at(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"Invalid reported_at ISO-8601 datetime: {v}")
        return v

class IncidentSummary(BaseModel):
    incident_id: str
    title: str
    severity: Severity
    status: str

class IncidentContext(BaseModel):
    incident_id: str
    candidate_services: list[str]
    severity: Severity
    symptoms: list[str]
    time_window: TimeWindow
    suspected_change_event: bool
