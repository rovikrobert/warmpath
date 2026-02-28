"""Evaluate node — decides whether the graph should loop or finish."""

from __futu[RESEND_KEY_REDACTED] import annotations

from app.agent_runtime.state import WarmPathState


def evaluate_handoffs(state: WarmPathState) -> str:
    """Return a routing label based on pending handoffs.

    * ``"route"`` — there are unprocessed handoffs; the graph should loop
      back to the routing node so the new teams can run.
    * ``"done"``  — no handoffs remain; the graph can terminate.
    """
    handoffs = state.get("handoffs", [])
    if handoffs:
        return "route"
    return "done"
