"""Root LangGraph definition -- CoS supervisor graph.

This is the main orchestration graph. It classifies events, routes them
to team subgraphs, synthesizes findings, and decides whether to act,
escalate, or loop back for cross-team handoffs.
"""

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.agent_runtime.nodes.classify import classify_event
from app.agent_runtime.nodes.cos_route import cos_route
from app.agent_runtime.nodes.evaluate import evaluate_handoffs
from app.agent_runtime.nodes.synthesize import synthesize_findings
from app.agent_runtime.nodes.telegram_escalate import send_escalation
from app.agent_runtime.state import WarmPathState

logger = logging.getLogger(__name__)


async def _team_dispatch(
    state: WarmPathState, config: RunnableConfig | None = None
) -> dict:
    """Run team scanners with optional SDK augmentation.

    Each team's TeamRunner.run() executes: scan → SDK augment → return.
    Trust level and budget status flow from graph config.
    """
    from app.agent_runtime.cost_guard import BudgetStatus
    from app.agent_runtime.teams.data import DataTeam
    from app.agent_runtime.teams.engineering import EngineeringTeam
    from app.agent_runtime.teams.finance import FinanceTeam
    from app.agent_runtime.teams.gtm import GtmTeam
    from app.agent_runtime.teams.ops import OpsTeam
    from app.agent_runtime.teams.product import ProductTeam
    from app.agent_runtime.trust import TrustLevel

    teams = state.get("routed_teams", [])
    findings = list(state.get("findings", []))

    configurable = (config or {}).get("configurable", {})
    trust_level = configurable.get("trust_level", TrustLevel.RECOMMENDER)
    budget_status = configurable.get("budget_status", BudgetStatus.OK)

    team_runners = {
        "engineering": EngineeringTeam(),
        "data": DataTeam(),
        "product": ProductTeam(),
        "ops": OpsTeam(),
        "gtm": GtmTeam(),
        "finance": FinanceTeam(),
    }

    for team_name in teams:
        runner = team_runners.get(team_name)
        if runner:
            team_findings = await runner.run(
                event=state.get("event", {}),
                trust_level=trust_level,
                budget_status=budget_status,
            )
            findings.extend(team_findings)

    return {"findings": findings}


async def _escalate(state: WarmPathState) -> dict[str, Any]:
    """Send Telegram escalation notification for human review."""
    event = state.get("event", {})
    findings = state.get("findings", [])
    priority = state.get("priority", "medium")

    summary_parts = [f.get("title", "") for f in findings[:3]]
    summary = "; ".join(summary_parts) if summary_parts else "No findings summary"

    try:
        await send_escalation(
            event_type=event.get("type", "unknown"),
            priority=priority,
            findings_count=len(findings),
            summary=summary,
        )
    except Exception:
        logger.exception("Failed to send Telegram escalation")

    return {"needs_human": True}


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
    builder.add_node("escalate", _escalate)
    builder.add_node("consume_handoffs", _consume_handoffs)

    # Edges
    builder.add_edge(START, "classify")
    builder.add_edge("classify", "cos_route")
    builder.add_edge("cos_route", "team_dispatch")
    builder.add_edge("team_dispatch", "synthesize")
    builder.add_edge("synthesize", "evaluate")

    # Conditional: escalate, loop back for handoffs, or end
    builder.add_conditional_edges(
        "evaluate",
        evaluate_handoffs,
        {
            "escalate": "escalate",
            "route": "consume_handoffs",
            "done": END,
        },
    )
    builder.add_edge("escalate", END)
    builder.add_edge("consume_handoffs", "cos_route")

    return builder
