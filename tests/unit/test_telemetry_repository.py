import pytest
from app.config import settings
from app.services.telemetry.repository import ScenarioRepository

@pytest.fixture
def repo():
    scenario_path = settings.GENERATED_DATA_DIR / "SCN-DB-POOL-001"
    return ScenarioRepository(scenario_path)

def test_load_incident(repo):
    incident = repo.load_incident()
    assert incident.incident_id == "INC-0042"
    assert incident.reported_services == ["checkout-service"]

def test_load_evidence(repo):
    evidence = repo.load_evidence()
    assert len(evidence) > 0
    # Make sure all evidence IDs contain -EV-
    for e in evidence:
        assert "-EV-" in e.evidence_id
        assert e.incident_id == "INC-0042"

def test_load_golden_case(repo):
    golden = repo.load_golden_case()
    assert golden.incident_id == "INC-0042"
    assert golden.labels.affected_service == "checkout-service"
    assert len(golden.required_evidence_ids) > 0

def test_load_logs(repo):
    logs = repo.load_logs()
    assert len(logs) > 0
    assert any(x.level == "ERROR" for x in logs)

def test_load_metrics(repo):
    metrics = repo.load_metrics()
    assert len(metrics) > 0
    assert any(x.metric_name == "db_pool_active" for x in metrics)

def test_load_traces(repo):
    traces = repo.load_traces()
    assert len(traces) > 0
    assert any(x.span_kind == "SERVER" for x in traces)

def test_load_deployments(repo):
    deployments = repo.load_deployments()
    assert len(deployments) == 1
    assert deployments[0].event_id == "DEPLOY-0042-001"
