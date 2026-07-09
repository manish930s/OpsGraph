import logging
from datetime import datetime
from app.schemas.evidence import Evidence, ConfidenceSummary, ConfidenceComponents
from app.schemas.incident import IncidentRecord
from app.common.enums import SourceType

logger = logging.getLogger("opsgraph.evidence.confidence")

class EvidenceConfidenceScorer:
    """
    Evaluates evidence collections, generating heuristic confidence scores,
    bands, and analytical explanations with explicit components.
    """
    def compute_confidence(self, evidences: list[Evidence], incident: IncidentRecord) -> ConfidenceSummary:
        """
        Computes the heuristic confidence summary and components for the collected evidence.
        """
        if not evidences:
            logger.info("No evidence collected. Setting confidence to 0.0 (LOW)")
            components = ConfidenceComponents(
                source_reliability=1.0,
                cross_source_agreement=0.0,
                timeline_consistency=0.0,
                topology_consistency=0.0,
                evidence_coverage=0.0,
                deployment_consistency=0.0,
                observation_completeness=0.0,
                contradictions=0.0
            )
            return ConfidenceSummary(
                score=0.0,
                band="LOW",
                explanation=["No evidence collected for the incident."],
                components=components,
                supporting_evidence_count=0,
                conflicting_evidence_count=0,
                missing_evidence_categories=["log", "metric", "trace", "deployment", "topology"]
            )

        explanations = []

        # 1. Evidence Coverage
        reported = set(incident.reported_services)
        covered = set()
        for ev in evidences:
            if ev.service in reported:
                covered.add(ev.service)
        coverage_ratio = len(covered) / len(reported) if reported else 1.0
        evidence_coverage = round(coverage_ratio, 2)
        explanations.append(f"Coverage: {int(evidence_coverage * 100)}% of reported services covered.")

        # 2. Cross-Source Consensus
        consensus_count = 0
        service_types: dict[str, set[str]] = {}
        for ev in evidences:
            if ev.service not in service_types:
                service_types[ev.service] = set()
            service_types[ev.service].add(ev.source_type.value)
        for svc, types in service_types.items():
            if len(types) >= 2:
                consensus_count += 1
        cross_source_agreement = round(min(1.0, consensus_count * 0.5), 2)
        explanations.append(f"Consensus: found cross-source agreement for {consensus_count} services.")

        # 3. Timeline Consistency
        temporal_matches = 0
        try:
            reported_dt = datetime.fromisoformat(incident.reported_at.replace("Z", "+00:00"))
            for ev in evidences:
                if ev.time_window and ev.time_window.start:
                    ev_dt = datetime.fromisoformat(ev.time_window.start.replace("Z", "+00:00"))
                    diff_sec = abs((reported_dt - ev_dt).total_seconds())
                    if diff_sec <= 600:  # within 10 minutes
                        temporal_matches += 1
            timeline_consistency = round(temporal_matches / len(evidences), 2)
            explanations.append(f"Timeline: {int(timeline_consistency * 100)}% of events occurred close to incident report.")
        except Exception as e:
            logger.warning(f"Error parsing timestamps: {e}")
            timeline_consistency = 0.5
            explanations.append("Timeline: temporal checks defaulted due to timestamp formats.")

        # 4. Topology Consistency
        # Since validate_evidence asserts service presence, topology consistency is stable
        topology_consistency = 1.0

        # 5. Deployment Consistency
        has_deployment = any(ev.source_type == SourceType.DEPLOYMENT for ev in evidences)
        deployment_consistency = 1.0 if has_deployment else 0.0
        if not has_deployment:
            explanations.append("Penalty: no deployment telemetry is present.")

        # 6. Observation Completeness
        types_present = {ev.source_type for ev in evidences}
        observation_completeness = round(len(types_present) / 5.0, 2) # LOG, METRIC, TRACE, DEPLOYMENT, TOPOLOGY

        # 7. Contradictions
        # For simplicity, count error logs that clash with other success states
        conflicting_count = sum(1 for ev in evidences if ev.source_type == SourceType.LOG and "error" in ev.observation.lower())
        contradictions = round(min(1.0, conflicting_count * 0.1), 2)

        # 8. Source Reliability
        source_reliability = 1.0

        # Overall Score calculation:
        # coverage (30%) + consensus (20%) + timeline (20%) + observation_completeness (20%) + deployment_consistency (10%) - contradictions (10%)
        raw_score = (
            evidence_coverage * 0.30 +
            cross_source_agreement * 0.20 +
            timeline_consistency * 0.20 +
            observation_completeness * 0.20 +
            deployment_consistency * 0.10 -
            contradictions * 0.10
        )
        score = round(min(1.0, max(0.0, raw_score)), 2)

        # Map score band
        if score >= 0.7:
            band = "HIGH"
        elif score >= 0.4:
            band = "MEDIUM"
        else:
            band = "LOW"

        # Missing categories
        all_cats = {"log", "metric", "trace", "deployment", "topology"}
        present_cats = {ev.source_type.value for ev in evidences}
        missing_cats = list(all_cats - present_cats)

        components = ConfidenceComponents(
            source_reliability=source_reliability,
            cross_source_agreement=cross_source_agreement,
            timeline_consistency=timeline_consistency,
            topology_consistency=topology_consistency,
            evidence_coverage=evidence_coverage,
            deployment_consistency=deployment_consistency,
            observation_completeness=observation_completeness,
            contradictions=contradictions
        )

        return ConfidenceSummary(
            score=score,
            band=band,
            explanation=explanations,
            components=components,
            supporting_evidence_count=len(evidences),
            conflicting_evidence_count=conflicting_count,
            missing_evidence_categories=missing_cats
        )
