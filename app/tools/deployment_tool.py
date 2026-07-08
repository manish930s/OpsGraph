from pydantic import BaseModel, Field
from app.schemas.telemetry import DeploymentEvent
from app.services.telemetry.deployment_repository import DeploymentRepository
from app.tools.base import BaseTool

class DeploymentHistoryInput(BaseModel):
    environment: str | None = Field(default=None, description="Scope target environment name.")
    timestamp: str | None = Field(default=None, description="Optional ISO-8601 boundary to get latest deployment before.")

class DeploymentHistoryResponse(BaseModel):
    deployments: list[DeploymentEvent] = Field(default_factory=list)
    latest_change: DeploymentEvent | None = None

class DeploymentHistoryTool(BaseTool):
    """
    Diagnostic tool to list, filter, and track deployment modifications.
    """
    name: str = "deployment_event_search"
    description: str = (
        "Queries deployment history events, filters by environment, and identifies "
        "the latest change preceding a specific time."
    )
    args_model: type[BaseModel] = DeploymentHistoryInput

    def __init__(self, deploy_repo: DeploymentRepository):
        self.deploy_repo = deploy_repo

    def run(self, environment: str | None = None, timestamp: str | None = None) -> DeploymentHistoryResponse:
        # Load datasets
        deployments = self.deploy_repo.get_deployments()

        if environment:
            deployments = self.deploy_repo.filter_by_environment(environment)

        latest_change = None
        if timestamp:
            # Query the repository's latest_before adapter
            latest_change = self.deploy_repo.latest_before(timestamp)
            # Make sure it matches environment if filtered
            if environment and latest_change and latest_change.environment != environment:
                latest_change = None

        return DeploymentHistoryResponse(
            deployments=deployments,
            latest_change=latest_change
        )
