"""Data team subgraph -- wraps existing data_team/ scanners."""

from __future__ import annotations

from typing import Any

from app.agent_runtime.teams.base import TeamRunner


class DataTeam(TeamRunner):
    team_name = "data"
    scanner_modules = {
        "pipeline": "data_team.pipeline.pipeline",
        "analyst": "data_team.analyst.analyst",
        "model_engineer": "data_team.model_engineer.model_engineer",
        "data_lead": "data_team.data_lead.data_lead",
    }


_instance = DataTeam()


def run_existing_scanners(
    scanner_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Backwards-compatible wrapper around TeamRunner.run_scanners()."""
    return _instance.run_scanners(scanner_names)
