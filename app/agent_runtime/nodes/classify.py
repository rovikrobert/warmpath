"""Classify node — determines event priority and affected domain."""

from __future__ import annotations

from typing import Any

from app.agent_runtime.state import WarmPathState


def classify_event(state: WarmPathState) -> dict[str, Any]:
    """Classify event priority based on type and payload signals."""
    event = state["event"]
    event_type = event.get("type", "")
    payload = event.get("payload", {})
    priority = _classify_priority(event_type, payload)
    return {"priority": priority}


def _classify_priority(event_type: str, payload: dict) -> str:
    """Deterministic priority assignment."""
    if event_type == "incident":
        error_count = payload.get("error_count", 0)
        if error_count >= 10:
            return "critical"
        if error_count >= 3:
            return "high"
        return "medium"

    if event_type == "code_change":
        files = payload.get("files_changed", [])
        security_files = [
            f for f in files if "auth" in f or "security" in f or "middleware" in f
        ]
        if security_files:
            return "high"
        return "medium"

    if event_type == "agent_finding":
        severity = payload.get("severity", "medium")
        return severity

    if event_type == "external_signal":
        return "low"

    if event_type == "scheduled_scan":
        return "low"

    return "medium"
