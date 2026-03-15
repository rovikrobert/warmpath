"""Tests for the agent auto-repair module."""

from __futu[RESEND_KEY_REDACTED] import annotations

from unittest.mock import MagicMock, patch

from agents.shared.repair import (
    RepairResult,
    _collect_recommendations,
    repair_auto_fixable,
)
from agents.shared.report import Finding


class TestCollectRecommendations:
    def test_extracts_high_severity_recommendations(self) -> None:
        findings = [
            Finding(
                id="f1",
                severity="high",
                category="perf",
                title="N+1 query in job_scan",
                detail="Use batch IN clause",
                recommendation="Batch with IN clause",
                auto_fixable=False,
            ),
            Finding(
                id="f2",
                severity="low",
                category="style",
                title="Minor style issue",
                detail="",
                recommendation="Fix indentation",
                auto_fixable=False,
            ),
        ]
        recs = _collect_recommendations(findings)
        assert len(recs) == 1
        assert "Batch with IN clause" in recs[0]

    def test_skips_auto_fixable_findings(self) -> None:
        findings = [
            Finding(
                id="f1",
                severity="high",
                category="lint",
                title="Ruff issue",
                detail="",
                recommendation="Run ruff",
                auto_fixable=True,
            ),
        ]
        recs = _collect_recommendations(findings)
        assert len(recs) == 0

    def test_auto_generates_recommendation_when_missing(self) -> None:
        findings = [
            Finding(
                id="f1",
                severity="critical",
                category="security",
                title="SQL injection risk",
                detail="Parameterize queries",
                file="app/api/search.py",
                auto_fixable=False,
            ),
        ]
        recs = _collect_recommendations(findings)
        assert len(recs) == 1
        assert "SQL injection risk" in recs[0]
        assert "app/api/search.py" in recs[0]

    def test_caps_at_five_recommendations(self) -> None:
        findings = [
            Finding(
                id=f"f{i}",
                severity="high",
                category="perf",
                title=f"Issue {i}",
                detail="",
                recommendation=f"Fix {i}",
                auto_fixable=False,
            )
            for i in range(10)
        ]
        recs = _collect_recommendations(findings)
        assert len(recs) == 5


