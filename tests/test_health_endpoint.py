"""Tests for /health endpoint status semantics.

Covers the three rollup states: healthy (all deps ok), degraded (non-critical
dep down), and unhealthy (critical dep down → HTTP 503).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.api import health as health_module


# ---------------------------------------------------------------------------
# Helpers — patch the per-dep check functions so we control the rollup inputs
# ---------------------------------------------------------------------------


async def _ok_db() -> dict[str, Any]:
    return {"status": "ok", "latency_ms": 0.5}


async def _down_db() -> dict[str, Any]:
    return {"status": "unavailable", "error": "OperationalError", "latency_ms": 12.3}


def _ok_celery() -> dict[str, Any]:
    return {"status": "ok", "latency_ms": 5.0, "workers": 2}


def _down_celery() -> dict[str, Any]:
    return {"status": "unavailable", "error": "ConnectionError", "latency_ms": 2000.0}


# ---------------------------------------------------------------------------
# Status rollup
# ---------------------------------------------------------------------------


def test_rollup_healthy_when_all_ok() -> None:
    checks = {"db": {"status": "ok"}, "celery": {"status": "ok"}}
    assert health_module._roll_up_status(checks, critical={"db"}) == "healthy"


def test_rollup_degraded_when_noncritical_down() -> None:
    checks = {"db": {"status": "ok"}, "celery": {"status": "unavailable"}}
    assert health_module._roll_up_status(checks, critical={"db"}) == "degraded"


def test_rollup_unhealthy_when_critical_down() -> None:
    checks = {"db": {"status": "unavailable"}, "celery": {"status": "ok"}}
    assert health_module._roll_up_status(checks, critical={"db"}) == "unhealthy"


def test_rollup_unhealthy_takes_precedence_over_degraded() -> None:
    checks = {"db": {"status": "unavailable"}, "celery": {"status": "unavailable"}}
    assert health_module._roll_up_status(checks, critical={"db"}) == "unhealthy"


# ---------------------------------------------------------------------------
# End-to-end via the FastAPI test client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_endpoint_healthy(client: AsyncClient) -> None:
    """All deps ok → HTTP 200, status=healthy, both checks ok."""
    with (
        patch.object(health_module, "_check_db", _ok_db),
        patch.object(health_module, "_check_celery", _ok_celery),
    ):
        resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["status"] == "healthy"
    assert body["celery"] == "connected"
    assert body["checks"]["db"]["status"] == "ok"
    assert body["checks"]["celery"]["status"] == "ok"
    assert body["checks"]["celery"]["workers"] == 2


@pytest.mark.asyncio
async def test_health_endpoint_degraded(client: AsyncClient) -> None:
    """DB ok + Celery down → HTTP 200, status=degraded (still serving traffic)."""
    with (
        patch.object(health_module, "_check_db", _ok_db),
        patch.object(health_module, "_check_celery", _down_celery),
    ):
        resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["status"] == "degraded"
    assert body["celery"] == "unavailable"
    assert body["checks"]["db"]["status"] == "ok"
    assert body["checks"]["celery"]["status"] == "unavailable"
    assert body["checks"]["celery"]["error"] == "ConnectionError"


@pytest.mark.asyncio
async def test_health_endpoint_unhealthy(client: AsyncClient) -> None:
    """DB down → HTTP 503, status=unhealthy (load balancer should eject)."""
    with (
        patch.object(health_module, "_check_db", _down_db),
        patch.object(health_module, "_check_celery", _ok_celery),
    ):
        resp = await client.get("/health")

    assert resp.status_code == 503
    body = resp.json()["data"]
    assert body["status"] == "unhealthy"
    assert body["checks"]["db"]["status"] == "unavailable"
    assert body["checks"]["db"]["error"] == "OperationalError"


@pytest.mark.asyncio
async def test_check_db_swallows_engine_failure() -> None:
    """The real _check_db must never propagate — it returns 'unavailable' on error."""
    with patch("app.database._get_engine", side_effect=RuntimeError("no engine")):
        result = await health_module._check_db()

    assert result["status"] == "unavailable"
    assert result["error"] == "RuntimeError"
    assert "latency_ms" in result
