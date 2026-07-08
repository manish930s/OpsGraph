from datetime import datetime
import re
from app.schemas.telemetry import LogRecord
from app.services.telemetry.base import BaseTelemetryRepository
from app.common.utils import parse_and_validate_time_window
from app.common.exceptions import ValidationError

class LogRepository(BaseTelemetryRepository):
    """
    Read-only repository for querying and filtering log records.
    """
    def __init__(self, scenario_repo):
        super().__init__(scenario_repo)
        self._logs = None  # lazy-loaded repository state

    def _get_all(self) -> list[LogRecord]:
        if self._logs is None:
            self._logs = self.repo.load_logs()
        return self._logs

    def get_logs(self) -> list[LogRecord]:
        return self._get_all()

    def filter_by_service(self, service: str) -> list[LogRecord]:
        if not service or not isinstance(service, str) or not service.strip():
            raise ValidationError(f"Invalid service name: '{service}'")
        return [l for l in self._get_all() if l.service == service]

    def filter_by_time_window(self, start: str, end: str) -> list[LogRecord]:
        start_dt, end_dt = parse_and_validate_time_window(start, end)
        results = []
        for l in self._get_all():
            l_dt = datetime.fromisoformat(l.timestamp.replace("Z", "+00:00"))
            if start_dt <= l_dt <= end_dt:
                results.append(l)
        return results

    def search_patterns(self, pattern: str) -> list[LogRecord]:
        if not pattern:
            return self._get_all()
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            raise ValidationError(f"Invalid regex pattern '{pattern}': {e}")
        return [l for l in self._get_all() if regex.search(l.message)]
