from abc import ABC
from app.services.telemetry.repository import ScenarioRepository

class BaseTelemetryRepository(ABC):
    """
    Abstract base class for all read-only, stateless telemetry repositories.
    """
    def __init__(self, scenario_repo: ScenarioRepository):
        self.repo = scenario_repo
