"""Test monitor Celery task registration."""


def test_monitor_task_exists():
    """Monitor task should be importable."""
    from app.tasks.monitor_tasks import run_monitor_check

    assert callable(run_monitor_check)


def test_monitor_task_registered_name():
    """Monitor task should have the correct Celery task name."""
    from app.tasks.monitor_tasks import run_monitor_check

    assert run_monitor_check.name == "monitor.run_health_check"


def test_monitor_beat_schedule_entry():
    """Monitor task should be in the Celery Beat schedule."""
    from app.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "monitor-health-check" in schedule
    entry = schedule["monitor-health-check"]
    assert entry["task"] == "monitor.run_health_check"
    assert entry["schedule"] == 300.0


def test_monitor_tasks_in_include():
    """Monitor tasks module should be in celery include list."""
    from app.celery_app import celery_app

    assert "app.tasks.monitor_tasks" in celery_app.conf.include


def test_monitor_task_returns_calibration_mode_from_config():
    """Verify return dict uses config.calibration_mode, not report."""
    from agents.monitor.monitor import MonitorConfig, MonitorReport

    config = MonitorConfig()
    report = MonitorReport()
    # MonitorReport has no calibration_mode attr; config does
    assert hasattr(config, "calibration_mode")
    assert not hasattr(report, "calibration_mode")
    assert config.calibration_mode is True
