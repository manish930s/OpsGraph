import pytest
from datetime import datetime, timedelta
from app.config import settings
from app.services.telemetry import ScenarioRepository, ServiceTopologyRepository
from app.schemas.incident import IncidentRecord
from app.schemas.common import TimeWindow
from app.schemas.evidence import Evidence, EvidenceProvenance, EvidenceRetrievalMetadata
from app.common.enums import SourceType, Severity, EnvironmentName
from app.common.exceptions import ValidationError
from app.services.evidence import (
    EvidenceNormalizer,
    EvidenceAggregator,
    EvidenceDeduplicator,
    EvidenceConfidenceScorer,
    EvidenceTimeline,
    EvidencePackager,
    EvidenceQueryAPI,
    validate_evidence,
)

@pytest.fixture
def context_bundle():
    scenario_path = settings.GENERATED_DATA_DIR / "SCN-DB-POOL-001"
    repo = ScenarioRepository(scenario_path)
    topo_repo = ServiceTopologyRepository(repo)
    incident = repo.load_incident()
    topology = topo_repo.get_topology()
    return {
        "incident": incident,
        "topology": topology,
        "repo": repo,
    }

# --- 1. EvidenceNormalizer Tests ---

def test_normalization(context_bundle):
    normalizer = EvidenceNormalizer(
        incident_id=context_bundle["incident"].incident_id,
        scenario_id=context_bundle["incident"].scenario_id
    )

    # Normalize incident context
    ev_incident = normalizer.normalize_incident(
        incident_id="INC-0042",
        title="DB saturation",
        description="Active pool high utilization",
        reported_services=["checkout-service"],
        reported_symptoms=["high latency"],
        reported_at="2026-01-15T14:10:00Z",
        investigation_window={"start": "2026-01-15T13:55:00Z", "end": "2026-01-15T14:30:00Z"}
    )
    assert ev_incident.source_type == SourceType.HISTORICAL_INCIDENT
    assert ev_incident.service == "checkout-service"

    # Normalize telemetry mocks
    logs = context_bundle["repo"].load_logs()
    ev_logs = normalizer.normalize_logs(logs[:3])
    assert len(ev_logs) == 3
    assert all(e.source_type == SourceType.LOG for e in ev_logs)

    metrics = context_bundle["repo"].load_metrics()
    ev_metrics = normalizer.normalize_metrics(metrics[:3], "db_pool_active")
    assert len(ev_metrics) == 3
    assert all(e.source_type == SourceType.METRIC for e in ev_metrics)

    traces = context_bundle["repo"].load_traces()
    ev_traces = normalizer.normalize_traces(traces[:3], "trace-1234")
    assert len(ev_traces) == 3
    assert all(e.source_type == SourceType.TRACE for e in ev_traces)

    deploys = context_bundle["repo"].load_deployments()
    ev_deploys = normalizer.normalize_deployments(deploys)
    assert len(ev_deploys) == len(deploys)
    assert all(e.source_type == SourceType.DEPLOYMENT for e in ev_deploys)

    ev_topo = normalizer.normalize_topology(
        service_id="checkout-service",
        direction="downstream",
        connected_services=["payment-service"]
    )
    assert ev_topo.source_type == SourceType.TOPOLOGY
    assert ev_topo.service == "checkout-service"

# --- 2. EvidenceAggregator & Timeline Tests ---

def test_aggregation_and_timeline(context_bundle):
    normalizer = EvidenceNormalizer(
        incident_id=context_bundle["incident"].incident_id,
        scenario_id=context_bundle["incident"].scenario_id
    )
    
    logs = context_bundle["repo"].load_logs()
    ev_logs = normalizer.normalize_logs(logs[:2])
    
    deploys = context_bundle["repo"].load_deployments()
    ev_deploys = normalizer.normalize_deployments(deploys)

    aggregator = EvidenceAggregator()
    merged = aggregator.merge(ev_logs, ev_deploys)
    assert len(merged) == len(ev_logs) + len(ev_deploys)

    # Timeline sequencing
    timeline_builder = EvidenceTimeline()
    sorted_ev = timeline_builder.build_timeline(merged)
    # Check chronological ordering
    timestamps = [e.time_window.start for e in sorted_ev if e.time_window]
    assert timestamps == sorted(timestamps)

    # Slicing
    sliced = timeline_builder.filter_by_window(merged, "2026-01-15T14:00:00Z", "2026-01-15T14:05:00Z")
    assert len(sliced) <= len(merged)

# --- 3. EvidenceDeduplicator Tests ---

def test_deduplicator():
    dedup = EvidenceDeduplicator()

    # Create duplicates with identical source records
    ev1 = Evidence(
        evidence_id="LOG-EV-SCN-0001",
        incident_id="INC-0042",
        scenario_id="SCN-001",
        source_type=SourceType.LOG,
        service="checkout-service",
        observation="Connection timeout",
        source_record_ids=["log-1"],
        provenance=EvidenceProvenance(dataset="logs", record_reference="log-1", query_reference="q1")
    )
    ev2 = Evidence(
        evidence_id="LOG-EV-SCN-0002",
        incident_id="INC-0042",
        scenario_id="SCN-001",
        source_type=SourceType.LOG,
        service="checkout-service",
        observation="Connection timeout",
        source_record_ids=["log-1"],  # Match source record ID
        provenance=EvidenceProvenance(dataset="logs", record_reference="log-1", query_reference="q2")
    )

    results = dedup.deduplicate([ev1, ev2])
    assert len(results) == 1
    # Check merged provenance query strings
    assert "q1" in results[0].provenance.query_reference
    assert "q2" in results[0].provenance.query_reference

