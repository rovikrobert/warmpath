"""Root LangGraph definition -- CoS supervisor graph.

This is the main orchestration graph. It classifies events, routes them
to team subgraphs, synthesizes findings, and decides whether to act,
escalate, or loop back for cross-team handoffs.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent_runtime.nodes.classify import classify_event
from app.agent_runtime.nodes.cos_route import cos_route
from app.agent_runtime.nodes.evaluate import evaluate_handoffs
from app.agent_runtime.nodes.synthesize import synthesize_findings
from app.agent_runtime.state import WarmPathState


def _team_dispatch(state: WarmPathState) -> dict:
    """Placeholder for parallel team execution via Send().

    Phase 1: Runs engineering scanners synchronously.
    Phase 2: Will use LangGraph Send() for parallel Claude Agent SDK sessions.
    """
    from app.agent_runtime.teams.engineering import run_existing_scanners

    teams = state.get("routed_teams", [])
    findings = list(state.get("findings", []))

    if "engineering" in teams:
        findings.extend(run_existing_scanners())

    # Other teams will be added in subsequent tasks
    return {"findings": findings}


def _consume_handoffs(state: WarmPathState) -> dict:
    """Convert pending handoffs into routed_teams for the next loop."""
    handoffs = state.get("handoffs", [])
    teams = list({h["to_team"] for h in handoffs})
    return {"routed_teams": teams, "handoffs": []}  # Clear processed handoffs


MAX_HANDOFF_LOOPS = 5


def build_graph() -> StateGraph:
    """Build the CoS supervisor graph (uncompiled).

    Call .compile() to get a runnable graph. The recursion_limit is set
    to MAX_HANDOFF_LOOPS * nodes_per_loop to guard against infinite
    cross-team handoff cycles.
    """
    builder = StateGraph(WarmPathState)

    # Nodes
    builder.add_node("classify", classify_event)
    builder.add_node("cos_route", cos_route)
    builder.add_node("team_dispatch", _team_dispatch)
    builder.add_node("synthesize", synthesize_findings)
    builder.add_node("evaluate", lambda state: state)  # Routing logic is in the edge
    builder.add_node("consume_handoffs", _consume_handoffs)

    # Edges
    builder.add_edge(START, "classify")
    builder.add_edge("classify", "cos_route")
    builder.add_edge("cos_route", "team_dispatch")
    builder.add_edge("team_dispatch", "synthesize")
    builder.add_edge("synthesize", "evaluate")

    # Conditional: loop back for handoffs or end
    builder.add_conditional_edges(
        "evaluate",
        evaluate_handoffs,
        {
            "route": "consume_handoffs",
            "done": END,
        },
    )
    builder.add_edge("consume_handoffs", "cos_route")

    return builder
