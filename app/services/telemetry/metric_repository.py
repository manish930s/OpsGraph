from datetime import datetime
from app.schemas.telemetry import MetricPoint
from app.services.telemetry.base import BaseTelemetryRepository
from app.common.utils import parse_and_validate_time_window
from app.common.exceptions import ValidationError

class MetricRepository(BaseTelemetryRepository):
    """
    Read-only repository for querying, aggregating, and analyzing metrics.
    """
    def __init__(self, scenario_repo):
        super().__init__(scenario_repo)
        self._metrics = None  # lazy-loaded repository state

    def _get_all(self) -> list[MetricPoint]:
        if self._metrics is None:
            self._metrics = self.repo.load_metrics()
        return self._metrics

    def get_metrics(self) -> list[MetricPoint]:
        return self._get_all()

    def get_metric(self, metric_name: str) -> list[MetricPoint]:
        if not metric_name:
            raise ValidationError("metric_name cannot be empty")
        return [m for m in self._get_all() if m.metric_name == metric_name]

    def get_metric_window(self, metric_name: str, start: str, end: str) -> list[MetricPoint]:
        start_dt, end_dt = parse_and_validate_time_window(start, end)
        candidates = self.get_metric(metric_name)
        results = []
        for m in candidates:
            m_dt = datetime.fromisoformat(m.timestamp.replace("Z", "+00:00"))
            if start_dt <= m_dt <= end_dt:
                results.append(m)
        return results

    def aggregate(self, metric_name: str, aggregator: str) -> float | None:
        aggregator_lower = aggregator.lower()
        if aggregator_lower not in ("avg", "min", "max", "sum"):
            raise ValidationError(f"Unsupported aggregator: '{aggregator}'. Supported: avg, min, max, sum")

        points = self.get_metric(metric_name)
        if not points:
            return None

        values = [p.value for p in points]
        if aggregator_lower == "avg":
            return sum(values) / len(values)
        elif aggregator_lower == "min":
            return min(values)
        elif aggregator_lower == "max":
            return max(values)
        elif aggregator_lower == "sum":
            return sum(values)
        return None

    def detect_missing_points(self, metric_name: str, expected_interval_sec: int) -> list[str]:
        if expected_interval_sec <= 0:
            raise ValidationError(f"expected_interval_sec must be positive, got {expected_interval_sec}")

        points = self.get_metric(metric_name)
        if len(points) < 2:
            return []

        # Sort points chronologically
        sorted_points = sorted(
            points,
            key=lambda x: datetime.fromisoformat(x.timestamp.replace("Z", "+00:00"))
        )

        gaps = []
        for i in range(len(sorted_points) - 1):
            curr_dt = datetime.fromisoformat(sorted_points[i].timestamp.replace("Z", "+00:00"))
            next_dt = datetime.fromisoformat(sorted_points[i + 1].timestamp.replace("Z", "+00:00"))
            diff_sec = (next_dt - curr_dt).total_seconds()
            
            # If the difference is greater than 1.5x expected interval, report a gap
            if diff_sec > expected_interval_sec * 1.5:
                gaps.append(
                    f"Gap detected between {sorted_points[i].timestamp} and {sorted_points[i + 1].timestamp} "
                    f"({int(diff_sec)} seconds)"
                )
        return gaps
