from app.schemas.evidence import EvidenceBundle
from app.schemas.knowledge import KnowledgeBundle
from app.schemas.context import ContextItem, ContextCoverageSummary, ContextGapSummary

ALL_CANONICAL_CATEGORIES = (
    "log",
    "metric",
    "trace",
    "deployment",
    "topology",
    "runbook",
    "operational_procedure",
    "historical_incident_knowledge"
)

def map_to_canonical(source_kind: str, category: str | None) -> str | None:
    if not category:
        return None
    cat = category.lower()
    if source_kind == "evidence":
        if "log" in cat:
            return "log"
        if "metric" in cat:
            return "metric"
        if "trace" in cat:
            return "trace"
        if "deployment" in cat:
            return "deployment"
        if "topology" in cat:
            return "topology"
    else:
        if "runbook" in cat:
            return "runbook"
        if "sop" in cat or "procedure" in cat:
            return "operational_procedure"
        if "postmortem" in cat or "history" in cat or "post_mortem" in cat:
            return "historical_incident_knowledge"
    return None

class CoverageAnalyzer:
    """
    Analyzes which telemetry and operational knowledge categories are populated
    in the final selected context.
    """
    @staticmethod
    def analyze(
        candidates: list[ContextItem],
        selected: list[ContextItem],
        duplicates_removed_count: int
    ) -> ContextCoverageSummary:
        selected_ids = {x.item_id for x in selected}
        
        # Track counts per canonical category
        candidate_counts = {c: 0 for c in ALL_CANONICAL_CATEGORIES}
        selected_counts = {c: 0 for c in ALL_CANONICAL_CATEGORIES}
        dropped_counts = {c: 0 for c in ALL_CANONICAL_CATEGORIES}
        
        for item in candidates:
            canon = map_to_canonical(item.source_kind, item.category)
            if not canon:
                continue
            
            candidate_counts[canon] += 1
            if item.item_id in selected_ids:
                selected_counts[canon] += 1
            else:
                dropped_counts[canon] += 1

        covered = tuple(c for c, count in selected_counts.items() if count > 0)
        missing = tuple(c for c in ALL_CANONICAL_CATEGORIES if c not in covered)

        # Map duplicate counts to source kind categories
        dropped_dup_counts = {"total": duplicates_removed_count}

        return ContextCoverageSummary(
            covered_categories=covered,
            missing_categories=missing,
            selected_item_counts=selected_counts,
            candidate_item_counts=candidate_counts,
            dropped_item_counts=dropped_counts,
            dropped_duplicate_counts=dropped_dup_counts
        )

class GapReporter:
    """
    Evaluates rule-based gaps and operational warnings for the context.
    """
    @staticmethod
    def report_gaps(
        coverage: ContextCoverageSummary,
        evidence_bundle: EvidenceBundle,
        knowledge_bundle: KnowledgeBundle | None,
        dropped_by_budget_count: int,
        contradictory_dropped: bool = False,
        oversized_exclusions: tuple[str, ...] = ()
    ) -> ContextGapSummary:
        gaps = []
        warnings = []

        # 1. Missing telemetries
        if "trace" not in coverage.covered_categories:
            gaps.append("No trace evidence available.")
        if "deployment" not in coverage.covered_categories:
            gaps.append("No deployment history selected.")
        if "topology" not in coverage.covered_categories:
            gaps.append("No topology evidence available.")
        if "runbook" not in coverage.covered_categories:
            gaps.append("No relevant runbook retrieved.")

        # 2. Contradiction warning
        if evidence_bundle.confidence_summary.components.contradictions > 0.0 or \
           evidence_bundle.confidence_summary.conflicting_evidence_count > 0:
            warnings.append("Evidence contradiction present.")

        # 3. Degraded mode warning
        if knowledge_bundle and knowledge_bundle.execution_metadata.degraded_mode:
            warnings.append("Retrieval operated in degraded mode.")

        # 4. Empty knowledge warning
        if not knowledge_bundle or not knowledge_bundle.chunks:
            warnings.append("Knowledge results empty after filters.")

        # 5. Budget exclusion warning
        if dropped_by_budget_count > 0:
            warnings.append("Budget excluded lower-priority context.")

        # 6. Budget excluded contradictory evidence
        if contradictory_dropped:
            gaps.append("Budget excluded contradictory evidence.")

        # 7. Excluded oversized items
        for excl in oversized_exclusions:
            parts = excl.split(" - ")
            item_info = parts[0]
            gaps.append(f"Oversized item {item_info} excluded (reason: OVERSIZED_ITEM_EXCLUDED).")

        return ContextGapSummary(
            gaps=tuple(gaps),
            warnings=tuple(warnings)
        )
