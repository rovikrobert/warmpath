from app.agent_runtime.cost_guard import check_budget, select_model, BudgetStatus


def test_check_budget_ok_when_under_limit():
    assert check_budget(daily_spend=5.0, daily_limit=10.0) == BudgetStatus.OK


def test_check_budget_warning_when_near_limit():
    assert check_budget(daily_spend=8.5, daily_limit=10.0) == BudgetStatus.WARNING


def test_check_budget_exceeded_when_over_limit():
    assert check_budget(daily_spend=11.0, daily_limit=10.0) == BudgetStatus.EXCEEDED


def test_select_model_downgrades_on_warning():
    assert (
        select_model(
            preferred="claude-sonnet-4-20250514", budget_status=BudgetStatus.WARNING
        )
        == "claude-haiku-4-5-20251001"
    )


def test_select_model_uses_preferred_when_ok():
    assert (
        select_model(
            preferred="claude-sonnet-4-20250514", budget_status=BudgetStatus.OK
        )
        == "claude-sonnet-4-20250514"
    )


def test_select_model_blocks_on_exceeded():
    assert (
        select_model(
            preferred="claude-sonnet-4-20250514", budget_status=BudgetStatus.EXCEEDED
        )
        is None
    )
