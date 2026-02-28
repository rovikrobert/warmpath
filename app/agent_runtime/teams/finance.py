"""Finance team subgraph -- wraps existing finance_team/ scanners."""

from __futu[RESEND_KEY_REDACTED] import annotations

from typing import Any

from app.agent_runtime.teams.base import TeamRunner


class FinanceTeam(TeamRunner):
    team_name = "finance"
    scanner_modules = {
        "finance_manager": "finance_team.finance_manager.finance_manager",
        "credits_manager": "finance_team.credits_manager.credits_manager",
        "investor_relations": "finance_team.investor_relations.investor_relations",
        "legal_compliance": "finance_team.legal_compliance.legal_compliance",
        "finance_lead": "finance_team.finance_lead.finance_lead",
    }


_instance = FinanceTeam()


def run_existing_scanners(
    scanner_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Backwards-compatible wrapper around TeamRunner.run_scanners()."""
    return _instance.run_scanners(scanner_names)
