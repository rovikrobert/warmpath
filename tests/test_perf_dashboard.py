"""Test perf dashboard endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_perf_dashboard_returns_structure(client: AsyncClient):
    """Dashboard returns expected top-level keys and data structure."""
    resp = await client.get("/health/perf/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "meta" in body
    data = body["data"]
    assert "timing_stats" in data
    assert "celery" in data
    assert "query_budgets" in data
    assert "daily_report" in data
    assert isinstance(data["timing_stats"], list)
    assert isinstance(data["query_budgets"], list)


@pytest.mark.asyncio
async def test_perf_dashboard_query_budgets_have_fields(client: AsyncClient):
    """Each query budget entry includes method, path, and limit fields."""
    resp = await client.get("/health/perf/dashboard")
    data = resp.json()["data"]
    assert len(data["query_budgets"]) > 0
    first = data["query_budgets"][0]
    assert "method" in first
    assert "path" in first
    assert "max_queries" in first
    assert "max_latency_ms" in first


@pytest.mark.asyncio
async def test_perf_dashboard_meta_has_thresholds(client: AsyncClient):
    """Meta section includes operations_tracked count and thresholds dict."""
    resp = await client.get("/health/perf/dashboard")
    meta = resp.json()["meta"]
    assert "operations_tracked" in meta
    assert "thresholds" in meta
    assert isinstance(meta["thresholds"], dict)