class TestRepairAutoFixable:
    @patch("agents.shared.repair._already_attempted_today", return_value=False)
    @patch("agents.shared.repair._mark_attempted", return_value=True)
    @patch("agents.shared.repair._run")
    def test_skips_when_no_fixable_findings(
        self, mock_run: MagicMock, mock_mark: MagicMock, mock_already: MagicMock
    ) -> None:
        findings = [
            Finding(
                id="f1",
                severity="high",
                category="perf",
                title="Slow query",
                detail="",
                auto_fixable=False,
            ),
        ]
        result = repair_auto_fixable(findings)
        assert result.fixed_count == 0
        assert result.skipped_count == 1
        mock_run.assert_not_called()

    @patch("agents.shared.repair._already_attempted_today", return_value=True)
    def test_skips_when_already_attempted_today(self, mock_already: MagicMock) -> None:
        findings = [
            Finding(
                id="f1",
                severity="low",
                category="lint",
                title="Lint issue",
                detail="",
                auto_fixable=True,
            ),
        ]
        result = repair_auto_fixable(findings)
        assert result.fixed_count == 0
        assert result.skipped_count >= 1
        assert findings[0].repair_status == "skipped"

    @patch("agents.shared.repair._already_attempted_today", return_value=False)
    @patch("agents.shared.repair._mark_attempted", return_value=True)
    @patch("agents.shared.repair._run")
    def test_reverts_when_tests_fail(
        self, mock_run: MagicMock, mock_mark: MagicMock, mock_already: MagicMock
    ) -> None:
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=""),  # git stash push
            MagicMock(returncode=0),  # ruff check --fix
            MagicMock(returncode=0),  # ruff format
            MagicMock(returncode=0, stdout="2 files changed"),  # git diff --stat
            MagicMock(returncode=1),  # pytest fails
            MagicMock(returncode=0),  # git checkout . (revert)
            MagicMock(returncode=0, stdout=""),  # git stash pop
        ]
        findings = [
            Finding(
                id="f1",
                severity="low",
                category="lint",
                title="Lint",
                detail="",
                auto_fixable=True,
            ),
        ]
        result = repair_auto_fixable(findings)
        assert result.fixed_count == 0
        assert result.failed_count == 1
        assert findings[0].repair_status == "failed"
        assert "Tests failed" in result.errors[0]

    @patch("agents.shared.repair._already_attempted_today", return_value=False)
    @patch("agents.shared.repair._mark_attempted", return_value=True)
    @patch("agents.shared.repair._run")
    def test_creates_pr_when_tests_pass(
        self, mock_run: MagicMock, mock_mark: MagicMock, mock_already: MagicMock
    ) -> None:
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=""),  # git stash push
            MagicMock(returncode=0),  # ruff check --fix
            MagicMock(returncode=0),  # ruff format
            MagicMock(returncode=0, stdout="3 files changed"),  # git diff --stat
            MagicMock(returncode=0),  # pytest passes
            MagicMock(returncode=0),  # git checkout -b
            MagicMock(returncode=0),  # git add -u
            MagicMock(returncode=0),  # git commit
            MagicMock(returncode=0),  # git push
            MagicMock(
                returncode=0, stdout="https://github.com/org/repo/pull/99"
            ),  # gh pr
            MagicMock(returncode=0),  # git checkout -
            MagicMock(returncode=0, stdout=""),  # git stash pop
        ]
        findings = [
            Finding(
                id="f1",
                severity="low",
                category="lint",
                title="Lint",
                detail="",
                auto_fixable=True,
            ),
        ]
        result = repair_auto_fixable(findings)
        assert result.fixed_count == 1
        assert result.pr_url == "https://github.com/org/repo/pull/99"
        assert findings[0].repair_status == "fixed"
        assert "f1" in result.fixed_ids

    @patch("agents.shared.repair._already_attempted_today", return_value=False)
    @patch("agents.shared.repair._mark_attempted", return_value=False)
    @patch("agents.shared.repair._run")
    def test_skips_when_race_lost(
        self, mock_run: MagicMock, mock_mark: MagicMock, mock_already: MagicMock
    ) -> None:
        """When _mark_attempted returns False, another process won the race — skip."""
        findings = [
            Finding(
                id="f1",
                severity="low",
                category="lint",
                title="Lint issue",
                detail="",
                auto_fixable=True,
            ),
        ]
        result = repair_auto_fixable(findings)
        assert result.fixed_count == 0
        assert result.skipped_count >= 1
        assert findings[0].repair_status == "skipped"
        mock_run.assert_not_called()

    def test_repair_result_defaults(self) -> None:
        r = RepairResult()
        assert r.fixed_count == 0
        assert r.failed_count == 0
        assert r.skipped_count == 0
        assert r.pr_url is None
        assert r.errors == []
        assert r.fixed_ids == []
        assert r.recommendations == []

    @patch("agents.shared.repair._already_attempted_today", return_value=False)
    @patch("agents.shared.repair._mark_attempted", return_value=True)
    @patch("agents.shared.repair._run")
    def test_uses_git_add_u_not_git_add_a(
        self, mock_run: MagicMock, mock_mark: MagicMock, mock_already: MagicMock
    ) -> None:
        """Repair should use git add -u (tracked only), not git add -A (all files)."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=""),  # git stash push
            MagicMock(returncode=0),  # ruff check --fix
            MagicMock(returncode=0),  # ruff format
            MagicMock(returncode=0, stdout="2 files changed"),  # git diff --stat
            MagicMock(returncode=0),  # pytest
            MagicMock(returncode=0),  # git checkout -b
            MagicMock(returncode=0),  # git add -u
            MagicMock(returncode=0),  # git commit
            MagicMock(returncode=0),  # git push
            MagicMock(
                returncode=0, stdout="https://github.com/org/repo/pull/99"
            ),  # gh pr
            MagicMock(returncode=0),  # git checkout -
            MagicMock(returncode=0, stdout=""),  # git stash pop
        ]
        findings = [
            Finding(
                id="f1",
                severity="low",
                category="lint",
                title="Lint",
                detail="",
                auto_fixable=True,
            ),
        ]
        result = repair_auto_fixable(findings)
        # Check that git add uses -u flag
        add_calls = [
            c for c in mock_run.call_args_list if c[0][0][:2] == ["git", "add"]
        ]
        assert len(add_calls) == 1
        assert add_calls[0][0][0] == ["git", "add", "-u"]
        assert result.fixed_count == 1

    def test_ci_minutes_estimated_default_is_zero(self) -> None:
        """RepairResult should have ci_minutes_estimated default to 0.0."""
        result = RepairResult()
        assert result.ci_minutes_estimated == 0.0

    @patch("agents.shared.repair._already_attempted_today", return_value=False)
    @patch("agents.shared.repair._mark_attempted", return_value=True)
    @patch("agents.shared.repair._run")
    def test_ci_minutes_estimated_set_on_successful_repair(
        self, mock_run: MagicMock, mock_mark: MagicMock, mock_already: MagicMock
    ) -> None:
        """Successful repair should set ci_minutes_estimated to 3.0."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=""),  # git stash push
            MagicMock(returncode=0),  # ruff check --fix
            MagicMock(returncode=0),  # ruff format
            MagicMock(returncode=0, stdout="2 files changed"),  # git diff --stat
            MagicMock(returncode=0),  # pytest
            MagicMock(returncode=0),  # git checkout -b
            MagicMock(returncode=0),  # git add -u
            MagicMock(returncode=0),  # git commit
            MagicMock(returncode=0),  # git push
            MagicMock(
                returncode=0, stdout="https://github.com/org/repo/pull/99"
            ),  # gh pr
            MagicMock(returncode=0),  # git checkout -
            MagicMock(returncode=0, stdout=""),  # git stash pop
        ]
        findings = [
            Finding(
                id="f1",
                severity="low",
                category="lint",
                title="Lint",
                detail="",
                auto_fixable=True,
            ),
        ]
        result = repair_auto_fixable(findings)
        assert result.ci_minutes_estimated == 3.0
        assert result.fixed_count == 1


