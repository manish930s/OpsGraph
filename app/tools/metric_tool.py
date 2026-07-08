from pydantic import BaseModel, Field
from app.schemas.telemetry import MetricPoint
from app.services.telemetry.metric_repository import MetricRepository
from app.tools.base import BaseTool

class MetricAnalysisInput(BaseModel):
    metric_name: str = Field(..., description="Name of the metric series to query.")
    aggregator: str | None = Field(default=None, description="Optional aggregator operation: 'avg', 'min', 'max', 'sum'.")
    start: str | None = Field(default=None, description="ISO-8601 window start filter.")
    end: str | None = Field(default=None, description="ISO-8601 window end filter.")
    expected_interval_sec: int | None = Field(default=None, description="Optional interval to perform temporal gap checks.")

class MetricAnalysisResponse(BaseModel):
    metric_name: str
    aggregated_value: float | None = None
    points_count: int
    gaps: list[str] = Field(default_factory=list)
    points: list[MetricPoint] = Field(default_factory=list)

class MetricAnalysisTool(BaseTool):
    """
    Diagnostic tool to retrieve, aggregate, and analyze metric data series.
    """
    name: str = "metric_window_analysis"
    description: str = (
        "Queries a metric series by name, applies window filters, aggregates results, "
        "and checks for temporal data gaps."
    )
    args_model: type[BaseModel] = MetricAnalysisInput

    def __init__(self, metric_repo: MetricRepository):
        self.metric_repo = metric_repo

    def run(
        self,
        metric_name: str,
        aggregator: str | None = None,
        start: str | None = None,
        end: str | None = None,
        expected_interval_sec: int | None = None,
    ) -> MetricAnalysisResponse:
        # Load and slice window
        if start or end:
            start_str = start if start else "1970-01-01T00:00:00Z"
            end_str = end if end else "2100-01-01T00:00:00Z"
            points = self.metric_repo.get_metric_window(metric_name, start_str, end_str)
        else:
            points = self.metric_repo.get_metric(metric_name)

        # Aggregate if requested
        aggregated_value = None
        if aggregator and points:
            # We can use the repository aggregate logic directly on the subset or run it
            # Since the repo queries all, let's calculate locally for the filtered subset
            values = [p.value for p in points]
            agg = aggregator.lower()
            if agg == "avg":
                aggregated_value = sum(values) / len(values)
            elif agg == "min":
                aggregated_value = min(values)
            elif agg == "max":
                aggregated_value = max(values)
            elif agg == "sum":
                aggregated_value = sum(values)

        # Gap detection
        gaps = []
        if expected_interval_sec and expected_interval_sec > 0 and len(points) > 1:
            # Sort subset and identify gaps
            sorted_p = sorted(points, key=lambda x: x.timestamp)
            from datetime import datetime
            for i in range(len(sorted_p) - 1):
                t1 = datetime.fromisoformat(sorted_p[i].timestamp.replace("Z", "+00:00"))
                t2 = datetime.fromisoformat(sorted_p[i + 1].timestamp.replace("Z", "+00:00"))
                diff = (t2 - t1).total_seconds()
                if diff > expected_interval_sec * 1.5:
                    gaps.append(
                        f"Gap detected between {sorted_p[i].timestamp} and {sorted_p[i + 1].timestamp} "
                        f"({int(diff)} seconds)"
                    )

        return MetricAnalysisResponse(
            metric_name=metric_name,
            aggregated_value=aggregated_value,
            points_count=len(points),
            gaps=gaps,
            points=points
        )
