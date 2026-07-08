import pytest
from app.config import settings
from app.services.telemetry import (
    ScenarioRepository,
    LogRepository,
    MetricRepository,
    TraceRepository,
    DeploymentRepository,
    ServiceTopologyRepository,
)
from app.tools import (
    create_default_registry,
    IncidentSummaryTool,
    LogSearchTool,
    MetricAnalysisTool,
    TraceInspectionTool,
    DeploymentHistoryTool,
    ServiceDependencyTool,
    TimeWindowTool,
)
from app.tools.log_tool import LogSearchInput
from app.tools.metric_tool import MetricAnalysisInput
from app.tools.trace_tool import TraceInspectionInput
from app.tools.deployment_tool import DeploymentHistoryInput
from app.tools.topology_tool import ServiceDependencyInput
from app.tools.incident_tool import IncidentSummaryInput
from app.tools.window_tool import TimeWindowInput
from app.common.exceptions import ToolNotFoundError, ValidationError

@pytest.fixture
def repo_bundle():
    scenario_path = settings.GENERATED_DATA_DIR / "SCN-DB-POOL-001"
    scenario_repo = ScenarioRepository(scenario_path)
    return {
        "scenario_repo": scenario_repo,
        "log_repo": LogRepository(scenario_repo),
        "metric_repo": MetricRepository(scenario_repo),
        "trace_repo": TraceRepository(scenario_repo),
        "deploy_repo": DeploymentRepository(scenario_repo),
        "topo_repo": ServiceTopologyRepository(scenario_repo),
    }

@pytest.fixture
def registry(repo_bundle):
    return create_default_registry(
        repo_bundle["scenario_repo"],
        repo_bundle["log_repo"],
        repo_bundle["metric_repo"],
        repo_bundle["trace_repo"],
        repo_bundle["deploy_repo"],
        repo_bundle["topo_repo"],
    )

# --- 1. ToolRegistry Tests ---

def test_registry_lookup(registry):
    tools = registry.list_tools()
    assert len(tools) == 7

    # Positive lookup
    tool = registry.get_tool("log_pattern_search")
    assert isinstance(tool, LogSearchTool)

    # Negative lookup
    with pytest.raises(ToolNotFoundError):
        registry.get_tool("nonexistent_tool")

    # Schemas
    schemas = registry.get_schemas()
    assert "log_pattern_search" in schemas
    assert schemas["log_pattern_search"]["name"] == "log_pattern_search"

    # Duplicate registration check
    with pytest.raises(ValidationError):
        registry.register(registry.get_tool("log_pattern_search"))

def test_evaluation_isolation(repo_bundle, registry):
    # Ensure runtime tools never load golden.json cases
    original_load = repo_bundle["scenario_repo"].load_golden_case
    def mock_load_golden():
        raise RuntimeError("Access denied to golden.json inside runtime tool executions")
    repo_bundle["scenario_repo"].load_golden_case = mock_load_golden

    try:
        # Run all registered tools to verify they do not invoke the mock
        for tool in registry.list_tools():
            if tool.name == "log_pattern_search":
                tool.run()
            elif tool.name == "metric_window_analysis":
                tool.run(metric_name="db_pool_active")
            elif tool.name == "trace_dependency_analysis":
                spans = repo_bundle["trace_repo"].get_spans()
                tool.run(trace_id=spans[0].trace_id)
            elif tool.name == "deployment_event_search":
                tool.run()
            elif tool.name == "service_topology_lookup":
                tool.run(service_id="checkout-service")
            elif tool.name == "incident_summary_lookup":
                tool.run()
            elif tool.name == "time_window_adjuster":
                tool.run(start="2026-01-15T14:00:00Z", end="2026-01-15T14:10:00Z")
    finally:
        repo_bundle["scenario_repo"].load_golden_case = original_load


# --- 2. IncidentSummaryTool Tests ---

def test_incident_summary_tool(repo_bundle):
    tool = IncidentSummaryTool(repo_bundle["scenario_repo"])
    
    # Success execution
    inp = IncidentSummaryInput()
    res = tool.execute(inp)
    assert res.incident_id == "INC-0042"
    assert res.environment == "production-sim"
    assert "checkout-service" in res.reported_services

    # Execution with valid ID matching
    res2 = tool.execute(IncidentSummaryInput(incident_id="INC-0042"))
    assert res2.incident_id == "INC-0042"

    # Execution mismatch raises error
    with pytest.raises(ValidationError):
        tool.execute(IncidentSummaryInput(incident_id="INC-9999"))

