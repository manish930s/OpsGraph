from pydantic import BaseModel, Field, field_validator
from typing import Literal
from app.services.telemetry.topology_repository import ServiceTopologyRepository
from app.tools.base import BaseTool
from app.common.exceptions import ValidationError

class ServiceDependencyInput(BaseModel):
    service_id: str = Field(..., description="Target service name to resolve connections for.")
    direction: Literal["upstream", "downstream", "both"] = Field(
        default="both",
        description="Filter direction: 'upstream' (callers), 'downstream' (called), 'both'."
    )

class ServiceDependencyResponse(BaseModel):
    service_id: str
    direction: str
    connected_services: list[str] = Field(default_factory=list)

class ServiceDependencyTool(BaseTool):
    """
    Diagnostic tool to inspect service architecture dependency topology.
    """
    name: str = "service_topology_lookup"
    description: str = (
        "Inspects service topology relationships, returning upstream (caller) "
        "or downstream (called) dependency names."
    )
    args_model: type[BaseModel] = ServiceDependencyInput

    def __init__(self, topo_repo: ServiceTopologyRepository):
        self.topo_repo = topo_repo

    def run(self, service_id: str, direction: Literal["upstream", "downstream", "both"] = "both") -> ServiceDependencyResponse:
        # Validate service exists
        node = self.topo_repo.get_service(service_id)
        if not node:
            raise ValidationError(f"Service not found in topology: '{service_id}'")

        if direction == "upstream":
            connected = self.topo_repo.upstream(service_id)
        elif direction == "downstream":
            connected = self.topo_repo.downstream(service_id)
        else:
            connected = self.topo_repo.dependencies(service_id)

        return ServiceDependencyResponse(
            service_id=service_id,
            direction=direction,
            connected_services=connected
        )
