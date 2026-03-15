"""Tests for app/tasks/approval_tasks.py."""


def test_approval_checks_kill_switch_befo[RESEND_KEY_REDACTED]():
    """Kill switch check must happen before ExecutionEngine instantiation."""
    import inspect

    from app.tasks.approval_tasks import _execute_approval

    source = inspect.getsource(_execute_approval)
    # Kill switch check must come before engine instantiation
    kill_switch_pos = source.find("AUTONOMOUS_EXECUTION_ENABLED")
    engine_pos = source.find("ExecutionEngine(")
    assert kill_switch_pos > 0, "Kill switch check not found in _execute_approval"
    assert engine_pos > 0, "ExecutionEngine instantiation not found"
    assert kill_switch_pos < engine_pos, (
        "Kill switch check must happen before ExecutionEngine instantiation"
    )
