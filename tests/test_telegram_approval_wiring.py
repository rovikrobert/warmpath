"""Tests for Telegram webhook approval wiring."""

import tempfile
from pathlib import Path
from unittest.mock import patch
from unittest.mock import patch as mock_patch

from agents.shared.message_formatter import MessageFormatter


class TestParseReplyApproveItem:
    def test_numeric_reply_returns_approve_item(self):
        result = MessageFormatter.parse_reply("1")
        assert result["command"] == "approve_item"
        assert result["item"] == 1

    def test_numbered_yes_returns_approve_item_with_value(self):
        result = MessageFormatter.parse_reply("2=yes")
        assert result["command"] == "approve_item"
        assert result["item"] == 2
        assert result["value"] == "yes"

    def test_numbered_no_returns_approve_item_with_no(self):
        result = MessageFormatter.parse_reply("1=no")
        assert result["command"] == "approve_item"
        assert result["item"] == 1
        assert result["value"] == "no"


class TestHandleCommandApproveItem:
    @patch("app.api.telegram._send_telegram_reply")
    @patch("app.tasks.approval_tasks.execute_telegram_approval.delay")
    def test_approve_item_sends_ack_and_enqueues_task(self, mock_delay, mock_reply):
        from app.api.telegram import _handle_command

        _handle_command(
            "approve_item", {"item": 1, "value": "yes"}, 123, is_founder=True
        )
        mock_reply.assert_called_once()
        assert "executing" in mock_reply.call_args[0][1].lower()
        mock_delay.assert_called_once_with(123, 1, False)

    @patch("app.api.telegram._send_telegram_reply")
    @patch("app.tasks.approval_tasks.execute_telegram_approval.delay")
    def test_approve_item_no_rejects(self, mock_delay, mock_reply):
        from app.api.telegram import _handle_command

        _handle_command(
            "approve_item", {"item": 1, "value": "no"}, 123, is_founder=True
        )
        mock_delay.assert_called_once_with(123, 1, True)

    @patch("app.api.telegram._send_telegram_reply")
    @patch("app.tasks.approval_tasks.execute_telegram_approval.delay")
    def test_approve_item_non_founder_rejected(self, mock_delay, mock_reply):
        from app.api.telegram import _handle_command

        _handle_command("approve_item", {"item": 1}, 456, is_founder=False)
        mock_delay.assert_not_called()
        assert "founder" in mock_reply.call_args[0][1].lower()


class TestEndToEndApprovalFlow:
    def test_synthesize_then_find_preserves_original_finding(self):
        """Full flow: synthesize_daily → save decisions → find → reconstruct."""
        from agents.chief_of_staff.synthesizer import synthesize_daily
        from agents.shared.decision_registry import (
            find_decision,
            load_pending_decisions,
        )
        from agents.shared.report import AgentReport, Finding

        reports = [
            AgentReport(
                agent="security_scanner",
                scan_duration_seconds=5.0,
                findings=[
                    Finding(
                        id="E2E-CVE-001",
                        severity="critical",
                        category="dependency-vulnerability",
                        title="Critical dep vuln",
                        detail="Needs bump",
                        recommendation="Bump bar>=3.0",
                        auto_fixable=True,
                        file="requirements.txt",
                    ),
                ],
            ),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "pending_decisions.json"
            reg_patch = mock_patch(
                "agents.shared.learning._load_resolved_registry",
                return_value={},
            )
            path_patch = mock_patch(
                "agents.shared.decision_registry.DECISIONS_PATH", tmp_path
            )

            with reg_patch, path_patch:
                synthesize_daily(reports)

                decisions = load_pending_decisions()
                assert len(decisions) == 1
                assert decisions[0].finding_id == "E2E-CVE-001"

                # Original Finding fields preserved
                assert decisions[0].finding["auto_fixable"] is True
                assert decisions[0].finding["file"] == "requirements.txt"

                # Reconstruct finding
                found = find_decision(1)
                assert found is not None
                f = Finding.from_dict(found.finding)
                assert f.auto_fixable is True
                assert f.category == "dependency-vulnerability"
