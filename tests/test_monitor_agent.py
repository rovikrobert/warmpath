"""Test the monitor agent (continuous production health)."""

from unittest.mock import patch, MagicMock
from agents.monitor.monitor import (
    check_app_health,
    check_worker_health,
    MonitorConfig,
    HealthStatus,
)


def test_health_check_ok():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok"}
    mock_resp.elapsed.total_seconds.return_value = 0.1

    with patch("agents.monitor.monitor.httpx.get", return_value=mock_resp):
        status = check_app_health("http://localhost:8000/health")
    assert status.healthy is True
    assert status.response_time_ms < 1000


def test_health_check_fail():
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.elapsed.total_seconds.return_value = 5.0

    with patch("agents.monitor.monitor.httpx.get", return_value=mock_resp):
        status = check_app_health("http://localhost:8000/health")
    assert status.healthy is False


def test_health_check_connection_error():
    with patch(
        "agents.monitor.monitor.httpx.get", side_effect=ConnectionError("refused")
    ):
        status = check_app_health("http://localhost:8000/health")
    assert status.healthy is False
    assert "Connection failed" in status.detail


def test_worker_health_ok():
    mock_redis = MagicMock()
    mock_redis.llen.return_value = 5
    status = check_worker_health(mock_redis, threshold=100)
    assert status.healthy is True


def test_worker_health_backed_up():
    mock_redis = MagicMock()
    mock_redis.llen.return_value = 150
    status = check_worker_health(mock_redis, threshold=100)
    assert status.healthy is False


def test_monitor_config_defaults():
    config = MonitorConfig()
    assert config.health_check_interval_seconds == 300
    assert config.consecutive_failures_to_alert == 2
    assert config.error_rate_threshold == 0.05
    assert config.calibration_mode is True


def test_monitor_report_tracks_unhealthy():
    from agents.monitor.monitor import MonitorReport

    report = MonitorReport()
    report.add_check(HealthStatus(healthy=True, source="app"))
    assert report.all_healthy is True
    report.add_check(HealthStatus(healthy=False, source="worker", detail="queue full"))
    assert report.all_healthy is False
