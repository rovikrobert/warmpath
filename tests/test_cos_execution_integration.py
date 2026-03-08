"""Test CoS integration with execution engine events."""

from agents.shared.event_stream import format_event
from agents.shared.message_formatter import MessageFormatter


def test_format_event_for_cos_brief():
    event = format_event(
        team="engineering",
        agent="deps_manager",
        finding_id="dep-1",
        tier="auto_do",
        action="auto_fixed",
        detail="Bumped requests 2.31.0 -> 2.32.0",
    )
    assert event["team"] == "engineering"
    assert event["action"] == "auto_fixed"
    assert event["detail"]
    assert event["timestamp"]


def test_execution_summary_with_events():
    fmt = MessageFormatter()
    events = [
        {"action": "auto_fixed", "detail": "Fixed lint issue", "pr_url": ""},
        {"action": "auto_fixed", "detail": "Bumped dep", "pr_url": ""},
        {
            "action": "pr_created",
            "detail": "New tests",
            "pr_url": "https://github.com/pr/1",
        },
        {"action": "escalated", "detail": "Auth bug found", "pr_url": ""},
    ]
    summary = fmt.execution_summary(events)
    assert "Auto-fixed: 2" in summary
    assert "PRs opened: 1" in summary
    assert "Escalated: 1" in summary


def test_execution_summary_empty():
    fmt = MessageFormatter()
    summary = fmt.execution_summary([])
    assert "No autonomous actions" in summary


def test_execution_engine_get_summary():
    from agents.shared.execution_engine import ExecutionEngine
    from agents.shared.report import Finding

    engine = ExecutionEngine(enabled=True)
    findings = [
        Finding(
            id="f1",
            severity="low",
            category="lint",
            title="Fix format",
            detail="",
            auto_fixable=True,
        ),
        Finding(
            id="f2",
            severity="medium",
            category="test",
            title="Add test",
            detail="",
            auto_fixable=False,
        ),
    ]
    engine.process_findings(findings, team="engineering", dry_run=True)
    summary = engine.get_summary_for_brief()
    assert isinstance(summary, str)
    assert len(summary) > 0
