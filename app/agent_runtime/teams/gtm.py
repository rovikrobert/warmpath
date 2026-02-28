"""GTM team subgraph -- wraps existing gtm_team/ scanners."""

from __future__ import annotations

from typing import Any

from app.agent_runtime.teams.base import TeamRunner


class GtmTeam(TeamRunner):
    team_name = "gtm"
    scanner_modules = {
        "stratops": "gtm_team.stratops.scanner",
        "monetization": "gtm_team.monetization.scanner",
        "marketing": "gtm_team.marketing.scanner",
        "partnerships": "gtm_team.partnerships.scanner",
        "gtm_lead": "gtm_team.gtm_lead.scanner",
    }


_instance = GtmTeam()


def run_existing_scanners(
    scanner_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Backwards-compatible wrapper around TeamRunner.run_scanners()."""
    return _instance.run_scanners(scanner_names)
