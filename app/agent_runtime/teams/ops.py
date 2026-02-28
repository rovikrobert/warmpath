"""Ops team subgraph -- wraps existing ops_team/ scanners."""

from __futu[RESEND_KEY_REDACTED] import annotations

from typing import Any

from app.agent_runtime.teams.base import TeamRunner


class OpsTeam(TeamRunner):
    team_name = "ops"
    scanner_modules = {
        "keevs": "ops_team.keevs.keevs",
        "treb": "ops_team.treb.treb",
        "naiv": "ops_team.naiv.naiv",
        "marsh": "ops_team.marsh.marsh",
        "ops_lead": "ops_team.ops_lead.ops_lead",
    }


_instance = OpsTeam()


def run_existing_scanners(
    scanner_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Backwards-compatible wrapper around TeamRunner.run_scanners()."""
    return _instance.run_scanners(scanner_names)
