from app.schemas.telemetry import TraceSpan
from app.services.telemetry.base import BaseTelemetryRepository
from app.common.exceptions import ValidationError

class TraceRepository(BaseTelemetryRepository):
    """
    Read-only repository for querying and building trace span hierarchies.
    """
    def __init__(self, scenario_repo):
        super().__init__(scenario_repo)
        self._spans = None  # lazy-loaded repository state

    def _get_all(self) -> list[TraceSpan]:
        if self._spans is None:
            self._spans = self.repo.load_traces()
        return self._spans

    def get_spans(self) -> list[TraceSpan]:
        return self._get_all()

    def get_trace(self, trace_id: str) -> list[TraceSpan]:
        if not trace_id:
            raise ValidationError("trace_id cannot be empty")
        return [s for s in self._get_all() if s.trace_id == trace_id]

    def filter_by_service(self, service: str) -> list[TraceSpan]:
        if not service or not isinstance(service, str) or not service.strip():
            raise ValidationError(f"Invalid service name: '{service}'")
        return [s for s in self._get_all() if s.service == service]

    def get_trace_tree(self, trace_id: str) -> dict[str, list[TraceSpan]]:
        """
        Groups spans by their parent_span_id to form tree structures.
        Returns a dictionary mapping parent_span_id (or "root" for None) to list of children spans.
        """
        spans = self.get_trace(trace_id)
        tree = {}
        for s in spans:
            parent = s.parent_span_id if s.parent_span_id else "root"
            if parent not in tree:
                tree[parent] = []
            tree[parent].append(s)
        return tree