class TestRepairAuditEvents:
    @patch("agents.shared.repair._already_attempted_today", return_value=False)
    @patch("agents.shared.repair._mark_attempted", return_value=True)
    @patch("agents.shared.repair._run")
    @patch("agents.shared.repair._emit_repair_event")
    def test_emits_success_event(self, mock_emit, mock_run, mock_mark, mock_already):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=""),  # git stash push
            MagicMock(returncode=0),  # ruff check
            MagicMock(returncode=0),  # ruff format
            MagicMock(returncode=0, stdout="2 files changed"),  # git diff
            MagicMock(returncode=0),  # pytest
            MagicMock(returncode=0),  # git checkout -b
            MagicMock(returncode=0),  # git add -u
            MagicMock(returncode=0),  # git commit
            MagicMock(returncode=0),  # git push
            MagicMock(
                returncode=0, stdout="https://github.com/org/repo/pull/1"
            ),  # gh pr
            MagicMock(returncode=0),  # git checkout -
            MagicMock(returncode=0, stdout=""),  # git stash pop
        ]
        findings = [
            Finding(
                id="f1",
                severity="low",
                category="lint",
                title="Lint",
                detail="",
                auto_fixable=True,
            )
        ]
        repair_auto_fixable(findings)
        mock_emit.assert_called_once()
        assert mock_emit.call_args[1]["action"] == "repair_success"

    @patch("agents.shared.repair._already_attempted_today", return_value=False)
    @patch("agents.shared.repair._mark_attempted", return_value=True)
    @patch("agents.shared.repair._run")
    @patch("agents.shared.repair._emit_repair_event")
    def test_emits_failu[RESEND_KEY_REDACTED](
        self, mock_emit, mock_run, mock_mark, mock_already
    ):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=""),  # git stash push
            MagicMock(returncode=0),  # ruff check
            MagicMock(returncode=0),  # ruff format
            MagicMock(returncode=0, stdout="2 files changed"),  # git diff
            MagicMock(returncode=1),  # pytest FAILS
            MagicMock(returncode=0),  # git checkout . (revert)
            MagicMock(returncode=0, stdout=""),  # git stash pop
        ]
        findings = [
            Finding(
                id="f1",
                severity="low",
                category="lint",
                title="Lint",
                detail="",
                auto_fixable=True,
            )
        ]
        repair_auto_fixable(findings)
        mock_emit.assert_called_once()
        assert mock_emit.call_args[1]["action"] == "repair_failure"
        assert "Tests failed" in mock_emit.call_args[1]["detail"]


