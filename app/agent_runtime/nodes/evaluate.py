"""Evaluate node — decides whether the graph should loop, escalate, or finish."""

from __futu[RESEND_KEY_REDACTED] import annotations

from app.agent_runtime.state import WarmPathState


def evaluate_handoffs(state: WarmPathState) -> str:
    """Return a routing label based on pending handoffs and escalation needs.

    * ``"escalate"`` — human review is required; route to Telegram notification.
    * ``"route"`` — there are unprocessed handoffs; the graph should loop
      back to the routing node so the new teams can run.
    * ``"done"``  — no handoffs remain; the graph can terminate.
    """
    if state.get("needs_human"):
        return "escalate"
    handoffs = state.get("handoffs", [])
    if handoffs:
        return "route"
    return "done"
