"""Engineering team subgraph -- wraps existing agents/ scanners."""

from __future__ import annotations

from typing import Any

from app.agent_runtime.teams.base import TeamRunner


class EngineeringTeam(TeamRunner):
    team_name = "engineering"
    scanner_modules = {
        "architect": "agents.architect.architect",
        "test_engineer": "agents.test_engineer.test_engineer",
        "perf_monitor": "agents.perf_monitor.perf_monitor",
        "deps_manager": "agents.deps_manager.deps_manager",
        "security": "agents.security.security",
        "privy": "agents.privy.privy",
    }


_instance = EngineeringTeam()


def run_existing_scanners(
    scanner_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Backwards-compatible wrapper around TeamRunner.run_scanners()."""
    return _instance.run_scanners(scanner_names)
