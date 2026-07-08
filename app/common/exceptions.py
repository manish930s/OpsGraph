class OpsGraphError(Exception):
    """Base exception for all OpsGraph errors."""
    pass

class IncidentNotFoundError(OpsGraphError):
    """Raised when an incident is not found in the scenario repository."""
    def __init__(self, incident_id: str):
        super().__init__(f"Incident not found: {incident_id}")
        self.incident_id = incident_id

class ToolNotFoundError(OpsGraphError):
    """Raised when the planner requests a tool that is not registered."""
    def __init__(self, tool_name: str):
        super().__init__(f"Tool not registered: {tool_name}")
        self.tool_name = tool_name

class ValidationError(OpsGraphError):
    """Raised when a schema validation fails deterministically."""
    pass

class GatewayError(OpsGraphError):
    """Raised when the LLM gateway fails and cannot fall back."""
    pass

class GuardrailsError(OpsGraphError):
    """Raised when conversational guardrails block the query or fail."""
    pass

class EvidenceGroundingError(OpsGraphError):
    """Raised when a generated hypothesis cites invalid or fabricated evidence."""
    pass