class TestMarkerAtomicity:
    def test_mark_attempted_uses_atomic_creation(self) -> None:
        """_mark_attempted should use atomic file creation to prevent races."""
        import inspect

        from agents.shared.repair import _mark_attempted

        source = inspect.getsource(_mark_attempted)
        assert "O_CREAT" in source or "O_EXCL" in source, (
            "_mark_attempted must use atomic file creation (O_CREAT|O_EXCL)"
        )

    def test_mark_attempted_returns_bool(self) -> None:
        """_mark_attempted should return True/False indicating if slot was claimed."""
        import inspect

        from agents.shared.repair import _mark_attempted

        source = inspect.getsource(_mark_attempted)
        assert "return True" in source and "return False" in source


class TestTelegramBriefWithRepairs:
    def test_format_includes_repair_line(self) -> None:
        from agents.chief_of_staff.telegram_bridge import TelegramBridge

        tg = TelegramBridge.__new__(TelegramBridge)
        msg = tg.format_daily_brief(
            date="Mar 04",
            team_summaries=[
                {"team": "engineering", "summary": "Clean scan", "health": "green"}
            ],
            decisions=[],
            cost="$0.12/day",
            repairs={"fixed_count": 3, "pr_url": "https://github.com/org/repo/pull/99"},
        )
        assert "Auto-actions:" in msg
        assert "[+] Fixed 3 issues" in msg
        assert "pull/99" in msg

    def test_format_includes_recommendations(self) -> None:
        from agents.chief_of_staff.telegram_bridge import TelegramBridge

        tg = TelegramBridge.__new__(TelegramBridge)
        msg = tg.format_daily_brief(
            date="Mar 04",
            team_summaries=[],
            decisions=[],
            cost="$0.12/day",
            recommendations=[
                "Fix N+1 query in job_scan",
                "Add missing index on user_id",
            ],
        )
        assert "[!] 2 recommendations:" in msg
        assert "1. Fix N+1 query in job_scan" in msg
        assert "2. Add missing index on user_id" in msg

    def test_format_without_repairs_unchanged(self) -> None:
        from agents.chief_of_staff.telegram_bridge import TelegramBridge

        tg = TelegramBridge.__new__(TelegramBridge)
        msg = tg.format_daily_brief(
            date="Mar 04",
            team_summaries=[
                {"team": "engineering", "summary": "OK", "health": "green"}
            ],
            decisions=[],
            cost="$0.05/day",
        )
        assert "[+]" not in msg
        assert "[!]" not in msg

    def test_format_separates_auto_actions_from_decisions(self) -> None:
        from agents.chief_of_staff.telegram_bridge import TelegramBridge

        tg = TelegramBridge.__new__(TelegramBridge)
        msg = tg.format_daily_brief(
            date="Mar 15",
            team_summaries=[
                {"team": "engineering", "summary": "2 fixes", "health": "green"}
            ],
            decisions=["Bump langchain-core?"],
            cost="$0.01/day",
            repairs={
                "fixed_count": 2,
                "pr_url": "https://github.com/org/repo/pull/100",
            },
        )
        assert "Auto-actions:" in msg
        assert "[+] Fixed 2 issues" in msg
