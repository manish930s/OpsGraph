from pydantic import BaseModel, Field
from app.schemas.telemetry import TraceSpan
from app.services.telemetry.trace_repository import TraceRepository
from app.tools.base import BaseTool

class TraceInspectionInput(BaseModel):
    trace_id: str = Field(..., description="The unique ID of the trace to inspect.")
    service: str | None = Field(default=None, description="Optional service name filter on spans.")

class TraceInspectionResponse(BaseModel):
    trace_id: str
    spans_count: int
    tree: dict[str, list[TraceSpan]] = Field(default_factory=dict)
    spans: list[TraceSpan] = Field(default_factory=list)

class TraceInspectionTool(BaseTool):
    """
    Diagnostic tool to inspect traces, filter spans, and build tree representations.
    """
    name: str = "trace_dependency_analysis"
    description: str = (
        "Inspects a distributed transaction trace, builds dependency calling trees, "
        "and highlights service latencies."
    )
    args_model: type[BaseModel] = TraceInspectionInput

    def __init__(self, trace_repo: TraceRepository):
        self.trace_repo = trace_repo

    def run(self, trace_id: str, service: str | None = None) -> TraceInspectionResponse:
        spans = self.trace_repo.get_trace(trace_id)
        if service:
            spans = [s for s in spans if s.service == service]

        # Construct tree for trace_id
        # Note: tree grouping maps parent_span_id to list of children spans
        # If filtering is active, some nodes might be skipped, but the tree maps available elements
        tree = {}
        for s in spans:
            parent = s.parent_span_id if s.parent_span_id else "root"
            if parent not in tree:
                tree[parent] = []
            tree[parent].append(s)

        return TraceInspectionResponse(
            trace_id=trace_id,
            spans_count=len(spans),
            tree=tree,
            spans=spans
        )
