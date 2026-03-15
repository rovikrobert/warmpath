"""Tests for Telegram approval action handlers."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from agents.shared.action_handlers import (
    ActionResult,
    dispatch_action,
    handle_dependency_bump,
    handle_lint_fix,
    handle_resolve_false_positive,
)
from agents.shared.execution_engine import ExecutionTier
from agents.shared.report import Finding


def _make_finding(**overrides) -> Finding:
    defaults = dict(
        id="TEST-001",
        severity="high",
        category="security",
        title="Test finding",
        detail="Test detail",
        file="app/main.py",
        recommendation="Fix it",
        auto_fixable=True,
    )
    defaults.update(overrides)
    return Finding(**defaults)


class TestActionResult:
    def test_failed_result(self):
        r = ActionResult(success=False, summary="Tests failed", reverted=True)
        assert not r.success
        assert r.reverted

    def test_success_with_pr(self):
        r = ActionResult(
            success=True,
            summary="PR opened",
            pr_url="https://github.com/test/1",
            branch="tg-approve/CVE-001-20260313",
        )
        assert r.success
        assert r.pr_url


class TestDispatchAction:
    def test_dispatches_dep_bump_for_vulnerability(self):
        """dependency-vulnerability category routes to handle_dependency_bump."""
        f = _make_finding(category="dependency-vulnerability")
        with patch("agents.shared.action_handlers.handle_dependency_bump") as mock:
            mock.return_value = ActionResult(success=True, summary="bumped")
            dispatch_action(f, ExecutionTier.AUTO_PR)
        mock.assert_called_once_with(f, ExecutionTier.AUTO_PR)

    def test_dispatches_lint_fix_for_lint(self):
        """lint category routes to handle_lint_fix."""
        f = _make_finding(category="lint")
        with patch("agents.shared.action_handlers.handle_lint_fix") as mock:
            mock.return_value = ActionResult(success=True, summary="fixed")
            dispatch_action(f, ExecutionTier.AUTO_DO)
        mock.assert_called_once()

    def test_protected_path_returns_failure(self):
        """Finding targeting protected path returns failure without execution."""
        f = _make_finding(file="app/api/auth.py")
        result = dispatch_action(f, ExecutionTier.AUTO_DO)
        assert not result.success
        assert "protected" in result.summary.lower()

    def test_escalate_tier_returns_logged_only(self):
        """ESCALATE tier logs the approval but doesn't execute."""
        f = _make_finding()
        result = dispatch_action(f, ExecutionTier.ESCALATE)
        assert not result.success
        assert "escalat" in result.summary.lower()


_FAKE_REQUIREMENTS = "langchain-core>=1.2.16\nfastapi>=0.135.0\n"


class TestHandleDependencyBump:
    @patch("agents.shared.action_handlers._run_subprocess")
    def test_success_creates_branch_and_pr(self, mock_run):
        """Successful dep bump: branch + commit + push + PR."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="https://github.com/test/pulls/1"
        )
        f = _make_finding(
            id="CVE-2026-001",
            category="dependency-vulnerability",
            title="SSRF in langchain-core",
            detail="Fix in v1.2.11",
            recommendation="Bump langchain-core>=1.2.11",
            file="requirements.txt",
        )
        with (
            patch.object(Path, "read_text", return_value=_FAKE_REQUIREMENTS),
            patch.object(Path, "write_text") as mock_write,
            patch.object(Path, "exists", return_value=True),
        ):
            result = handle_dependency_bump(f, ExecutionTier.AUTO_PR)
        assert result.success
        # Verify the write used the bumped version, not the original
        written = mock_write.call_args[0][0]
        assert "langchain-core>=1.2.11" in written
        calls = [str(c) for c in mock_run.call_args_list]
        assert any("checkout" in c and "-b" in c for c in calls)
        assert any("pr" in c and "create" in c for c in calls)

    @patch("agents.shared.action_handlers._run_subprocess")
    def test_test_failure_reverts_with_hard_reset(self, mock_run):
        """If pytest fails, handler does git reset --hard and returns failure."""

        def side_effect(cmd, **kwargs):
            m = MagicMock(returncode=0, stdout="")
            if cmd[0] == "pytest":
                m.returncode = 1
                m.stdout = "FAILED"
            if cmd[:2] == ["git", "rev-parse"] and len(cmd) > 2:
                if cmd[2] == "HEAD":
                    m.stdout = "abc123def"
                elif cmd[2] == "--abbrev-ref":
                    m.stdout = "master"
            if cmd[:2] == ["git", "diff"]:
                m.stdout = " requirements.txt | 1 +"
            return m

        mock_run.side_effect = side_effect
        f = _make_finding(
            category="dependency-vulnerability",
            recommendation="Bump foo>=2.0",
        )
        with (
            patch.object(Path, "read_text", return_value=_FAKE_REQUIREMENTS),
            patch.object(Path, "write_text"),
            patch.object(Path, "exists", return_value=True),
        ):
            result = handle_dependency_bump(f, ExecutionTier.AUTO_PR)
        assert not result.success
        assert result.reverted
        calls = [str(c) for c in mock_run.call_args_list]
        assert any("reset" in c and "--hard" in c for c in calls)


class TestHandleLintFix:
    @patch("agents.shared.action_handlers._run_subprocess")
    def test_delegates_to_ruff(self, mock_run):
        """Lint handler runs ruff check --fix and ruff format."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        f = _make_finding(category="lint", title="Unused import")
        handle_lint_fix(f, ExecutionTier.AUTO_DO)
        calls = [str(c) for c in mock_run.call_args_list]
        assert any("ruff" in c for c in calls)


class TestHandleResolveFalsePositive:
    @patch("agents.shared.action_handlers._run_subprocess")
    @patch("agents.shared.action_handlers._resolve_in_registry")
    def test_calls_existing_resolve_function(self, mock_resolve, mock_run):
        """FP handler uses learning.resolve_issue, not custom file I/O."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        f = _make_finding(id="FP-001", title="Known false positive")
        handle_resolve_false_positive(f, ExecutionTier.AUTO_PR)
        mock_resolve.assert_called_once_with(f)
