"""Test perf report task helpers."""


def test_perf_report_task_importable():
    """Verify the task module imports without errors."""
    from app.tasks import perf_report_tasks

    assert hasattr(perf_report_tasks, "daily_perf_report")


def test_collect_functions_handle_missing_extension():
    """Verify collectors degrade gracefully when pg_stat_statements is missing."""
    from app.tasks.perf_report_tasks import _collect_pg_stat_statements

    class FakeSession:
        def execute(self, *args, **kwargs):
            raise Exception("extension not installed")

    result = _collect_pg_stat_statements(FakeSession())
    assert result == []
