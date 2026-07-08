import pytest
import hashlib
from datetime import datetime
from app.config import settings
from app.services.telemetry import ScenarioRepository, ServiceTopologyRepository
from app.schemas.common import TimeWindow
from app.schemas.evidence import Evidence, EvidenceProvenance, EvidenceRetrievalMetadata, EvidenceBundle
from app.common.enums import SourceType
from app.common.exceptions import ValidationError
from app.services.evidence.identity import compute_evidence_hash
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

# --- 1. EvidenceNormalizer & SHA-256 Hashing Tests ---

def test_normalization_and_sha256(context_bundle):
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

    # Verify SHA-256 hashing is correct
    t_start = ev_incident.time_window.start if ev_incident.time_window else None
    computed = compute_evidence_hash(ev_incident.observation, ev_incident.service, t_start)
    
    # Assert it is a valid SHA-256 hex string (64 characters)
    assert len(computed) == 64
    
    # Assert SHA-256 formula
    hasher = hashlib.sha256()
    payload = f"{ev_incident.observation}|{ev_incident.service}|{t_start}"
    hasher.update(payload.encode("utf-8"))
    assert computed == hasher.hexdigest()

# --- 2. EvidenceBundle Immutability Tests ---

def test_evidence_bundle_immutability(context_bundle):
    incident = context_bundle["incident"]
    topology = context_bundle["topology"]

    ev1 = Evidence(
        evidence_id="LOG-EV-SCN-0001",
        incident_id=incident.incident_id,
        scenario_id=incident.scenario_id,
        source_type=SourceType.LOG,
        service="checkout-service",
        observation="Observation 1",
        source_record_ids=["r1"],
        provenance=EvidenceProvenance(dataset="logs", record_reference="r1"),
        time_window=TimeWindow(start="2026-01-15T14:05:00Z", end="2026-01-15T14:05:00Z")
    )

    packager = EvidencePackager()
    bundle = packager.package_bundle([ev1], incident, topology)

    # Attempt to modify packaged bundle attributes should raise PydanticValidationError or TypeError
    from pydantic import ValidationError as PydanticValidationError
    with pytest.raises((PydanticValidationError, TypeError)):
        # Attempt to modify a frozen attribute
        # In Pydantic v2, this raises PydanticValidationError
        # On some objects, it might raise TypeError
        object.__setattr__(bundle, "validation_status", "invalid")
        # Direct attribute assignment is blocked and raises PydanticValidationError:
        bundle.validation_status = "invalid"

    with pytest.raises((PydanticValidationError, TypeError)):
        # Attempt to modify the immutable tuple
        bundle.evidence_list[0] = None

# --- 3. Stable Ingestion Timeline Sorting Tests ---

def test_stable_timeline_sorting():
    timeline_builder = EvidenceTimeline()

    # Three events with the exact same timestamp but different sequence orders
    ev_a = Evidence(
        evidence_id="LOG-EV-SCN-0001",
        incident_id="INC-0042",
        scenario_id="SCN-001",
        source_type=SourceType.LOG,
        service="checkout-service",
        observation="A",
        source_record_ids=["a"],
        provenance=EvidenceProvenance(dataset="logs", record_reference="a"),
        time_window=TimeWindow(start="2026-01-15T14:00:00Z", end="2026-01-15T14:00:00Z")
    )
    ev_b = Evidence(
        evidence_id="LOG-EV-SCN-0002",
        incident_id="INC-0042",
        scenario_id="SCN-001",
        source_type=SourceType.LOG,
        service="checkout-service",
        observation="B",
        source_record_ids=["b"],
        provenance=EvidenceProvenance(dataset="logs", record_reference="b"),
        time_window=TimeWindow(start="2026-01-15T14:00:00Z", end="2026-01-15T14:00:00Z")
    )

    # Ingestion order: ev_a followed by ev_b
    sorted_1 = timeline_builder.build_timeline([ev_a, ev_b])
    assert sorted_1[0].observation == "A"
    assert sorted_1[1].observation == "B"

    # Ingestion order: ev_b followed by ev_a
    sorted_2 = timeline_builder.build_timeline([ev_b, ev_a])
    assert sorted_2[0].observation == "B"
    assert sorted_2[1].observation == "A"

# --- 4. EvidenceConfidenceScorer Components Tests ---

def test_confidence_components_scorer(context_bundle):
    scorer = EvidenceConfidenceScorer()
    
    # 1. No evidence
    res_zero = scorer.compute_confidence([], context_bundle["incident"])
    assert res_zero.score == 0.0
    assert res_zero.components.evidence_coverage == 0.0

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
    assert res.components.evidence_coverage > 0.0
    assert res.supporting_evidence_count == 1
    assert "log" not in res.missing_evidence_categories

# --- 5. Deterministic Validator Rejection Tests ---

def test_validator_rejections(context_bundle):
    incident = context_bundle["incident"]
    topology = context_bundle["topology"]

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
    with pytest.raises(ValidationError):
        bad = valid_ev.model_copy(update={
            "time_window": TimeWindow(start="2026-01-15T15:00:00Z", end="2026-01-15T15:00:00Z")
        })
        validate_evidence(bad, incident, topology)

    # 5. Reject invalid service names (not in topology nodes)
    with pytest.raises(ValidationError):
        bad = valid_ev.model_copy(update={"service": "fake-billing-service"})
        validate_evidence(bad, incident, topology)

    # 6. Reject missing provenance dataset
    with pytest.raises(ValidationError):
        bad = valid_ev.model_copy(update={
            "provenance": EvidenceProvenance(dataset="", record_reference="r1")
        })
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
    assert len(query_api.query_by_service("checkout-service")) == 1
    assert len(query_api.query_by_type("log")) == 1

    window_res = query_api.query_by_time_window("2026-01-15T14:00:00Z", "2026-01-15T14:06:00Z")
    assert len(window_res) == 1
    assert window_res[0].evidence_id == "LOG-EV-SCN-0001"
