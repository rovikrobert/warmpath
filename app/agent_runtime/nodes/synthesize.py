"""Synthesize node — collects cross-team handoff requests from findings."""

from __futu[RESEND_KEY_REDACTED] import annotations

from typing import Any

from app.agent_runtime.nodes.escalate import should_escalate
from app.agent_runtime.state import WarmPathState


def synthesize_findings(state: WarmPathState) -> dict[str, Any]:
    """Extract cross-team handoff requests and escalation flag from findings.

    Scans each finding for a ``cross_team_request`` dict.  When present the
    request is promoted to a top-level handoff entry so the graph can route
    the event to the requested team on the next iteration.

    Also checks whether the event priority + trust level warrants human
    escalation via Telegram.
    """
    handoffs: list[dict[str, Any]] = list(state.get("handoffs", []))
    for finding in state.get("findings", []):
        req = finding.get("cross_team_request")
        if req:
            handoffs.append(
                {
                    "from_team": finding.get("source_team", "unknown"),
                    "to_team": req["to_team"],
                    "reason": req.get("reason", ""),
                    "context": finding,
                }
            )

    # Determine if the event warrants human escalation.
    # Default trust level is RECOMMENDER (1) from runner.py config.
    priority = state.get("priority", "low")
    needs_human = should_escalate(priority, max_trust_level=1)

    return {"handoffs": handoffs, "needs_human": needs_human}
