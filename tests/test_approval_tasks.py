"""Tests for Telegram approval Celery task."""

from unittest.mock import patch

from agents.shared.decision_registry import PendingDecision


def _make_pending(number: int = 1, executed: bool = False) -> PendingDecision:
    return PendingDecision(
        number=number,
        finding_id="CVE-001",
        finding={
            "id": "CVE-001",
            "severity": "high",
            "category": "dependency-vulnerability",
            "title": "Test CVE",
            "detail": "d",
            "recommendation": "Bump foo>=2.0",
            "auto_fixable": True,
        },
        brief_date="2026-03-13",
        tier="auto_pr",
        action_plan="Bump foo",
        executed_at="2026-03-13T10:00:00Z" if executed else None,
        result_summary="Done" if executed else None,
    )


class TestExecuteTelegramApproval:
    @patch("app.tasks.approval_tasks._send_telegram_reply")
    @patch("app.tasks.approval_tasks.find_decision", return_value=None)
    def test_missing_decision_replies_not_found(self, mock_find, mock_reply):
        from app.tasks.approval_tasks import _execute_approval

        _execute_approval(123, 9, False)
        mock_reply.assert_called_once()
        assert "not found" in mock_reply.call_args[0][1].lower()

    @patch("app.tasks.approval_tasks._send_telegram_reply")
    @patch("app.tasks.approval_tasks.find_decision")
    def test_already_executed_replies_with_result(self, mock_find, mock_reply):
        from app.tasks.approval_tasks import _execute_approval

        mock_find.return_value = _make_pending(executed=True)
        _execute_approval(123, 1, False)
        mock_reply.assert_called_once()
        assert "already" in mock_reply.call_args[0][1].lower()

    @patch("app.tasks.approval_tasks._send_telegram_reply")
    @patch("app.tasks.approval_tasks.mark_executed")
    @patch("app.tasks.approval_tasks.find_decision")
    def test_rejection_marks_and_replies(self, mock_find, mock_mark, mock_reply):
        from app.tasks.approval_tasks import _execute_approval

        mock_find.return_value = _make_pending()
        _execute_approval(123, 1, True)
        mock_mark.assert_called_once_with(1, "Rejected by founder")
        assert "rejected" in mock_reply.call_args[0][1].lower()

    @patch("app.tasks.approval_tasks._send_telegram_reply")
    @patch("app.tasks.approval_tasks.mark_executed")
    @patch("app.tasks.approval_tasks._publish_event")
    @patch("app.tasks.approval_tasks.dispatch_action")
    @patch("app.tasks.approval_tasks.find_decision")
    @patch("app.tasks.approval_tasks._check_circuit_breaker", return_value=False)
    @patch("app.tasks.approval_tasks.filter_resolved_findings", side_effect=lambda x: x)
    @patch.dict("os.environ", {"AUTONOMOUS_EXECUTION_ENABLED": "true"})
    def test_successful_execution_dispatches_and_publishes_event(
        self,
        mock_filter,
        mock_cb,
        mock_find,
        mock_dispatch,
        mock_event,
        mock_mark,
        mock_reply,
    ):
        from app.tasks.approval_tasks import _execute_approval
        from agents.shared.action_handlers import ActionResult

        mock_find.return_value = _make_pending()
        mock_dispatch.return_value = ActionResult(
            success=True,
            summary="PR opened",
            pr_url="https://github.com/test/1",
            branch="tg-approve/CVE-001-20260313",
        )
        _execute_approval(123, 1, False)
        mock_dispatch.assert_called_once()
        mock_event.assert_called_once()
        mock_mark.assert_called_once()
        assert "PR opened" in mock_reply.call_args[0][1]

    @patch("app.tasks.approval_tasks._send_telegram_reply")
    @patch("app.tasks.approval_tasks.find_decision")
    @patch.dict("os.environ", {"AUTONOMOUS_EXECUTION_ENABLED": "false"})
    def test_disabled_execution_replies_logged_only(self, mock_find, mock_reply):
        from app.tasks.approval_tasks import _execute_approval

        mock_find.return_value = _make_pending()
        _execute_approval(123, 1, False)
        assert "disabled" in mock_reply.call_args[0][1].lower()

    @patch("app.tasks.approval_tasks._send_telegram_reply")
    @patch("app.tasks.approval_tasks.find_decision")
    @patch("app.tasks.approval_tasks._check_circuit_breaker", return_value=False)
    @patch("app.tasks.approval_tasks.filter_resolved_findings", side_effect=lambda x: x)
    @patch("app.tasks.approval_tasks.dispatch_action", side_effect=RuntimeError("boom"))
    @patch.dict("os.environ", {"AUTONOMOUS_EXECUTION_ENABLED": "true"})
    def test_handler_crash_always_replies_error(
        self, mock_dispatch, mock_filter, mock_cb, mock_find, mock_reply
    ):
        from app.tasks.approval_tasks import _execute_approval

        mock_find.return_value = _make_pending()
        _execute_approval(123, 1, False)
        assert "error" in mock_reply.call_args[0][1].lower()

    @patch("app.tasks.approval_tasks._send_telegram_reply")
    @patch("app.tasks.approval_tasks.mark_executed")
    @patch("app.tasks.approval_tasks.dispatch_action")
    @patch("app.tasks.approval_tasks.find_decision")
    @patch("app.tasks.approval_tasks._check_circuit_breaker", return_value=True)
    @patch("app.tasks.approval_tasks.filter_resolved_findings", side_effect=lambda x: x)
    @patch.dict("os.environ", {"AUTONOMOUS_EXECUTION_ENABLED": "true"})
    def test_circuit_breaker_downgrades_tier(
        self, mock_filter, mock_cb, mock_find, mock_dispatch, mock_mark, mock_reply
    ):
        """When circuit breaker is tripped, AUTO_DO is downgraded to AUTO_PR."""
        from app.tasks.approval_tasks import _execute_approval
        from agents.shared.action_handlers import ActionResult

        pending = _make_pending()
        pending.tier = "auto_do"
        mock_find.return_value = pending
        mock_dispatch.return_value = ActionResult(success=True, summary="PR opened")
        _execute_approval(123, 1, False)
        # dispatch_action should receive AUTO_PR (downgraded), not AUTO_DO
        call_args = mock_dispatch.call_args
        from agents.shared.execution_engine import ExecutionTier

        assert call_args[0][1] == ExecutionTier.AUTO_PR
