from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from app.common.enums import EnvironmentName

def _validate_iso(v: str) -> str:
    try:
        datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"Invalid ISO-8601 timestamp: {v}")
    return v

class LogRecord(BaseModel):
    timestamp: str
    log_id: str
    service: str
    environment: EnvironmentName
    instance_id: str
    level: str
    logger: str
    message: str
    template_id: str
    trace_id: str | None = None
    span_id: str | None = None
    attributes: dict = Field(default_factory=dict)
    scenario_id: str

    @field_validator("timestamp")
    @classmethod
    def val_time(cls, v: str) -> str:
        return _validate_iso(v)

class MetricPoint(BaseModel):
    timestamp: str
    metric_id: str
    service: str
    instance_id: str
    metric_name: str
    value: float
    unit: str
    environment: EnvironmentName
    scenario_id: str

    @field_validator("timestamp")
    @classmethod
    def val_time(cls, v: str) -> str:
        return _validate_iso(v)

class TraceSpan(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    timestamp: str
    duration_ms: float
    service: str
    operation: str
    span_kind: str
    status: str
    attributes: dict = Field(default_factory=dict)
    scenario_id: str

    @field_validator("timestamp")
    @classmethod
    def val_time(cls, v: str) -> str:
        return _validate_iso(v)

class DeploymentEvent(BaseModel):
    event_id: str
    timestamp: str
    event_type: str
    service: str
    environment: EnvironmentName
    version_from: str
    version_to: str
    change_summary: str
    change_codes: list[str] = Field(default_factory=list)
    actor_type: str
    scenario_id: str

    @field_validator("timestamp")
    @classmethod
    def val_time(cls, v: str) -> str:
        return _validate_iso(v)

class TopologyNode(BaseModel):
    service_id: str
    type: str

class TopologyEdge(BaseModel):
    source: str
    target: str
    protocol: str

class ServiceTopology(BaseModel):
    topology_version: str
    environment: EnvironmentName
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]
