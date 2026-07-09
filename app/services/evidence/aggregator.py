import logging
from app.schemas.evidence import Evidence

logger = logging.getLogger("opsgraph.evidence.aggregator")

class EvidenceAggregator:
    """
    Service responsible for grouping, sorting, merging, and unioning lists of Evidence.
    """
    def merge(self, *lists: list[Evidence]) -> list[Evidence]:
        """
        Combines multiple lists of Evidence, preserving all items and provenance.
        """
        merged = []
        for lst in lists:
            if lst:
                merged.extend(lst)
        logger.info(f"Aggregated multiple evidence lists into total items count: {len(merged)}")
        return merged

    def sort_chronologically(self, evidences: list[Evidence]) -> list[Evidence]:
        """
        Sorts evidence items chronologically. Items without time windows are sorted to the end.
        """
        def get_sort_key(ev: Evidence) -> str:
            if ev.time_window and ev.time_window.start:
                return ev.time_window.start
            return "9999-12-31T23:59:59Z"

        return sorted(evidences, key=get_sort_key)

    def group_by_service(self, evidences: list[Evidence]) -> dict[str, list[Evidence]]:
        """
        Groups evidence items by their affected service identifier.
        """
        grouped = {}
        for ev in evidences:
            if ev.service not in grouped:
                grouped[ev.service] = []
            grouped[ev.service].append(ev)
        return grouped

    def group_by_source_type(self, evidences: list[Evidence]) -> dict[str, list[Evidence]]:
        """
        Groups evidence items by their SourceType string.
        """
        grouped = {}
        for ev in evidences:
            st = ev.source_type.value
            if st not in grouped:
                grouped[st] = []
            grouped[st].append(ev)
        return grouped
