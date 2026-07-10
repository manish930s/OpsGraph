from typing import TypedDict, Any
from app.schemas.incident import IncidentRecord
from app.schemas.evidence import Evidence
from app.schemas.context import InvestigationContext
from app.schemas.model_response import RCADecisionResponse, CriticDecisionResponse
from app.schemas.orchestration import ToolSelectionDecision, HumanReviewTerminalState, FailureTerminalState

class InvestigationState(TypedDict, total=False):
    investigation_id: str
    incident: IncidentRecord
    iteration_count: int
    tool_call_count: int
    context_rebuild_count: int
    evidence_list: list[Evidence]
    investigation_context: InvestigationContext | None
    current_rca: RCADecisionResponse | None
    critic_decision: CriticDecisionResponse | None
    tool_selection: ToolSelectionDecision | None
    termination_reason: str | None
    human_review: HumanReviewTerminalState | None
    failure: FailureTerminalState | None
