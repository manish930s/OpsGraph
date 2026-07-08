from app.schemas.telemetry import ServiceTopology, TopologyNode
from app.services.telemetry.base import BaseTelemetryRepository
from app.common.exceptions import ValidationError

class ServiceTopologyRepository(BaseTelemetryRepository):
    """
    Read-only repository for mapping service dependency topologies.
    """
    def __init__(self, scenario_repo):
        super().__init__(scenario_repo)
        self._topology = None  # lazy-loaded repository state

    def _get_all(self) -> ServiceTopology:
        if self._topology is None:
            self._topology = self.repo.load_topology()
        return self._topology

    def get_topology(self) -> ServiceTopology:
        return self._get_all()

    def get_service(self, service_id: str) -> TopologyNode | None:
        if not service_id:
            raise ValidationError("service_id cannot be empty")
        for node in self._get_all().nodes:
            if node.service_id == service_id:
                return node
        return None

    def upstream(self, service_id: str) -> list[str]:
        """
        Returns services that call the target service_id (source nodes pointing to target).
        """
        if not service_id:
            raise ValidationError("service_id cannot be empty")
        # Validate service exists
        if not self.get_service(service_id):
            raise ValidationError(f"Service not found in topology: {service_id}")
            
        upstreams = []
        for edge in self._get_all().edges:
            if edge.target == service_id:
                upstreams.append(edge.source)
        return upstreams

    def downstream(self, service_id: str) -> list[str]:
        """
        Returns services that are called by the target service_id (target nodes called by source).
        """
        if not service_id:
            raise ValidationError("service_id cannot be empty")
        # Validate service exists
        if not self.get_service(service_id):
            raise ValidationError(f"Service not found in topology: {service_id}")

        downstreams = []
        for edge in self._get_all().edges:
            if edge.source == service_id:
                downstreams.append(edge.target)
        return downstreams

    def dependencies(self, service_id: str) -> list[str]:
        """
        Returns all immediate direct connections (upstream + downstream).
        """
        return list(set(self.upstream(service_id) + self.downstream(service_id)))
