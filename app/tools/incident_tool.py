from pydantic import BaseModel, Field
from app.services.telemetry.repository import ScenarioRepository
from app.tools.base import BaseTool
from app.common.exceptions import ValidationError

class IncidentSummaryInput(BaseModel):
    incident_id: str | None = Field(default=None, description="Optional incident identifier to inspect.")

class IncidentSummaryResponse(BaseModel):
    incident_id: str
    scenario_id: str
    title: str
    description: str
    environment: str
    severity: str
    reported_services: list[str] = Field(default_factory=list)
    reported_symptoms: list[str] = Field(default_factory=list)
    reported_at: str
    investigation_window: dict

class IncidentSummaryTool(BaseTool):
    """
    Diagnostic tool to retrieve the incident context and reported symptoms.
    """
    name: str = "incident_summary_lookup"
    description: str = (
        "Retrieves critical context about the reported incident, including services, "
        "reported symptoms, timestamps, and target environments."
    )
    args_model: type[BaseModel] = IncidentSummaryInput

    def __init__(self, scenario_repo: ScenarioRepository):
        self.repo = scenario_repo

    def run(self, incident_id: str | None = None) -> IncidentSummaryResponse:
        record = self.repo.load_incident()
        
        # Validate incident ID if provided
        if incident_id and record.incident_id != incident_id:
            raise ValidationError(
                f"Requested incident ID '{incident_id}' does not match loaded context ID '{record.incident_id}'"
            )

        return IncidentSummaryResponse(
            incident_id=record.incident_id,
            scenario_id=record.scenario_id,
            title=record.title,
            description=record.description,
            environment=record.environment.value,
            severity=record.severity.value,
            reported_services=record.reported_services,
            reported_symptoms=record.reported_symptoms,
            reported_at=record.reported_at,
            investigation_window={
                "start": record.investigation_window.start,
                "end": record.investigation_window.end
            }
        )
