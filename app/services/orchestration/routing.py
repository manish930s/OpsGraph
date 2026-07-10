import logging
from app.config import settings
from app.services.orchestration.state import InvestigationState

logger = logging.getLogger("opsgraph.orchestration.routing")

def route_after_evaluation(state: InvestigationState) -> str:
    """
    Deterministic routing function after the critic evaluates the hypothesis.
    """
    if state.get("failure") is not None:
        logger.warning("Routing to failure node due to existing failure in state.")
        return "failure"

    critic = state.get("critic_decision")
    if not critic:
        logger.error("Missing critic decision in state. Escalating to human review.")
        return "human_review"

    decision = critic.decision

    # Check hard budgets
    max_iters = settings.INVESTIGATION_MAX_ITERATIONS
    max_tools = settings.INVESTIGATION_MAX_TOOL_CALLS
    max_rebuilds = settings.INVESTIGATION_MAX_CONTEXT_REBUILDS

    iters = state.get("iteration_count", 0)
    tools = state.get("tool_call_count", 0)
    rebuilds = state.get("context_rebuild_count", 0)

    logger.info(
        f"Routing evaluation: decision={decision}, iters={iters}/{max_iters}, "
        f"tools={tools}/{max_tools}, rebuilds={rebuilds}/{max_rebuilds}"
    )

    # Enforce confidence threshold and consistency on ACCEPT
    if decision == "ACCEPT":
        if not critic.is_valid:
            logger.warning("Critic accepted RCA but is_valid is False. Demoting to CONTINUE_INVESTIGATION.")
            decision = "CONTINUE_INVESTIGATION"
        elif critic.confidence_score < settings.INVESTIGATION_CONFIDENCE_THRESHOLD:
            logger.warning(
                f"Critic accepted RCA but confidence {critic.confidence_score} is below threshold "
                f"{settings.INVESTIGATION_CONFIDENCE_THRESHOLD}. Demoting to CONTINUE_INVESTIGATION."
            )
            decision = "CONTINUE_INVESTIGATION"
        else:
            return "finalize_rca"
    
    if decision == "HUMAN_REVIEW":
        return "human_review"

    if decision in ("CONTINUE_INVESTIGATION", "REJECT"):
        # Check if budgets are exhausted
        if iters >= max_iters or tools >= max_tools or rebuilds >= max_rebuilds:
            logger.warning("Investigation budget exhausted. Routing to human review.")
            return "human_review"
        return "identify_evidence_gap"

    # Defensive default
    logger.warning(f"Unknown critic decision '{decision}'. Routing to human review.")
    return "human_review"
