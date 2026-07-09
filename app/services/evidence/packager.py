import logging
from app.schemas.evidence import Evidence, EvidenceBundle
from app.schemas.incident import IncidentRecord
from app.schemas.telemetry import ServiceTopology
from app.services.evidence.validator import validate_evidence
from app.services.evidence.deduplicator import EvidenceDeduplicator
from app.services.evidence.timeline import EvidenceTimeline
from app.services.evidence.confidence import EvidenceConfidenceScorer

logger = logging.getLogger("opsgraph.evidence.packager")

class EvidencePackager:
    """
    Combines, validates, de-duplicates, timelines, and scores evidence items,
    producing an immutable EvidenceBundle.
    """
    def __init__(self):
        self.deduplicator = EvidenceDeduplicator()
        self.timeline_builder = EvidenceTimeline()
        self.confidence_scorer = EvidenceConfidenceScorer()

    def package_bundle(self, evidences: list[Evidence], incident: IncidentRecord, topology: ServiceTopology) -> EvidenceBundle:
        """
        Validates all evidence, deduplicates matching ones, builds the timeline,
        scores confidence, and compiles service coverage details.
        """
        logger.info(f"Starting packaging of {len(evidences)} evidence elements.")
        
        # 1. Deterministic Validation
        for ev in evidences:
            validate_evidence(ev, incident, topology)
        
        # 2. Deduplication
        unique_ev = self.deduplicator.deduplicate(evidences)

        # 3. Timeline Ordering
        timeline_sorted = self.timeline_builder.build_timeline(unique_ev)

        # 4. Confidence scoring
        conf = self.confidence_scorer.compute_confidence(unique_ev, incident)

        # 5. Coverage Summary
        # Map service ID to list of source types that gathered observations for it
        coverage = {}
        for ev in unique_ev:
            if ev.service not in coverage:
                coverage[ev.service] = []
            if ev.source_type.value not in coverage[ev.service]:
                coverage[ev.service].append(ev.source_type.value)

        logger.info("Packaging completed successfully.")
        return EvidenceBundle(
            schema_version="1.0",
            evidence_list=unique_ev,
            timeline=timeline_sorted,
            confidence_summary=conf,
            validation_status="valid",
            coverage_summary=coverage
        )
