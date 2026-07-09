import logging
from typing import Any
from app.config import settings
from app.schemas.incident import IncidentRecord
from app.schemas.evidence import Evidence
from app.schemas.telemetry import ServiceTopology
from app.schemas.orchestration import (
    ToolSelectionDecision,
    HumanReviewTerminalState,
    FailureTerminalState
)
from app.services.orchestration.state import InvestigationState
from app.services.evidence.normalizer import EvidenceNormalizer
from app.services.evidence.packager import EvidencePackager
from app.services.context.builder import ContextBuilder
from app.services.prompting.assembler import PromptAssembler
from app.services.gateway.gateway import LLMGateway
from app.services.knowledge.retriever import HybridRetriever
from app.tools.registry import ToolRegistry

logger = logging.getLogger("opsgraph.orchestration.nodes")

class WorkflowNodes:
    """
    Dependency-injected SRE workflow nodes for LangGraph orchestration.
    """
    def __init__(
        self,
        gateway: LLMGateway,
        retriever: HybridRetriever,
        tool_registry: ToolRegistry,
        topology: ServiceTopology
    ):
        self.gateway = gateway
        self.retriever = retriever
        self.tool_registry = tool_registry
        self.topology = topology
        self.evidence_packager = EvidencePackager()

    def initialize_investigation(self, state: InvestigationState) -> dict[str, Any]:
        logger.info(f"Initializing investigation for incident: {state.get('investigation_id')}")
        incident: IncidentRecord = state["incident"]
        
        # Initialize evidence with base incident record normalized into evidence
        normalizer = EvidenceNormalizer(incident.incident_id, incident.scenario_id)
        base_ev = normalizer.normalize_incident(
            incident_id=incident.incident_id,
            title=incident.title,
            description=incident.description,
            reported_services=list(incident.reported_services),
            reported_symptoms=list(incident.reported_symptoms),
            reported_at=incident.reported_at,
            investigation_window=incident.investigation_window.model_dump()
        )
        
        return {
            "iteration_count": 0,
            "tool_call_count": 0,
            "context_rebuild_count": 0,
            "evidence_list": [base_ev],
            "investigation_context": None,
            "current_rca": None,
            "critic_decision": None,
            "tool_selection": None,
            "termination_reason": None,
            "human_review": None,
            "failure": None
        }

    def build_context(self, state: InvestigationState) -> dict[str, Any]:
        logger.info("Building initial investigation context.")
        incident: IncidentRecord = state["incident"]
        evidences = state.get("evidence_list", [])

        try:
            # 1. Package evidence list into bundle (this performs validation)
            evidence_bundle = self.evidence_packager.package_bundle(evidences, incident, self.topology)

            # 2. Retrieve matching runbooks/knowledge using incident title/symptoms
            query = f"{incident.title} {' '.join(incident.reported_symptoms)}"
            knowledge_bundle = self.retriever.retrieve(query, evidence_bundle=evidence_bundle, limit=3)

            # 3. Build context
            context_builder = ContextBuilder()
            context = context_builder.build(evidence_bundle, knowledge_bundle)
            return {"investigation_context": context}
        except Exception as e:
            logger.error(f"Context build failure: {str(e)}", exc_info=True)
            return {
                "failure": FailureTerminalState(
                    incident_id=incident.incident_id,
                    failure_type="CONTEXT_BUILD_FAILURE",
                    error_message=f"Context build failure: {str(e)}"
                )
            }

    def generate_hypothesis(self, state: InvestigationState) -> dict[str, Any]:
        logger.info("Generating RCA hypothesis.")
        context = state.get("investigation_context")
        incident = state["incident"]
        if not context:
            return {
                "failure": FailureTerminalState(
                    incident_id=incident.incident_id,
                    failure_type="MISSING_CONTEXT",
                    error_message="No investigation context available to generate hypothesis."
                )
            }

        # Increment iteration count
        iters = state.get("iteration_count", 0) + 1

        try:
            # Assemble request for task type "rca"
            request = PromptAssembler.assemble(context, task_type="rca")
            response = self.gateway.generate(request)
            return {
                "current_rca": response.parsed_response,
                "iteration_count": iters
            }
        except Exception as e:
            logger.error(f"Hypothesis generation failed: {str(e)}")
            return {
                "failure": FailureTerminalState(
                    incident_id=incident.incident_id,
                    failure_type="GATEWAY_FAILURE",
                    error_message=f"Hypothesis generation failed: {str(e)}"
                )
            }

    def evaluate_hypothesis(self, state: InvestigationState) -> dict[str, Any]:
        logger.info("Evaluating hypothesis via Critic.")
        context = state.get("investigation_context")
        rca = state.get("current_rca")
        incident = state["incident"]
        if not context or not rca:
            return {
                "failure": FailureTerminalState(
                    incident_id=incident.incident_id,
                    failure_type="MISSING_CONTEXT",
                    error_message="Cannot evaluate hypothesis: context or current_rca is missing."
                )
            }

        try:
            # Assemble request for task type "critic"
            request = PromptAssembler.assemble(
                context,
                task_type="critic",
                draft_rca=rca.model_dump_json()
            )
            response = self.gateway.generate(request)
            return {"critic_decision": response.parsed_response}
        except Exception as e:
            logger.error(f"Critic evaluation failed: {str(e)}")
            return {
                "failure": FailureTerminalState(
                    incident_id=incident.incident_id,
                    failure_type="GATEWAY_FAILURE",
                    error_message=f"Critic evaluation failed: {str(e)}"
                )
            }

    def identify_evidence_gap(self, state: InvestigationState) -> dict[str, Any]:
        critic = state.get("critic_decision")
        gaps = critic.evidence_gaps if critic else ()
        logger.info(f"Critic identified evidence gaps: {gaps}")
        return {}

    def select_tool(self, state: InvestigationState) -> dict[str, Any]:
        logger.info("Selecting next diagnostic tool to execute.")
        context = state.get("investigation_context")
        rca = state.get("current_rca")
        critic = state.get("critic_decision")
        incident = state["incident"]

        if not context or not rca or not critic:
            return {
                "failure": FailureTerminalState(
                    incident_id=incident.incident_id,
                    failure_type="MISSING_CONTEXT",
                    error_message="Cannot select tool: missing context, rca, or critic decision."
                )
            }

        try:
            # Compile allowed tools and their schemas
            allowed_schemas = self.tool_registry.get_schemas()
            import json
            schemas_str = json.dumps(allowed_schemas, indent=2)

            request = PromptAssembler.assemble(
                context,
                task_type="tool_selection",
                draft_rca=rca.model_dump_json(),
                critic_findings=", ".join(critic.findings),
                critic_suggestions=", ".join(critic.suggestions),
                allowed_tools_schemas=schemas_str
            )
            response = self.gateway.generate(request)
            return {"tool_selection": response.parsed_response}
        except Exception as e:
            logger.error(f"Tool selection failed: {str(e)}")
            return {
                "failure": FailureTerminalState(
                    incident_id=incident.incident_id,
                    failure_type="GATEWAY_FAILURE",
                    error_message=f"Tool selection failed: {str(e)}"
                )
            }

    def execute_tool(self, state: InvestigationState) -> dict[str, Any]:
        logger.info("Executing selected tool.")
        selection: ToolSelectionDecision = state.get("tool_selection")
        incident = state["incident"]
        tools_run = state.get("tool_call_count", 0) + 1

        if not selection:
            return {
                "failure": FailureTerminalState(
                    incident_id=incident.incident_id,
                    failure_type="MISSING_TOOL_SELECTION",
                    error_message="No tool selected to execute."
                )
            }

        # Validate tool against allowlist
        try:
            tool = self.tool_registry.get_tool(selection.tool_name)
        except Exception as e:
            logger.error(f"Tool '{selection.tool_name}' not found in registry: {str(e)}")
            return {
                "failure": FailureTerminalState(
                    incident_id=incident.incident_id,
                    failure_type="TOOL_NOT_FOUND",
                    error_message=f"Tool '{selection.tool_name}' is not in the allowlist registry."
                )
            }

        # Parameter validation
        try:
            args_model = tool.args_model
            validated_params = args_model(**selection.parameters)
        except Exception as e:
            logger.error(f"Parameter validation failed for tool '{selection.tool_name}': {str(e)}")
            return {
                "failure": FailureTerminalState(
                    incident_id=incident.incident_id,
                    failure_type="TOOL_PARAMETER_INVALID",
                    error_message=f"Parameters invalid for tool '{selection.tool_name}': {str(e)}"
                )
            }

        # Bounded Tool Execution
        try:
            tool_output = tool.run(**validated_params.model_dump())
            
            # Evidence Normalization
            normalizer = EvidenceNormalizer(incident.incident_id, incident.scenario_id)
            new_evidences = []
            
            if selection.tool_name == "log_pattern_search":
                new_evidences = normalizer.normalize_logs(tool_output.logs)
            elif selection.tool_name == "metric_window_analysis":
                # Metric tool returns values
                new_evidences = normalizer.normalize_metrics(
                    tool_output.points,
                    metric_name=selection.parameters.get("metric_name", "unknown")
                )
            elif selection.tool_name == "trace_dependency_analysis":
                new_evidences = normalizer.normalize_traces(
                    tool_output.spans,
                    trace_id=selection.parameters.get("trace_id", "unknown")
                )
            elif selection.tool_name == "deployment_event_search":
                new_evidences = normalizer.normalize_deployments(tool_output.deployments)
            elif selection.tool_name == "service_topology_lookup":
                new_evidences = [
                    normalizer.normalize_topology(
                        service_id=selection.parameters.get("service_id"),
                        direction=selection.parameters.get("direction", "downstream"),
                        connected_services=list(tool_output.connected_services)
                    )
                ]
            else:
                # Custom/fallback normalization
                logger.warning(f"No specific normalizer for tool: {selection.tool_name}")
                new_evidences = []

            # Filter evidence count limit
            current_evidence = list(state.get("evidence_list", []))
            for ev in new_evidences:
                if len(current_evidence) < settings.INVESTIGATION_MAX_EVIDENCE_ITEMS:
                    current_evidence.append(ev)

            return {
                "evidence_list": current_evidence,
                "tool_call_count": tools_run
            }
        except Exception as e:
            logger.error(f"Tool execution failure: {str(e)}")
            return {
                "failure": FailureTerminalState(
                    incident_id=incident.incident_id,
                    failure_type="TOOL_EXECUTION_FAILURE",
                    error_message=f"Tool execution failure: {str(e)}"
                )
            }

    def validate_evidence(self, state: InvestigationState) -> dict[str, Any]:
        logger.info("Validating new evidence.")
        return {}

    def rebuild_context(self, state: InvestigationState) -> dict[str, Any]:
        logger.info("Rebuilding investigation context.")
        incident: IncidentRecord = state["incident"]
        evidences = state.get("evidence_list", [])
        rebuilds = state.get("context_rebuild_count", 0) + 1

        try:
            # Package evidences (which runs validate_evidence internally)
            evidence_bundle = self.evidence_packager.package_bundle(evidences, incident, self.topology)

            # Retrieve matching runbooks
            query = f"{incident.title} {' '.join(incident.reported_symptoms)}"
            knowledge_bundle = self.retriever.retrieve(query, evidence_bundle=evidence_bundle, limit=3)

            # Build context
            context_builder = ContextBuilder()
            context = context_builder.build(evidence_bundle, knowledge_bundle)
            return {
                "investigation_context": context,
                "context_rebuild_count": rebuilds
            }
        except Exception as e:
            logger.error(f"Context rebuild failure: {str(e)}")
            return {
                "failure": FailureTerminalState(
                    incident_id=incident.incident_id,
                    failure_type="CONTEXT_REBUILD_FAILURE",
                    error_message=f"Context rebuild failure: {str(e)}"
                )
            }

    def finalize_rca(self, state: InvestigationState) -> dict[str, Any]:
        logger.info("Finalizing successful RCA.")
        return {"termination_reason": "RCA accepted by critic"}

    def human_review(self, state: InvestigationState) -> dict[str, Any]:
        logger.info("Investigation escalated to human review.")
        incident = state["incident"]
        critic = state.get("critic_decision")
        gaps = critic.evidence_gaps if critic else ()
        
        escalation_reason = "Critic requested human review or iteration budget exhausted."
        if state.get("iteration_count", 0) >= settings.INVESTIGATION_MAX_ITERATIONS:
            escalation_reason = "Max investigation iteration limit reached."
        elif state.get("tool_call_count", 0) >= settings.INVESTIGATION_MAX_TOOL_CALLS:
            escalation_reason = "Max tool call budget exhausted."
        elif state.get("context_rebuild_count", 0) >= settings.INVESTIGATION_MAX_CONTEXT_REBUILDS:
            escalation_reason = "Max context rebuild budget reached."

        review = HumanReviewTerminalState(
            incident_id=incident.incident_id,
            current_rca=state.get("current_rca"),
            gaps=tuple(gaps),
            reason=escalation_reason,
            recommended_actions=critic.suggestions if critic else ()
        )
        return {
            "termination_reason": "Escalated to human review",
            "human_review": review
        }

    def failure(self, state: InvestigationState) -> dict[str, Any]:
        logger.info("Investigation encountered a fatal graph failure.")
        return {"termination_reason": "Investigation failure"}
