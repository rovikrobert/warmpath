from app.agent_runtime.events.railway import parse_error_logs, should_alert


def test_parse_error_logs_counts_errors():
    logs = [
        "INFO Starting",
        "ERROR Internal server error",
        "ERROR DB failed",
        "WARNING Slow",
        "ERROR Timeout",
    ]
    result = parse_error_logs(logs)
    assert result["error_count"] == 3
    assert len(result["sample_errors"]) == 3


def test_should_alert_when_error_threshold_exceeded():
    assert should_alert(error_count=10, threshold=5) is True


def test_should_not_alert_below_threshold():
    assert should_alert(error_count=2, threshold=5) is False
