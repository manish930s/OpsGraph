import logging
from datetime import datetime
from app.schemas.evidence import Evidence
from app.common.utils import parse_and_validate_time_window

logger = logging.getLogger("opsgraph.evidence.timeline")

class EvidenceTimeline:
    """
    Manages chronological sequencing and window-slicing of evidence records.
    Ensures stable, deterministic ordering for items with identical timestamps.
    """
    def build_timeline(self, evidences: list[Evidence]) -> list[Evidence]:
        """
        Sorts all evidence items chronologically. Stable ordering is preserved via index.
        """
        indexed_evidences = []
        for idx, ev in enumerate(evidences):
            t_str = ev.time_window.start if ev.time_window and ev.time_window.start else "9999-12-31T23:59:59Z"
            indexed_evidences.append((t_str, idx, ev))

        # Sort first by timestamp string, second by original list index
        sorted_triplets = sorted(indexed_evidences, key=lambda x: (x[0], x[1]))
        logger.info(f"Built chronological timeline of {len(sorted_triplets)} elements with stable sequence order.")
        return [item[2] for item in sorted_triplets]

    def filter_by_window(self, evidences: list[Evidence], start: str, end: str) -> list[Evidence]:
        """
        Filters the evidence collection to include only those within start/end boundaries.
        """
        start_dt, end_dt = parse_and_validate_time_window(start, end)
        results = []
        for ev in evidences:
            if not ev.time_window or not ev.time_window.start:
                continue
            
            try:
                ev_dt = datetime.fromisoformat(ev.time_window.start.replace("Z", "+00:00"))
                if start_dt <= ev_dt <= end_dt:
                    results.append(ev)
            except ValueError:
                logger.warning(f"Skipped filtering for item {ev.evidence_id} due to invalid timestamp.")
                
        return results
