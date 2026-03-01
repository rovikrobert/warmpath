"""Shared state schema for the LangGraph agent runtime."""

from __future__ import annotations

from enum import Enum
from typing import Any

from typing_extensions import TypedDict


class EventType(str, Enum):
    CODE_CHANGE = "code_change"
    INCIDENT = "incident"
    EXTERNAL_SIGNAL = "external_signal"
    AGENT_FINDING = "agent_finding"


class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class WarmPathState(TypedDict):
    """Root state flowing through the CoS supervisor graph."""

    event: dict[str, Any]
    routed_teams: list[str]
    priority: str
    trust_level: int
    findings: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    needs_human: bool
    human_decision: str
    handoffs: list[dict[str, Any]]