# --- 4. EvidenceConfidenceScorer Tests ---

def test_confidence_scorer(context_bundle):
    scorer = EvidenceConfidenceScorer()
    
    # 1. No evidence
    res_zero = scorer.compute_confidence([], context_bundle["incident"])
    assert res_zero.score == 0.0
    assert res_zero.band == "LOW"

    # 2. Setup mock evidence
    ev = Evidence(
        evidence_id="LOG-EV-SCN-0001",
        incident_id=context_bundle["incident"].incident_id,
        scenario_id=context_bundle["incident"].scenario_id,
        source_type=SourceType.LOG,
        service="checkout-service",
        observation="Pool saturation",
        source_record_ids=["r1"],
        provenance=EvidenceProvenance(dataset="logs", record_reference="r1"),
        time_window=TimeWindow(start="2026-01-15T14:10:00Z", end="2026-01-15T14:10:00Z")
    )
    res = scorer.compute_confidence([ev], context_bundle["incident"])
    assert res.score > 0.0

# --- 5. Deterministic Validator Rejection Tests ---

def test_validator_rejections(context_bundle):
    incident = context_bundle["incident"]
    topology = context_bundle["topology"]

    # Valid base item
    valid_ev = Evidence(
        evidence_id="LOG-EV-SCN-0001",
        incident_id=incident.incident_id,
        scenario_id=incident.scenario_id,
        source_type=SourceType.LOG,
        service="checkout-service",
        observation="Valid observation",
        source_record_ids=["r1"],
        provenance=EvidenceProvenance(dataset="logs", record_reference="r1"),
        time_window=TimeWindow(start="2026-01-15T14:00:00Z", end="2026-01-15T14:00:00Z")
    )

    # 1. Reject missing IDs
    with pytest.raises(ValidationError):
        bad = valid_ev.model_copy(update={"evidence_id": ""})
        validate_evidence(bad, incident, topology)

    # 2. Reject cross-scenario items
    with pytest.raises(ValidationError):
        bad = valid_ev.model_copy(update={"scenario_id": "SCN-OTHER-POOL"})
        validate_evidence(bad, incident, topology)

    # 3. Reject cross-incident items
    with pytest.raises(ValidationError):
        bad = valid_ev.model_copy(update={"incident_id": "INC-OTHER-99"})
        validate_evidence(bad, incident, topology)

    # 4. Reject future timestamps (beyond investigation window end)
    # Context investigation end is 2026-01-15T14:30:00Z
    with pytest.raises(ValidationError):
        bad = valid_ev.model_copy(update={
            "time_window": TimeWindow(start="2026-01-15T15:00:00Z", end="2026-01-15T15:00:00Z")
        })
        validate_evidence(bad, incident, topology)

    # 5. Reject invalid service names (not in topology nodes)
    with pytest.raises(ValidationError):
        bad = valid_ev.model_copy(update={"service": "fake-billing-service"})
        validate_evidence(bad, incident, topology)

# --- 6. EvidencePackager & QueryAPI Tests ---

def test_packager_and_query_api(context_bundle):
    incident = context_bundle["incident"]
    topology = context_bundle["topology"]

    ev1 = Evidence(
        evidence_id="LOG-EV-SCN-0001",
        incident_id=incident.incident_id,
        scenario_id=incident.scenario_id,
        source_type=SourceType.LOG,
        service="checkout-service",
        observation="Valid observation",
        source_record_ids=["r1"],
        provenance=EvidenceProvenance(dataset="logs", record_reference="r1"),
        time_window=TimeWindow(start="2026-01-15T14:05:00Z", end="2026-01-15T14:05:00Z")
    )
    ev2 = Evidence(
        evidence_id="METRIC-EV-SCN-0002",
        incident_id=incident.incident_id,
        scenario_id=incident.scenario_id,
        source_type=SourceType.METRIC,
        service="payment-service",
        observation="High error rate",
        source_record_ids=["m1"],
        provenance=EvidenceProvenance(dataset="metrics", record_reference="m1"),
        time_window=TimeWindow(start="2026-01-15T14:08:00Z", end="2026-01-15T14:08:00Z")
    )

    packager = EvidencePackager()
    bundle = packager.package_bundle([ev1, ev2], incident, topology)

    assert bundle.validation_status == "valid"
    assert len(bundle.evidence_list) == 2
    assert "checkout-service" in bundle.coverage_summary

    # Query API
    query_api = EvidenceQueryAPI(bundle)
    
    # Query service
    assert len(query_api.query_by_service("checkout-service")) == 1
    
    # Query type
    assert len(query_api.query_by_type("log")) == 1

    # Query window
    window_res = query_api.query_by_time_window("2026-01-15T14:00:00Z", "2026-01-15T14:06:00Z")
    assert len(window_res) == 1
    assert window_res[0].evidence_id == "LOG-EV-SCN-0001"
