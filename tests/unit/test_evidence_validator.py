import pytest
from app.common.exceptions import ValidationError, EvidenceGroundingError
from app.schemas.incident import IncidentRecord
from app.schemas.evidence import Evidence, EvidenceProvenance
from app.schemas.rca import Hypothesis
from app.services.evidence.validator import (
    validate_incident_record,
    validate_evidence_list,
    validate_hypothesis_citations,
)

@pytest.fixture
def base_incident():
    return IncidentRecord(
        schema_version="1.0",
        incident_id="INC-0042",
        scenario_id="SCN-DB-POOL-001",
        title="Incident Title",
        description="Incident Desc",
        environment="production-sim",
        severity="SEV-1",
        reported_services=["checkout-service"],
        reported_symptoms=["high latency"],
        reported_at="2026-01-15T14:10:00Z",
        investigation_window={
            "start": "2026-01-15T13:55:00Z",
            "end": "2026-01-15T14:30:00Z"
        },
        status="open"
    )

@pytest.fixture
def mock_evidence():
    return Evidence(
        schema_version="1.0",
        evidence_id="METRIC-EV-0042-001",
        incident_id="INC-0042",
        scenario_id="SCN-DB-POOL-001",
        source_type="metric",
        source_name="db_pool_active",
        service="checkout-service",
        time_window={"start": "2026-01-15T14:05:00Z", "end": "2026-01-15T14:10:00Z"},
        observation="Saturation of db pool connections",
        provenance={"dataset": "generated-v1", "record_reference": "ref-1"}
    )


def test_validate_incident_record_valid(base_incident):
    # Should complete without error
    validate_incident_record(base_incident)

def test_validate_incident_record_invalid_reported_at(base_incident):
    # reported_at outside the investigation window bounds
    base_incident.reported_at = "2026-01-15T14:45:00Z"
    with pytest.raises(ValidationError) as excinfo:
        validate_incident_record(base_incident)
    assert "falls outside the investigation window" in str(excinfo.value)

def test_validate_evidence_list_duplicate_id(mock_evidence):
    ev1 = mock_evidence
    ev2 = mock_evidence.model_copy(update={"evidence_id": "METRIC-EV-0042-001"})
    
    with pytest.raises(ValidationError) as excinfo:
        validate_evidence_list([ev1, ev2], "INC-0042", "SCN-DB-POOL-001")
    assert "Duplicate evidence ID detected" in str(excinfo.value)

def test_validate_evidence_list_cross_incident_check(mock_evidence):
    ev = mock_evidence.model_copy(update={"incident_id": "INC-9999"})
    with pytest.raises(ValidationError) as excinfo:
        validate_evidence_list([ev], "INC-0042", "SCN-DB-POOL-001")
    assert "belongs to incident INC-9999" in str(excinfo.value)

def test_validate_hypothesis_citations_valid(mock_evidence):
    h = Hypothesis(
        cause="Configuration issue",
        affected_service="checkout-service",
        evidence_ids=["METRIC-EV-0042-001"]
    )
    # Should pass without error
    valid, missing = validate_hypothesis_citations(h, [mock_evidence])
    assert valid is True

def test_validate_hypothesis_citations_invalid(mock_evidence):
    h = Hypothesis(
        cause="Configuration issue",
        affected_service="checkout-service",
        evidence_ids=["METRIC-EV-0042-001", "FABRICATED-EV-999"]
    )
    with pytest.raises(EvidenceGroundingError) as excinfo:
        validate_hypothesis_citations(h, [mock_evidence])
    assert "cites non-existent or uncollected evidence" in str(excinfo.value)

def test_validate_incident_record_empty_services(base_incident):
    base_incident.reported_services = []
    with pytest.raises(ValidationError) as excinfo:
        validate_incident_record(base_incident)
    assert "reported_services list cannot be empty" in str(excinfo.value)

def test_validate_incident_record_invalid_service_type(base_incident):
    base_incident.reported_services = ["checkout-service", ""]
    with pytest.raises(ValidationError) as excinfo:
        validate_incident_record(base_incident)
    assert "Invalid service name" in str(excinfo.value)

def test_validate_incident_record_empty_incident_id(base_incident):
    base_incident.incident_id = "   "
    with pytest.raises(ValidationError) as excinfo:
        validate_incident_record(base_incident)
    assert "incident_id cannot be empty" in str(excinfo.value)

