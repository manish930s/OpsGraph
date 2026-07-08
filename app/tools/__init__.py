from app.tools.base import BaseTool
from app.tools.registry import ToolRegistry
from app.tools.log_tool import LogSearchTool
from app.tools.metric_tool import MetricAnalysisTool
from app.tools.trace_tool import TraceInspectionTool
from app.tools.deployment_tool import DeploymentHistoryTool
from app.tools.topology_tool import ServiceDependencyTool
from app.tools.incident_tool import IncidentSummaryTool
from app.tools.window_tool import TimeWindowTool

def create_default_registry(
    scenario_repo,
    log_repo,
    metric_repo,
    trace_repo,
    deploy_repo,
    topo_repo,
) -> ToolRegistry:
    """
    Dependency injection helper to bootstrap the central ToolRegistry
    and register all standard diagnostic tools.
    """
    registry = ToolRegistry()
    registry.register(IncidentSummaryTool(scenario_repo))
    registry.register(LogSearchTool(log_repo))
    registry.register(MetricAnalysisTool(metric_repo))
    registry.register(TraceInspectionTool(trace_repo))
    registry.register(DeploymentHistoryTool(deploy_repo))
    registry.register(ServiceDependencyTool(topo_repo))
    registry.register(TimeWindowTool())
    return registry

__all__ = [
    "BaseTool",
    "ToolRegistry",
    "LogSearchTool",
    "MetricAnalysisTool",
    "TraceInspectionTool",
    "DeploymentHistoryTool",
    "ServiceDependencyTool",
    "IncidentSummaryTool",
    "TimeWindowTool",
    "create_default_registry",
]
