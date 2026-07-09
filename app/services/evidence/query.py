import logging
from datetime import datetime
from app.schemas.evidence import Evidence, EvidenceBundle
from app.common.utils import parse_and_validate_time_window

logger = logging.getLogger("opsgraph.evidence.query")

class EvidenceQueryAPI:
    """
    Exposes deterministic search and filter operations over packaged EvidenceBundles.
    """
    def __init__(self, bundle: EvidenceBundle):
        self.bundle = bundle

    def query_by_service(self, service: str) -> list[Evidence]:
        """
        Filters evidence items targeting a specific service name.
        """
        if not service:
            return []
        return [e for e in self.bundle.evidence_list if e.service == service]

    def query_by_type(self, source_type: str) -> list[Evidence]:
        """
        Filters evidence items matching the given SourceType value string.
        """
        if not source_type:
            return []
        return [e for e in self.bundle.evidence_list if e.source_type.value == source_type]

    def query_by_time_window(self, start: str, end: str) -> list[Evidence]:
        """
        Queries timeline items falling within the specified time window bounds.
        """
        start_dt, end_dt = parse_and_validate_time_window(start, end)
        results = []
        for e in self.bundle.timeline:
            if not e.time_window or not e.time_window.start:
                continue
            try:
                ev_dt = datetime.fromisoformat(e.time_window.start.replace("Z", "+00:00"))
                if start_dt <= ev_dt <= end_dt:
                    results.append(e)
            except ValueError:
                pass
        return results

    def get_chronological_events(self) -> list[Evidence]:
        """
        Returns the pre-sorted chronological timeline events list.
        """
        return self.bundle.timeline
