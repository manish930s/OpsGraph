from datetime import datetime
from app.common.exceptions import ValidationError, EvidenceGroundingError
from app.schemas.incident import IncidentRecord
from app.schemas.evidence import Evidence
from app.schemas.rca import Hypothesis
from app.schemas.telemetry import ServiceTopology

def validate_incident_record(incident: IncidentRecord) -> None:
    """
    Validates the sanity and constraints of an IncidentRecord.
    Raises ValidationError if any check fails.
    """
    # 1. reported_services must not be empty and must contain valid string tokens
    if not incident.reported_services:
        raise ValidationError("reported_services list cannot be empty")
    for s in incident.reported_services:
        if not isinstance(s, str) or not s.strip():
            raise ValidationError(f"Invalid service name in reported_services: '{s}'")

    # 2. Check for valid identifier strings
    if not incident.incident_id or not incident.incident_id.strip():
        raise ValidationError("incident_id cannot be empty")
    if not incident.scenario_id or not incident.scenario_id.strip():
        raise ValidationError("scenario_id cannot be empty")

    # 3. reported_at timestamp sanity check
    try:
        reported_dt = datetime.fromisoformat(incident.reported_at.replace("Z", "+00:00"))
    except ValueError:
        raise ValidationError(f"Invalid reported_at ISO timestamp: {incident.reported_at}")

    # 4. Verify reported_at is within investigation window bounds
    start_dt = datetime.fromisoformat(incident.investigation_window.start.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(incident.investigation_window.end.replace("Z", "+00:00"))

    if not (start_dt <= reported_dt <= end_dt):
        raise ValidationError(
            f"reported_at ({incident.reported_at}) falls outside the investigation window "
            f"[{incident.investigation_window.start} to {incident.investigation_window.end}]"
        )


def validate_evidence_list(evidence_list: list[Evidence], incident_id: str, scenario_id: str) -> None:
    """
    Validates a list of evidence items for uniqueness and incident/scenario scope alignment.
    Raises ValidationError if any issues are detected.
    """
    seen_ids = set()
    for e in evidence_list:
        # 1. Check for duplicate evidence IDs
        if e.evidence_id in seen_ids:
            raise ValidationError(f"Duplicate evidence ID detected: {e.evidence_id}")
        seen_ids.add(e.evidence_id)

        # 2. Check incident ID mapping alignment
        if e.incident_id != incident_id:
            raise ValidationError(
                f"Evidence {e.evidence_id} belongs to incident {e.incident_id}, "
                f"but investigation context incident is {incident_id}"
            )

        # 3. Check scenario ID mapping alignment
        if e.scenario_id != scenario_id:
            raise ValidationError(
                f"Evidence {e.evidence_id} belongs to scenario {e.scenario_id}, "
                f"but investigation context scenario is {scenario_id}"
            )


def validate_evidence(evidence: Evidence, incident: IncidentRecord, topology: ServiceTopology) -> None:
    """
    Deterministically validates a single evidence item against incident context and topology boundaries.
    Raises ValidationError on violation.
    """
    if not evidence.evidence_id:
        raise ValidationError("Evidence is missing an evidence_id")

    if not evidence.provenance or not evidence.provenance.dataset:
        raise ValidationError(f"Evidence {evidence.evidence_id} is missing dataset provenance")

    # Check scenario ID matching
    if evidence.scenario_id != incident.scenario_id:
        raise ValidationError(
            f"Evidence {evidence.evidence_id} scenario_id '{evidence.scenario_id}' does not match "
            f"incident scenario_id '{incident.scenario_id}'"
        )

    # Check incident ID matching
    if evidence.incident_id != incident.incident_id:
        raise ValidationError(
            f"Evidence {evidence.evidence_id} incident_id '{evidence.incident_id}' does not match "
            f"incident incident_id '{incident.incident_id}'"
        )

    # Check for future timestamps relative to the investigation window bounds
    if evidence.time_window and evidence.time_window.start:
        try:
            ev_dt = datetime.fromisoformat(evidence.time_window.start.replace("Z", "+00:00"))
            window_end_dt = datetime.fromisoformat(incident.investigation_window.end.replace("Z", "+00:00"))
            if ev_dt > window_end_dt:
                raise ValidationError(
                    f"Evidence {evidence.evidence_id} timestamp '{evidence.time_window.start}' is in the future "
                    f"relative to investigation window end '{incident.investigation_window.end}'"
                )
        except ValueError as ex:
            raise ValidationError(f"Invalid timestamp format in evidence {evidence.evidence_id}: {ex}")

    # Verify service reference exists in service topology nodes
    topology_services = {node.service_id for node in topology.nodes}
    if evidence.service not in topology_services:
        raise ValidationError(
            f"Evidence {evidence.evidence_id} references service '{evidence.service}' which is not present "
            f"in the service topology nodes list: {topology_services}"
        )


def validate_hypothesis_citations(hypothesis: Hypothesis, available_evidence: list[Evidence]) -> tuple[bool, list[str]]:
    """
    Verifies that all evidence IDs cited in the hypothesis are present in the
    collected investigation evidence.
    Returns (True, []) if valid.
    Raises EvidenceGroundingError if any cited evidence ID is missing.
    """
    available_ids = {e.evidence_id for e in available_evidence}
    missing_ids = [eid for eid in hypothesis.evidence_ids if eid not in available_ids]

    if missing_ids:
        raise EvidenceGroundingError(
            f"Hypothesis cites non-existent or uncollected evidence IDs: {missing_ids}"
        )
    return True, []
