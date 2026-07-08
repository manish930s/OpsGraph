import logging
from datetime import datetime
from app.schemas.evidence import Evidence
from app.common.utils import parse_and_validate_time_window

logger = logging.getLogger("opsgraph.evidence.timeline")

class EvidenceTimeline:
    """
    Manages chronological sequencing and window-slicing of evidence records.
    """
    def build_timeline(self, evidences: list[Evidence]) -> list[Evidence]:
        """
        Sorts all evidence items chronologically. Items without timestamps are placed last.
        """
        def get_timestamp(ev: Evidence) -> str:
            if ev.time_window and ev.time_window.start:
                return ev.time_window.start
            return "9999-12-31T23:59:59Z"

        sorted_ev = sorted(evidences, key=get_timestamp)
        logger.info(f"Built chronological timeline of {len(sorted_ev)} elements")
        return sorted_ev

    def filter_by_window(self, evidences: list[Evidence], start: str, end: str) -> list[Evidence]:
        """
        Filters the evidence collection to include only those within start/end boundaries.
        """
        start_dt, end_dt = parse_and_validate_time_window(start, end)
        results = []
        for ev in evidences:
            if not ev.time_window or not ev.time_window.start:
                # Include timeless items (like topology) by default or skip?
                # Usually we skip them for timeline filtering, or include them. Let's skip them.
                continue
            
            try:
                ev_dt = datetime.fromisoformat(ev.time_window.start.replace("Z", "+00:00"))
                if start_dt <= ev_dt <= end_dt:
                    results.append(ev)
            except ValueError:
                logger.warning(f"Skipped filtering for item {ev.evidence_id} due to invalid timestamp.")
                
        return results
