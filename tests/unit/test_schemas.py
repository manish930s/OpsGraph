import pytest
from pydantic import ValidationError
from app.schemas.common import TimeWindow
from app.schemas.incident import IncidentRecord
from app.common.enums import Severity, EnvironmentName

def test_time_window_validation():
    # Valid window
    tw = TimeWindow(start="2026-01-15T13:55:00Z", end="2026-01-15T14:30:00Z")
    assert tw.start == "2026-01-15T13:55:00Z"
    
    # Invalid ISO format
    with pytest.raises(ValidationError):
        TimeWindow(start="invalid-date", end="2026-01-15T14:30:00Z")

    # Chronology validation error (start > end)
    with pytest.raises(ValidationError) as excinfo:
        TimeWindow(start="2026-01-15T14:35:00Z", end="2026-01-15T14:30:00Z")
    assert "Start time" in str(excinfo.value)

def test_incident_record_validation():
    # Valid payload
    valid_payload = {
        "schema_version": "1.0",
        "incident_id": "INC-0042",
        "scenario_id": "SCN-DB-POOL-001",
        "title": "Checkout Latency Spike",
        "description": "Failures on DB pool connection requests",
        "environment": "production-sim",
        "severity": "SEV-1",
        "reported_services": ["checkout-service"],
        "reported_symptoms": ["HTTP 503 increase"],
        "reported_at": "2026-01-15T14:10:00Z",
        "investigation_window": {
            "start": "2026-01-15T13:55:00Z",
            "end": "2026-01-15T14:30:00Z"
        },
        "status": "open"
    }
    
    record = IncidentRecord.model_validate(valid_payload)
    assert record.incident_id == "INC-0042"
    assert record.severity == Severity.SEV_1
    assert record.environment == EnvironmentName.PRODUCTION_SIM

    # Invalid severity
    invalid_severity = valid_payload.copy()
    invalid_severity["severity"] = "SEV-999"
    with pytest.raises(ValidationError):
        IncidentRecord.model_validate(invalid_severity)
