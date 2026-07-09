import logging
from langgraph.graph import StateGraph, START, END
from app.services.orchestration.state import InvestigationState
from app.services.orchestration.nodes import WorkflowNodes
from app.services.orchestration.routing import route_after_evaluation

logger = logging.getLogger("opsgraph.orchestration.graph")

def route_after_context_build(state: InvestigationState) -> str:
    if state.get("failure") is not None:
        return "failure"
    return "generate_hypothesis"

def route_after_hypothesis_gen(state: InvestigationState) -> str:
    if state.get("failure") is not None:
        return "failure"
    return "evaluate_hypothesis"

def route_after_tool_selection(state: InvestigationState) -> str:
    if state.get("failure") is not None:
        return "failure"
    return "execute_tool"

def route_after_tool_execution(state: InvestigationState) -> str:
    if state.get("failure") is not None:
        return "failure"
    return "validate_evidence"

def route_after_rebuild(state: InvestigationState) -> str:
    if state.get("failure") is not None:
        return "failure"
    return "generate_hypothesis"

def create_investigation_graph(nodes: WorkflowNodes) -> StateGraph:
    """
    Constructs and compiles the StateGraph linking all SRE node contracts.
    """
    workflow = StateGraph(InvestigationState)

    # Add all nodes
    workflow.add_node("initialize", nodes.initialize_investigation)
    workflow.add_node("build_context", nodes.build_context)
    workflow.add_node("generate_hypothesis", nodes.generate_hypothesis)
    workflow.add_node("evaluate_hypothesis", nodes.evaluate_hypothesis)
    workflow.add_node("identify_evidence_gap", nodes.identify_evidence_gap)
    workflow.add_node("select_tool", nodes.select_tool)
    workflow.add_node("execute_tool", nodes.execute_tool)
    workflow.add_node("validate_evidence", nodes.validate_evidence)
    workflow.add_node("rebuild_context", nodes.rebuild_context)
    workflow.add_node("finalize_rca", nodes.finalize_rca)
    workflow.add_node("human_review", nodes.human_review)
    workflow.add_node("failure", nodes.failure)

    # Establish flow topology
    workflow.add_edge(START, "initialize")
    workflow.add_edge("initialize", "build_context")

    workflow.add_conditional_edges(
        "build_context",
        route_after_context_build,
        {
            "failure": "failure",
            "generate_hypothesis": "generate_hypothesis"
        }
    )

    workflow.add_conditional_edges(
        "generate_hypothesis",
        route_after_hypothesis_gen,
        {
            "failure": "failure",
            "evaluate_hypothesis": "evaluate_hypothesis"
        }
    )

    workflow.add_conditional_edges(
        "evaluate_hypothesis",
        route_after_evaluation,
        {
            "finalize_rca": "finalize_rca",
            "identify_evidence_gap": "identify_evidence_gap",
            "human_review": "human_review",
            "failure": "failure"
        }
    )

    workflow.add_edge("identify_evidence_gap", "select_tool")

    workflow.add_conditional_edges(
        "select_tool",
        route_after_tool_selection,
        {
            "failure": "failure",
            "execute_tool": "execute_tool"
        }
    )

    workflow.add_conditional_edges(
        "execute_tool",
        route_after_tool_execution,
        {
            "failure": "failure",
            "validate_evidence": "validate_evidence"
        }
    )

    workflow.add_edge("validate_evidence", "rebuild_context")

    workflow.add_conditional_edges(
        "rebuild_context",
        route_after_rebuild,
        {
            "failure": "failure",
            "generate_hypothesis": "generate_hypothesis"
        }
    )

    # Terminals
    workflow.add_edge("finalize_rca", END)
    workflow.add_edge("human_review", END)
    workflow.add_edge("failure", END)

    return workflow
