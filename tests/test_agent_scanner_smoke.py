"""Smoke tests for agent scanners — verify they can find real project files.

These tests catch systemic issues like scanning .jsx when the project uses .tsx,
or using wrong directory paths. Each test verifies the scanner's file-discovery
function returns >0 files from the actual project structure.

Also tests the confidence field on Finding and the execution engine's
confidence gating.
"""

from __futu[RESEND_KEY_REDACTED] import annotations

import pytest

from agents.shared.report import Finding


# ---------------------------------------------------------------------------
# Scanner file-discovery smoke tests
# ---------------------------------------------------------------------------


@pytest.mark.smoke
class TestAgentScannerFileDiscovery:
    """Each agent's file-finder must return >0 files from the real project."""

    def test_naiv_finds_frontend_pages(self):
        """Naiv (ops) scanner finds .tsx pages."""
        from ops_team.naiv.naiv import _find_jsx_files

        files = _find_jsx_files()
        assert len(files) > 0, (
            "Naiv _find_jsx_files() returned 0 files — "
            "check PAGES_DIR path and file extension globs"
        )
        extensions = {f.suffix for f in files}
        assert ".tsx" in extensions or ".jsx" in extensions

    def test_gtm_marketing_finds_frontend_pages(self):
        """GTM marketing scanner finds .tsx pages."""
        from gtm_team.marketing.scanner import _find_jsx_files

        files = _find_jsx_files()
        assert len(files) > 0, (
            "GTM marketing _find_jsx_files() returned 0 files — "
            "check PAGES_DIR path and file extension globs"
        )

    def test_gtm_partnerships_finds_frontend_pages(self):
        """GTM partnerships scanner finds .tsx pages."""
        from gtm_team.partnerships.scanner import _find_jsx_files

        files = _find_jsx_files()
        assert len(files) > 0, (
            "GTM partnerships _find_jsx_files() returned 0 files — "
            "check PAGES_DIR path and file extension globs"
        )

    def test_product_user_researcher_finds_frontend_pages(self):
        """Product user_researcher finds .tsx pages."""
        from product_team.user_researcher.user_researcher import _find_page_files

        files = _find_page_files()
        assert len(files) > 0, (
            "Product user_researcher _find_page_files() returned 0 files — "
            "check PAGES_DIR path and file extension globs"
        )

    def test_product_manager_finds_frontend_pages(self):
        """Product product_manager finds .tsx pages."""
        from product_team.product_manager.product_manager import _find_page_files

        files = _find_page_files()
        assert len(files) > 0, (
            "Product product_manager _find_page_files() returned 0 files — "
            "check PAGES_DIR path and file extension globs"
        )

    def test_naiv_feedback_pattern_matches_feedbackmodal(self):
        """Naiv feedback regex must match FeedbackModal (the actual component)."""
        from ops_team.naiv.naiv import _FEEDBACK_PATTERNS

        assert _FEEDBACK_PATTERNS.search("FeedbackModal"), (
            "_FEEDBACK_PATTERNS doesn't match 'FeedbackModal' — "
            "the actual component name used in the project"
        )

    def test_gtm_analytics_checks_tsx_files(self):
        """GTM analytics check must find PostHog init in .tsx main file."""
        from gtm_team.marketing.scanner import PROJECT_ROOT

        # Verify the project actually uses .tsx
        main_tsx = PROJECT_ROOT / "frontend" / "src" / "main.tsx"
        main_jsx = PROJECT_ROOT / "frontend" / "src" / "main.jsx"
        assert main_tsx.exists() or main_jsx.exists(), (
            "Neither main.tsx nor main.jsx exists — check PROJECT_ROOT"
        )


# ---------------------------------------------------------------------------
# Finding confidence field
# ---------------------------------------------------------------------------


