import pytest
from pathlib import Path
from app.config import settings
from app.services.telemetry.repository import ScenarioRepository
from app.services.telemetry.log_repository import LogRepository
from app.services.telemetry.metric_repository import MetricRepository
from app.services.telemetry.trace_repository import TraceRepository
from app.services.telemetry.deployment_repository import DeploymentRepository
from app.services.telemetry.topology_repository import ServiceTopologyRepository
from app.common.exceptions import ValidationError

@pytest.fixture
def repo():
    scenario_path = settings.GENERATED_DATA_DIR / "SCN-DB-POOL-001"
    return ScenarioRepository(scenario_path)

# --- 1. General Repository & Loader Tests ---

def test_scenario_missing():
    with pytest.raises(FileNotFoundError):
        ScenarioRepository(Path("nonexistent/scenario/path"))

def test_missing_files_graceful(tmp_path):
    # Setup temporary directory containing only incident.json to pass incident validation
    incident_file = tmp_path / "incident.json"
    incident_file.write_text("""{
        "schema_version": "1.0",
        "incident_id": "INC-0042",
        "scenario_id": "SCN-DB-POOL-001",
        "title": "Incident Title",
        "description": "Incident Desc",
        "environment": "production-sim",
        "reported_services": ["checkout-service"],
        "reported_symptoms": ["high latency"],
        "reported_at": "2026-01-15T14:10:00Z",
        "investigation_window": {
            "start": "2026-01-15T13:55:00Z",
            "end": "2026-01-15T14:30:00Z"
        },
        "status": "open"
    }""", encoding="utf-8")
    
    empty_repo = ScenarioRepository(tmp_path)
    assert empty_repo.load_logs() == []
    assert empty_repo.load_metrics() == []
    assert empty_repo.load_traces() == []
    assert empty_repo.load_deployments() == []

# --- 2. LogRepository Tests ---

def test_log_repository_filters(repo):
    log_repo = LogRepository(repo)
    logs = log_repo.get_logs()
    assert len(logs) > 0

    # Service filter positive
    service_logs = log_repo.filter_by_service("checkout-service")
    assert len(service_logs) > 0
    assert all(l.service == "checkout-service" for l in service_logs)

    # Service filter negative
    with pytest.raises(ValidationError):
        log_repo.filter_by_service("   ")

    # Time window filter positive
    window_logs = log_repo.filter_by_time_window("2026-01-15T14:00:00Z", "2026-01-15T14:10:00Z")
    assert len(window_logs) <= len(logs)

    # Time window filter negative (invalid format)
    with pytest.raises(ValidationError):
        log_repo.filter_by_time_window("invalid-date", "2026-01-15T14:10:00Z")

    # Time window filter negative (chronological violation)
    with pytest.raises(ValidationError):
        log_repo.filter_by_time_window("2026-01-15T14:15:00Z", "2026-01-15T14:10:00Z")

    # Search patterns
    matched_logs = log_repo.search_patterns("timeout")
    assert len(matched_logs) <= len(logs)

    # Search patterns invalid regex
    with pytest.raises(ValidationError):
        log_repo.search_patterns("[unclosed-regex")

# --- 3. MetricRepository Tests ---

def test_metric_repository_queries(repo):
    metric_repo = MetricRepository(repo)
    metrics = metric_repo.get_metrics()
    assert len(metrics) > 0

    # Get specific metric
    active_metrics = metric_repo.get_metric("db_pool_active")
    assert len(active_metrics) > 0
    assert all(m.metric_name == "db_pool_active" for m in active_metrics)

    # Get metric window
    window_metrics = metric_repo.get_metric_window("db_pool_active", "2026-01-15T14:00:00Z", "2026-01-15T14:10:00Z")
    assert len(window_metrics) <= len(active_metrics)

    # Aggregators
    avg_val = metric_repo.aggregate("db_pool_active", "avg")
    max_val = metric_repo.aggregate("db_pool_active", "max")
    min_val = metric_repo.aggregate("db_pool_active", "min")
    sum_val = metric_repo.aggregate("db_pool_active", "sum")

    assert avg_val is not None
    assert max_val >= min_val
    assert sum_val >= max_val

    # Aggregators invalid type
    with pytest.raises(ValidationError):
        metric_repo.aggregate("db_pool_active", "invalid_agg")

    # Gap detection
    # SCN-DB-POOL-001 has metrics every 60 seconds. Gap detection at 60s should find no gaps.
    gaps = metric_repo.detect_missing_points("db_pool_active", 60)
    assert len(gaps) == 0

    # Gap detection invalid parameters
    with pytest.raises(ValidationError):
        metric_repo.detect_missing_points("db_pool_active", 0)

# --- 4. TraceRepository Tests ---

def test_trace_repository_queries(repo):
    trace_repo = TraceRepository(repo)
    spans = trace_repo.get_spans()
    assert len(spans) > 0

    # Get specific trace
    target_trace_id = spans[0].trace_id
    trace_spans = trace_repo.get_trace(target_trace_id)
    assert len(trace_spans) > 0
    assert all(s.trace_id == target_trace_id for s in trace_spans)

    # Filter by service
    checkout_spans = trace_repo.filter_by_service("checkout-service")
    assert len(checkout_spans) > 0

    # Trace tree grouping
    tree = trace_repo.get_trace_tree(target_trace_id)
    assert len(tree) > 0
    assert "root" in tree or any(parent in tree for parent in tree.keys())

# --- 5. DeploymentRepository Tests ---

def test_deployment_repository_queries(repo):
    deploy_repo = DeploymentRepository(repo)
    deployments = deploy_repo.get_deployments()
    assert len(deployments) == 1

    # Filter environment
    env_deployments = deploy_repo.filter_by_environment("production-sim")
    assert len(env_deployments) == 1

    # Filter env empty error
    with pytest.raises(ValidationError):
        deploy_repo.filter_by_environment("")

    # Latest before timestamp
    latest = deploy_repo.latest_before("2026-01-15T14:05:00Z")
    assert latest is not None
    assert latest.event_id == "DEPLOY-0042-001"

    # None before early date
    none_latest = deploy_repo.latest_before("2026-01-15T13:00:00Z")
    assert none_latest is None

# --- 6. ServiceTopologyRepository Tests ---

def test_topology_repository_queries(repo):
    topo_repo = ServiceTopologyRepository(repo)
    topology = topo_repo.get_topology()
    assert len(topology.nodes) > 0

    # Get specific service
    checkout_node = topo_repo.get_service("checkout-service")
    assert checkout_node is not None
    assert checkout_node.type == "service"

    # Invalid service name
    with pytest.raises(ValidationError):
        topo_repo.get_service("")

    # Upstream lookup (source caller)
    # api-gateway calls checkout-service. So checkout-service's upstream should include api-gateway.
    upstreams = topo_repo.upstream("checkout-service")
    assert "api-gateway" in upstreams

    # Downstream lookup (targets called)
    # checkout-service calls payment-service and checkout-db.
    downstreams = topo_repo.downstream("checkout-service")
    assert "payment-service" in downstreams
    assert "checkout-db" in downstreams

    # Dependencies (all connected services)
    deps = topo_repo.dependencies("checkout-service")
    assert "api-gateway" in deps
    assert "payment-service" in deps
    assert "checkout-db" in deps

    # Upstream invalid service error
    with pytest.raises(ValidationError):
        topo_repo.upstream("non-existent-service")