# --- 3. LogSearchTool Tests ---

def test_log_search_tool(repo_bundle):
    tool = LogSearchTool(repo_bundle["log_repo"])

    # Empty inputs
    res_empty = tool.execute(LogSearchInput())
    assert len(res_empty.logs) > 0

    # Service search
    res_service = tool.execute(LogSearchInput(service="checkout-service"))
    assert len(res_service.logs) > 0
    assert all(l.service == "checkout-service" for l in res_service.logs)

    # Time filter
    res_time = tool.execute(LogSearchInput(
        start="2026-01-15T14:00:00Z",
        end="2026-01-15T14:10:00Z"
    ))
    assert len(res_time.logs) > 0

    # Pattern match
    res_pattern = tool.execute(LogSearchInput(pattern="timeout"))
    assert len(res_pattern.logs) > 0

# --- 4. MetricAnalysisTool Tests ---

def test_metric_analysis_tool(repo_bundle):
    tool = MetricAnalysisTool(repo_bundle["metric_repo"])

    # Query metrics
    res = tool.execute(MetricAnalysisInput(metric_name="db_pool_active"))
    assert res.points_count > 0

    # Aggregations
    res_agg = tool.execute(MetricAnalysisInput(
        metric_name="db_pool_active",
        aggregator="max"
    ))
    assert res_agg.aggregated_value is not None

    # Gap checks
    res_gap = tool.execute(MetricAnalysisInput(
        metric_name="db_pool_active",
        expected_interval_sec=30
    ))
    assert len(res_gap.gaps) > 0  # Interval is 60s, so 30s threshold triggers gaps

    # Boundary time window filter
    res_window = tool.execute(MetricAnalysisInput(
        metric_name="db_pool_active",
        start="2026-01-15T14:00:00Z",
        end="2026-01-15T14:05:00Z"
    ))
    assert res_window.points_count > 0

# --- 5. TraceInspectionTool Tests ---

def test_trace_inspection_tool(repo_bundle):
    tool = TraceInspectionTool(repo_bundle["trace_repo"])
    spans = repo_bundle["trace_repo"].get_spans()
    target_trace = spans[0].trace_id

    # Trace tree
    res = tool.execute(TraceInspectionInput(trace_id=target_trace))
    assert res.trace_id == target_trace
    assert res.spans_count > 0
    assert "root" in res.tree or len(res.tree) > 0

# --- 6. DeploymentHistoryTool Tests ---

def test_deployment_history_tool(repo_bundle):
    tool = DeploymentHistoryTool(repo_bundle["deploy_repo"])

    # Environment filter
    res = tool.execute(DeploymentHistoryInput(environment="production-sim"))
    assert len(res.deployments) == 1

    # Latest before timestamp
    res_latest = tool.execute(DeploymentHistoryInput(
        environment="production-sim",
        timestamp="2026-01-15T14:05:00Z"
    ))
    assert res_latest.latest_change is not None
    assert res_latest.latest_change.event_id == "DEPLOY-0042-001"

# --- 7. ServiceDependencyTool Tests ---

def test_service_dependency_tool(repo_bundle):
    tool = ServiceDependencyTool(repo_bundle["topo_repo"])

    # Downstream lookup
    res = tool.execute(ServiceDependencyInput(
        service_id="checkout-service",
        direction="downstream"
    ))
    assert "payment-service" in res.connected_services
    assert "checkout-db" in res.connected_services

    # Invalid service name
    with pytest.raises(ValidationError):
        tool.execute(ServiceDependencyInput(service_id="nonexistent-service"))

# --- 8. TimeWindowTool Tests ---

def test_time_window_tool():
    tool = TimeWindowTool()

    # Shift execution
    res = tool.execute(TimeWindowInput(
        start="2026-01-15T14:00:00Z",
        end="2026-01-15T14:10:00Z",
        shift_minutes=5
    ))
    assert res.start == "2026-01-15T13:55:00Z"
    assert res.end == "2026-01-15T14:15:00Z"