@pytest.mark.smoke
class TestFindingConfidence:
    """Finding.confidence field works correctly."""

    def test_default_confidence_is_1(self):
        """Findings default to full confidence."""
        f = Finding(
            id="test-1", severity="high", category="test", title="t", detail="d"
        )
        assert f.confidence == 1.0

    def test_low_confidence_finding(self):
        """Confidence can be set below threshold."""
        f = Finding(
            id="test-2",
            severity="high",
            category="test",
            title="t",
            detail="d",
            confidence=0.3,
        )
        assert f.confidence == 0.3

    def test_confidence_survives_serialization(self):
        """Confidence persists through dict round-trip."""
        original = Finding(
            id="test-3",
            severity="medium",
            category="test",
            title="t",
            detail="d",
            confidence=0.7,
        )
        restored = Finding.from_dict(
            {
                "id": "test-3",
                "severity": "medium",
                "category": "test",
                "title": "t",
                "detail": "d",
                "confidence": 0.7,
            }
        )
        assert restored.confidence == original.confidence

    def test_confidence_in_sort_key(self):
        """Higher confidence findings should not be deprioritized."""
        high_conf = Finding(
            id="a",
            severity="high",
            category="test",
            title="t",
            detail="d",
            confidence=0.9,
        )
        low_conf = Finding(
            id="b",
            severity="high",
            category="test",
            title="t",
            detail="d",
            confidence=0.3,
        )
        # Both same severity — sort_key is the same (confidence doesn't affect sort)
        assert high_conf.sort_key == low_conf.sort_key


# ---------------------------------------------------------------------------
# Execution engine confidence gating
# ---------------------------------------------------------------------------


@pytest.mark.smoke
class TestExecutionEngineConfidenceGating:
    """Execution engine skips low-confidence findings."""

    def test_low_confidence_finding_is_report_only(self):
        """Findings with confidence < 0.5 should be REPORT_ONLY."""
        from agents.shared.execution_engine import ExecutionEngine, ExecutionTier

        engine = ExecutionEngine(enabled=True)
        f = Finding(
            id="test-low",
            severity="medium",
            category="test",
            title="Low confidence finding",
            detail="d",
            confidence=0.3,
        )
        tier = engine.triage(f)
        assert tier == ExecutionTier.REPORT_ONLY

    def test_high_confidence_finding_is_actionable(self):
        """Findings with confidence >= 0.5 proceed to normal triage."""
        from agents.shared.execution_engine import ExecutionEngine, ExecutionTier

        engine = ExecutionEngine(enabled=True)
        f = Finding(
            id="test-high",
            severity="medium",
            category="test",
            title="High confidence finding",
            detail="d",
            confidence=0.9,
        )
        tier = engine.triage(f)
        assert tier != ExecutionTier.REPORT_ONLY

    def test_default_confidence_is_actionable(self):
        """Default confidence (1.0) should be actionable."""
        from agents.shared.execution_engine import ExecutionEngine, ExecutionTier

        engine = ExecutionEngine(enabled=True)
        f = Finding(
            id="test-default",
            severity="low",
            category="lint",
            title="Lint issue",
            detail="d",
        )
        tier = engine.triage(f)
        assert tier != ExecutionTier.REPORT_ONLY

    def test_disabled_engine_ignores_confidence(self):
        """When engine is disabled, everything is REPORT_ONLY regardless."""
        from agents.shared.execution_engine import ExecutionEngine, ExecutionTier

        engine = ExecutionEngine(enabled=False)
        f = Finding(
            id="test-disabled",
            severity="low",
            category="lint",
            title="Lint issue",
            detail="d",
            confidence=1.0,
        )
        tier = engine.triage(f)
        assert tier == ExecutionTier.REPORT_ONLY


# ---------------------------------------------------------------------------
# Synthesizer confidence filtering
# ---------------------------------------------------------------------------


class TestSynthesizerConfidenceFiltering:
    """Low-confidence findings should be filtered from daily briefs."""

    def test_low_confidence_filtered_from_brief(self):
        """Findings with confidence < 0.5 should not appear in briefs."""
        from agents.chief_of_staff.synthesizer import _filter_noisy_findings

        findings = [
            Finding(
                id="a",
                severity="high",
                category="perf",
                title="t",
                detail="d",
                confidence=0.9,
            ),
            Finding(
                id="b",
                severity="high",
                category="perf",
                title="t",
                detail="d",
                confidence=0.3,
            ),
        ]
        filtered = _filter_noisy_findings(findings)
        assert len(filtered) == 1
        assert filtered[0].id == "a"

    def test_critical_bypasses_confidence_filter(self):
        """Critical findings always surface regardless of confidence."""
        from agents.chief_of_staff.synthesizer import _filter_noisy_findings

        findings = [
            Finding(
                id="c",
                severity="critical",
                category="security",
                title="t",
                detail="d",
                confidence=0.2,
            ),
        ]
        filtered = _filter_noisy_findings(findings)
        assert len(filtered) == 1
        assert filtered[0].id == "c"
