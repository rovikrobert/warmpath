from __future__ import annotations

from enum import Enum


class BudgetStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"
    EXCEEDED = "exceeded"


def check_budget(daily_spend: float, daily_limit: float) -> BudgetStatus:
    if daily_spend >= daily_limit:
        return BudgetStatus.EXCEEDED
    if daily_spend >= daily_limit * 0.8:
        return BudgetStatus.WARNING
    return BudgetStatus.OK


def select_model(preferred: str, budget_status: BudgetStatus) -> str | None:
    if budget_status == BudgetStatus.EXCEEDED:
        return None
    if budget_status == BudgetStatus.WARNING:
        return "claude-haiku-4-5-20251001"
    return preferred
