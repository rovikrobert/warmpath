"""Tests for KPI anomaly detection."""

import pytest
import fakeredis.aioredis

from app.agent_runtime.kpi_monitor import (
    _detect_anomaly,
    record_metric,
    get_history,
)


def test_detect_anomaly_returns_none_with_insufficient_data():
    """Need at least 5 data points for meaningful detection."""
    result = _detect_anomaly([1.0, 2.0, 3.0], 10.0, "test_metric")
    assert result is None


def test_detect_anomaly_returns_none_within_normal_range():
    """Values within 2σ are not anomalous."""
    values = [10.0, 11.0, 10.5, 9.5, 10.2]
    result = _detect_anomaly(values, 10.3, "test_metric")
    assert result is None


def test_detect_anomaly_detects_high_deviation():
    """Values >3σ from mean are flagged as high severity."""
    values = [10.0, 10.1, 10.0, 9.9, 10.0]  # very low variance
    result = _detect_anomaly(values, 15.0, "test_metric")
    assert result is not None
    assert result["severity"] == "high"
    assert result["metric"] == "test_metric"
    assert "increased" in result["description"]


def test_detect_anomaly_detects_medium_deviation():
    """Values >2σ but <3σ are flagged as medium severity."""
    # Mean=10, stdev~1 → 2σ=12, 3σ=13
    values = [9.0, 10.0, 11.0, 10.0, 10.0]
    result = _detect_anomaly(values, 12.5, "test_metric")
    assert result is not None
    assert result["severity"] in ("medium", "high")


def test_detect_anomaly_handles_zero_variance():
    """Constant series flags any deviation."""
    values = [5.0, 5.0, 5.0, 5.0, 5.0]
    result = _detect_anomaly(values, 6.0, "test_metric")
    assert result is not None
    assert result["severity"] == "medium"


def test_detect_anomaly_zero_variance_no_change():
    """Constant series with same value is not anomalous."""
    values = [5.0, 5.0, 5.0, 5.0, 5.0]
    result = _detect_anomaly(values, 5.0, "test_metric")
    assert result is None


def test_detect_anomaly_detects_decrease():
    """Significant decrease is also flagged."""
    values = [10.0, 10.1, 10.0, 9.9, 10.0]
    result = _detect_anomaly(values, 5.0, "test_metric")
    assert result is not None
    assert "decreased" in result["description"]


@pytest.mark.asyncio
async def test_record_and_get_history():
    """Metrics are recorded and retrievable."""
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    from unittest.mock import patch

    with patch("app.agent_runtime.kpi_monitor._get_redis", return_value=r):
        await record_metric("test_metric", 10.0)
        await record_metric("test_metric", 11.0)
        await record_metric("test_metric", 12.0)

        history = await get_history("test_metric")
        assert history == [10.0, 11.0, 12.0]
