"""Test Celery metrics collection."""

from unittest.mock import MagicMock, patch

from app.utils.celery_metrics import (
    QUEUE_DEPTH_CRITICAL,
    QUEUE_DEPTH_WARNING,
    collect_celery_metrics,
)


def test_collect_metrics_redis_unavailable():
    """Graceful degradation when Redis is down."""
    with patch("redis.from_url", side_effect=Exception("Connection refused")):
        result = collect_celery_metrics()
        assert result["overall_alert"] == "unknown"
        assert "error" in result


def test_queue_depth_thresholds():
    """Thresholds are ordered correctly."""
    assert QUEUE_DEPTH_WARNING < QUEUE_DEPTH_CRITICAL
    assert QUEUE_DEPTH_WARNING > 0


def test_collect_metrics_ok_queues():
    """All queues under warning threshold return ok."""
    mock_redis_client = MagicMock()
    mock_redis_client.llen.return_value = 5
    mock_redis_client.lindex.return_value = None

    with patch("redis.from_url", return_value=mock_redis_client):
        result = collect_celery_metrics()

    assert result["overall_alert"] == "ok"
    assert result["total_depth"] == 20  # 4 queues * 5
    for q_stats in result["queues"].values():
        assert q_stats["alert"] == "ok"
        assert q_stats["depth"] == 5


def test_collect_metrics_warning_queue():
    """Queue at warning threshold triggers warning alert."""
    mock_redis_client = MagicMock()

    def llen_side_effect(queue_name: str) -> int:
        if queue_name == "celery":
            return QUEUE_DEPTH_WARNING + 1
        return 0

    mock_redis_client.llen.side_effect = llen_side_effect
    mock_redis_client.lindex.return_value = None

    with patch("redis.from_url", return_value=mock_redis_client):
        result = collect_celery_metrics()

    assert result["overall_alert"] == "warning"
    assert result["queues"]["celery"]["alert"] == "warning"


def test_collect_metrics_critical_queue():
    """Queue at critical threshold triggers critical alert."""
    mock_redis_client = MagicMock()

    def llen_side_effect(queue_name: str) -> int:
        if queue_name == "csv_processing":
            return QUEUE_DEPTH_CRITICAL + 10
        return 0

    mock_redis_client.llen.side_effect = llen_side_effect
    mock_redis_client.lindex.return_value = None

    with patch("redis.from_url", return_value=mock_redis_client):
        result = collect_celery_metrics()

    assert result["overall_alert"] == "critical"
    assert result["queues"]["csv_processing"]["alert"] == "critical"
