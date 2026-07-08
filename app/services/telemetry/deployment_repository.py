from datetime import datetime
from app.schemas.telemetry import DeploymentEvent
from app.services.telemetry.base import BaseTelemetryRepository
from app.common.exceptions import ValidationError

class DeploymentRepository(BaseTelemetryRepository):
    """
    Read-only repository for querying and tracking system deployment events.
    """
    def __init__(self, scenario_repo):
        super().__init__(scenario_repo)
        self._deployments = None  # lazy-loaded repository state

    def _get_all(self) -> list[DeploymentEvent]:
        if self._deployments is None:
            self._deployments = self.repo.load_deployments()
        return self._deployments

    def get_deployments(self) -> list[DeploymentEvent]:
        return self._get_all()

    def filter_by_environment(self, environment: str) -> list[DeploymentEvent]:
        if not environment:
            raise ValidationError("environment name cannot be empty")
        return [d for d in self._get_all() if d.environment == environment]

    def latest_before(self, timestamp: str) -> DeploymentEvent | None:
        try:
            target_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as e:
            raise ValidationError(f"Invalid timestamp format: {e}")

        candidates = []
        for d in self._get_all():
            d_dt = datetime.fromisoformat(d.timestamp.replace("Z", "+00:00"))
            if d_dt <= target_dt:
                candidates.append((d, d_dt))

        if not candidates:
            return None

        # Return candidate with maximum datetime (latest before target)
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]
