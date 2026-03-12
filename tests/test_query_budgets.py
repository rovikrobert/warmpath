"""Verify query budgets are well-formed and importable."""

from app.utils.query_budgets import ENDPOINT_BUDGETS, get_budget


def test_budgets_have_required_keys():
    for key, budget in ENDPOINT_BUDGETS.items():
        assert "max_queries" in budget, f"Missing max_queries for {key}"
        assert "max_latency_ms" in budget, f"Missing max_latency_ms for {key}"
        assert budget["max_queries"] >= 0
        assert budget["max_latency_ms"] > 0


def test_get_budget_match():
    budget = get_budget("GET", "/api/v1/contacts")
    assert budget is not None
    assert budget["max_queries"] == 8


def test_get_budget_no_match():
    assert get_budget("DELETE", "/api/v1/nonexistent") is None


def test_health_has_zero_query_budget():
    budget = get_budget("GET", "/health")
    assert budget is not None
    assert budget["max_queries"] == 0
