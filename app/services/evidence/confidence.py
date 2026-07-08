import logging
from datetime import datetime
from app.schemas.evidence import Evidence, ConfidenceSummary
from app.schemas.incident import IncidentRecord
from app.common.enums import SourceType

logger = logging.getLogger("opsgraph.evidence.confidence")

class EvidenceConfidenceScorer:
    """
    Evaluates evidence collections, generating heuristic confidence scores,
    bands, and analytical explanations.
    """
    def compute_confidence(self, evidences: list[Evidence], incident: IncidentRecord) -> ConfidenceSummary:
        """
        Computes the heuristic confidence summary for the collected evidence.
        """
        explanations = []
        
        if not evidences:
            logger.info("No evidence collected. Setting confidence to 0.0 (LOW)")
            return ConfidenceSummary(
                score=0.0,
                band="LOW",
                explanation=["No evidence collected for the incident."]
            )

        score_components = []

        # 1. Coverage / Completeness
        reported = set(incident.reported_services)
        covered = set()
        for ev in evidences:
            if ev.service in reported:
                covered.add(ev.service)
        
        coverage_ratio = len(covered) / len(reported) if reported else 1.0
        score_components.append(coverage_ratio * 0.4)  # Max weight 0.4
        explanations.append(
            f"Coverage: covered {len(covered)} of {len(reported)} reported services "
            f"({int(coverage_ratio * 100)}%)."
        )

        # 2. Cross-Source Consensus
        # Count services with both logs/metrics or multiple telemetry types
        consensus_count = 0
        from app.common.enums import SourceType
        service_types: dict[str, set[str]] = {}
        for ev in evidences:
            if ev.service not in service_types:
                service_types[ev.service] = set()
            service_types[ev.service].add(ev.source_type.value)

        for svc, types in service_types.items():
            if len(types) >= 2:
                consensus_count += 1

        consensus_score = min(0.3, consensus_count * 0.15)  # Max weight 0.3
        score_components.append(consensus_score)
        if consensus_count > 0:
            explanations.append(
                f"Consensus: found cross-source agreement (multiple telemetry types) "
                f"for {consensus_count} services."
            )
        else:
            explanations.append("Consensus: no cross-source consensus found.")

        # 3. Temporal Consistency
        # Check if telemetry events are close to reported_at timestamp
        try:
            reported_dt = datetime.fromisoformat(incident.reported_at.replace("Z", "+00:00"))
            temporal_matches = 0
            for ev in evidences:
                if ev.time_window and ev.time_window.start:
                    ev_dt = datetime.fromisoformat(ev.time_window.start.replace("Z", "+00:00"))
                    diff_sec = abs((reported_dt - ev_dt).total_seconds())
                    if diff_sec <= 600:  # within 10 minutes
                        temporal_matches += 1

            temporal_ratio = min(1.0, temporal_matches / len(evidences)) if evidences else 1.0
            temporal_score = temporal_ratio * 0.3  # Max weight 0.3
            score_components.append(temporal_score)
            explanations.append(
                f"Timeline: {temporal_matches} of {len(evidences)} events occurred within "
                f"10 minutes of the incident report."
            )
        except Exception as e:
            logger.warning(f"Error computing temporal consistency: {e}")
            score_components.append(0.15)
            explanations.append("Timeline: temporal checks skipped due to timestamp parse errors.")

        # Compute total
        total_score = sum(score_components)
        
        # Penalize if there are no deployment logs or topology clues
        source_types_present = {ev.source_type for ev in evidences}
        if SourceType.DEPLOYMENT not in source_types_present:
            total_score = max(0.0, total_score - 0.1)
            explanations.append("Penalty: no deployment change events found in evidence.")

        total_score = round(min(1.0, max(0.0, total_score)), 2)

        # Map score band
        if total_score >= 0.7:
            band = "HIGH"
        elif total_score >= 0.4:
            band = "MEDIUM"
        else:
            band = "LOW"

        logger.info(f"Confidence score computed: {total_score} ({band})")
        return ConfidenceSummary(
            score=total_score,
            band=band,
            explanation=explanations
        )
