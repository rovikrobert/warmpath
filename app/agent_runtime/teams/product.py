"""Product team subgraph -- wraps existing product_team/ scanners."""

from __future__ import annotations

from typing import Any

from app.agent_runtime.teams.base import TeamRunner


class ProductTeam(TeamRunner):
    team_name = "product"
    scanner_modules = {
        "user_researcher": "product_team.user_researcher.user_researcher",
        "product_manager": "product_team.product_manager.product_manager",
        "ux_lead": "product_team.ux_lead.ux_lead",
        "design_lead": "product_team.design_lead.design_lead",
        "product_lead": "product_team.product_lead.product_lead",
    }


_instance = ProductTeam()


def run_existing_scanners(
    scanner_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Backwards-compatible wrapper around TeamRunner.run_scanners()."""
    return _instance.run_scanners(scanner_names)
