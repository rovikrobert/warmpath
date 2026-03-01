"""Tests for agent runtime Telegram notifications."""

import pytest
import fakeredis.aioredis

from app.agent_runtime.notifications import (
    _format_kpi_alert,
    _mark_notified,
    notify_kpi_anomaly,
)


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def test_format_kpi_alert_shows_anomalies():
    """KPI alert lists anomaly metrics and severity."""
    anomalies = [
        {"severity": "high", "metric": "daily_agent_spend_usd", "value": "4.50"},
        {"severity": "medium", "metric": "open_findings", "value": "25"},
    ]
    msg = _format_kpi_alert(anomalies)
    assert "KPI Anomaly" in msg
    assert "daily_agent_spend_usd" in msg
    assert "HIGH" in msg


@pytest.mark.asyncio
async def test_mark_notified_first_call_returns_false(fake_redis):
    """First notification is not a duplicate."""
    import unittest.mock as mock

    with mock.patch("redis.asyncio.from_url", return_value=fake_redis):
        is_dup = await _mark_notified("redis://fake", "kpi_anomaly", "2026-03-01")
    assert is_dup is False


@pytest.mark.asyncio
async def test_mark_notified_second_call_returns_true(fake_redis):
    """Second call for same type+date returns True (duplicate)."""
    import unittest.mock as mock

    with mock.patch("redis.asyncio.from_url", return_value=fake_redis):
        await _mark_notified("redis://fake", "kpi_anomaly", "2026-03-01")
        is_dup = await _mark_notified("redis://fake", "kpi_anomaly", "2026-03-01")
    assert is_dup is True


@pytest.mark.asyncio
async def test_notify_kpi_anomaly_sends_alert(fake_redis):
    """KPI anomaly alert is sent on first call."""
    import unittest.mock as mock

    with (
        mock.patch("redis.asyncio.from_url", return_value=fake_redis),
        mock.patch("app.agent_runtime.notifications._send_telegram") as mock_send,
    ):
        await notify_kpi_anomaly(
            anomalies=[{"severity": "high", "metric": "daily_spend", "value": "5.00"}],
            redis_url="redis://fake",
        )
    mock_send.assert_called_once()
    assert "KPI Anomaly" in mock_send.call_args[0][0]


@pytest.mark.asyncio
async def test_notify_kpi_anomaly_deduped_second_call(fake_redis):
    """Second KPI anomaly call on same day is skipped."""
    import unittest.mock as mock

    with (
        mock.patch("redis.asyncio.from_url", return_value=fake_redis),
        mock.patch("app.agent_runtime.notifications._send_telegram") as mock_send,
    ):
        await notify_kpi_anomaly(
            anomalies=[{"severity": "high", "metric": "x", "value": "1"}],
            redis_url="redis://fake",
        )
        await notify_kpi_anomaly(
            anomalies=[{"severity": "high", "metric": "x", "value": "1"}],
            redis_url="redis://fake",
        )
    assert mock_send.call_count == 1
