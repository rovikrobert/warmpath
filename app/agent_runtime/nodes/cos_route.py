# app/agent_runtime/nodes/cos_route.py
"""CoS routing node — assigns events to 1-3 teams."""

from __future__ import annotations

from typing import Any

from app.agent_runtime.state import WarmPathState

_EVENT_ROUTING: dict[str, dict[str, list[str]]] = {
    "incident": {
        "default": ["engineering"],
        "critical": ["engineering", "ops"],
    },
    "code_change": {
        "default": ["engineering"],
    },
    "external_signal": {
        "competitor_update": ["gtm"],
        "job_board_update": ["data"],
        "pricing_change": ["gtm", "finance"],
        "default": ["gtm"],
    },
    "agent_finding": {
        "security": ["engineering"],
        "performance": ["engineering", "data"],
        "ux": ["product"],
        "marketplace": ["ops"],
        "cost": ["finance"],
        "kpi_anomaly": ["engineering", "data"],
        "default": ["engineering"],
    },
    "scheduled_scan": {
        "daily": ["engineering", "data", "product", "ops", "gtm", "finance"],
        "weekly": ["engineering", "data", "product", "ops", "gtm", "finance"],
        "default": ["engineering", "data", "product", "ops", "gtm", "finance"],
    },
}


def cos_route(state: WarmPathState) -> dict[str, Any]:
    """Route event to the appropriate team(s)."""
    event = state["event"]
    priority = state["priority"]
    event_type = event.get("type", "")
    payload = event.get("payload", {})
    teams = _route_deterministic(event_type, priority, payload)
    return {"routed_teams": teams}


def _route_deterministic(event_type: str, priority: str, payload: dict) -> list[str]:
    """Deterministic team routing based on event type and payload."""
    type_routes = _EVENT_ROUTING.get(event_type, {"default": ["engineering"]})

    if priority in type_routes:
        return list(type_routes[priority])

    signal_type = payload.get("signal_type", "")
    if signal_type in type_routes:
        return list(type_routes[signal_type])

    category = payload.get("category", "")
    if category in type_routes:
        return list(type_routes[category])

    return list(type_routes.get("default", ["engineering"]))
