"""Tests for automated agent briefs (Railway cron) and product lead beta feedback.

Tests cover:
  - RunMode includes full-scan-weekly and full-scan-monthly
  - Weekly/monthly scan orders include all 6 teams
  - _COMMANDS has all required entries
  - _strip_pii removes emails, phones, LinkedIn URLs
  - _check_beta_feedback returns empty when NOTION_API_KEY not set
  - _check_beta_feedback produces findings from mocked Notion response
  - FEEDBACK_SEVERITY_MAP covers all expected values
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Feature 1: Agent endpoint RunMode and scan orders
# ---------------------------------------------------------------------------


class TestAgentRunModes:
    """Validate RunMode, _COMMANDS, and scan order lists."""

    def test_full_scan_weekly_is_valid_mode(self):
        from typing import get_args

        from app.api.agents import RunMode

        modes = get_args(RunMode)
        assert "full-scan-weekly" in modes

    def test_full_scan_monthly_is_valid_mode(self):
        from typing import get_args

        from app.api.agents import RunMode

        modes = get_args(RunMode)
        assert "full-scan-monthly" in modes

    def test_all_original_modes_preserved(self):
        from typing import get_args

        from app.api.agents import RunMode

        modes = get_args(RunMode)
        for m in [
            "cos-daily",
            "cos-weekly",
            "engineering",
            "data",
            "product",
            "ops",
            "finance",
            "gtm",
            "full-scan",
        ]:
            assert m in modes, f"{m} missing from RunMode"

    def test_commands_has_weekly_monthly_entries(self):
        from app.api.agents import _COMMANDS

        expected = [
            "engineering-skip-tests",
            "engineering-weekly",
            "data-weekly",
            "data-monthly",
            "product-weekly",
            "product-monthly",
            "ops-weekly",
            "ops-monthly",
            "finance-weekly",
            "finance-monthly",
            "gtm-weekly",
            "gtm-monthly",
        ]
        for key in expected:
            assert key in _COMMANDS, f"{key} missing from _COMMANDS"

    def test_weekly_scan_order_has_all_teams(self):
        from app.api.agents import _WEEKLY_SCAN_ORDER

        teams = {"engineering", "data", "product", "ops", "finance", "gtm"}
        # Check team scans present (via skip-tests or plain)
        scan_modes = {m.split("-")[0] for m in _WEEKLY_SCAN_ORDER}
        for team in teams:
            assert team in scan_modes, f"{team} missing from _WEEKLY_SCAN_ORDER"
        # Check weekly briefs present
        for team in teams - {"engineering"}:
            assert f"{team}-weekly" in _WEEKLY_SCAN_ORDER
        assert "engineering-weekly" in _WEEKLY_SCAN_ORDER
        assert "cos-weekly" in _WEEKLY_SCAN_ORDER

    def test_monthly_scan_order_has_all_teams(self):
        from app.api.agents import _MONTHLY_SCAN_ORDER

        teams = {"data", "product", "ops", "finance", "gtm"}
        # Check monthly briefs present
        for team in teams:
            assert f"{team}-monthly" in _MONTHLY_SCAN_ORDER
        assert "cos-weekly" in _MONTHLY_SCAN_ORDER

    def test_weekly_scan_order_ends_with_cos(self):
        from app.api.agents import _WEEKLY_SCAN_ORDER

        assert _WEEKLY_SCAN_ORDER[-1] == "cos-weekly"

    def test_monthly_scan_order_ends_with_cos(self):
        from app.api.agents import _MONTHLY_SCAN_ORDER

        assert _MONTHLY_SCAN_ORDER[-1] == "cos-weekly"

    def test_full_scan_order_uses_skip_tests(self):
        from app.api.agents import _FULL_SCAN_ORDER

        assert "engineering-skip-tests" in _FULL_SCAN_ORDER
        assert "engineering" not in _FULL_SCAN_ORDER

    def test_all_scan_order_modes_exist_in_commands(self):
        from app.api.agents import (
            _COMMANDS,
            _FULL_SCAN_ORDER,
            _MONTHLY_SCAN_ORDER,
            _WEEKLY_SCAN_ORDER,
        )

        for order_name, order in [
            ("full", _FULL_SCAN_ORDER),
            ("weekly", _WEEKLY_SCAN_ORDER),
            ("monthly", _MONTHLY_SCAN_ORDER),
        ]:
            for mode in order:
                assert mode in _COMMANDS, (
                    f"{mode} in {order_name} scan order but not in _COMMANDS"
                )


# ---------------------------------------------------------------------------
# Feature 2: PII stripping
# ---------------------------------------------------------------------------


class TestStripPii:
    """_strip_pii must remove emails, phones, and LinkedIn URLs."""

    def _strip(self, text: str) -> str:
        from product_team.product_lead.product_lead import _strip_pii

        return _strip_pii(text)

    def test_strips_email(self):
        assert "[email]" in self._strip("Contact john@example.com for details")
        assert "john@example.com" not in self._strip(
            "Contact john@example.com for details"
        )

    def test_strips_phone(self):
        result = self._strip("Call +65 9123 4567 now")
        assert "[phone]" in result
        assert "9123 4567" not in result

    def test_strips_linkedin_url(self):
        result = self._strip("See https://www.linkedin.com/in/johndoe for profile")
        assert "[linkedin]" in result
        assert "linkedin.com/in/johndoe" not in result

    def test_strips_multiple_pii(self):
        text = (
            "Email: a@b.com, phone: +1 555-123-4567, profile: https://linkedin.com/in/x"
        )
        result = self._strip(text)
        assert "[email]" in result
        assert "[phone]" in result
        assert "[linkedin]" in result

    def test_preserves_clean_text(self):
        text = "UX score is 85 across 12 pages with 3 critical findings"
        assert self._strip(text) == text


# ---------------------------------------------------------------------------
# Feature 2: Feedback severity mapping
# ---------------------------------------------------------------------------


class TestFeedbackSeverityMap:
    """FEEDBACK_SEVERITY_MAP must cover all Notion severity options."""

    def test_blocker_maps_to_critical(self):
        from product_team.shared.config import FEEDBACK_SEVERITY_MAP

        assert FEEDBACK_SEVERITY_MAP["Blocker"] == "critical"

    def test_annoying_maps_to_high(self):
        from product_team.shared.config import FEEDBACK_SEVERITY_MAP

        assert FEEDBACK_SEVERITY_MAP["Annoying"] == "high"

    def test_minor_maps_to_medium(self):
        from product_team.shared.config import FEEDBACK_SEVERITY_MAP

        assert FEEDBACK_SEVERITY_MAP["Minor"] == "medium"

    def test_just_a_thought_maps_to_low(self):
        from product_team.shared.config import FEEDBACK_SEVERITY_MAP

        assert FEEDBACK_SEVERITY_MAP["Just a thought"] == "low"

    def test_all_four_severities_present(self):
        from product_team.shared.config import FEEDBACK_SEVERITY_MAP

        assert len(FEEDBACK_SEVERITY_MAP) == 4


# ---------------------------------------------------------------------------
# Feature 2: Beta feedback from Notion
# ---------------------------------------------------------------------------


class TestCheckBetaFeedback:
    """_check_beta_feedback must gracefully degrade and process Notion items."""

    def test_returns_empty_without_notion_key(self):
        from product_team.product_lead.product_lead import _check_beta_feedback

        with patch.dict("os.environ", {}, clear=False):
            # Ensure NOTION_API_KEY is NOT set
            import os

            old = os.environ.pop("NOTION_API_KEY", None)
            try:
                findings, insights, xtr = _check_beta_feedback()
                assert findings == []
                assert insights == []
                assert xtr == []
            finally:
                if old is not None:
                    os.environ["NOTION_API_KEY"] = old

    def test_produces_findings_from_notion_pages(self):
        from product_team.product_lead.product_lead import _check_beta_feedback

        mock_response = {
            "results": [
                {
                    "id": "abc12345-1234-1234-1234-123456789abc",
                    "properties": {
                        "Name": {"title": [{"text": {"content": "Search is slow"}}]},
                        "Severity": {"select": {"name": "Annoying"}},
                        "Category": {"select": {"name": "Bug"}},
                        "Description": {
                            "rich_text": [
                                {"text": {"content": "Search takes 10s to load"}}
                            ]
                        },
                        "Page/Feature": {"select": {"name": "Search"}},
                        "Status": {"select": {"name": "New"}},
                    },
                },
                {
                    "id": "def67890-5678-5678-5678-567890123def",
                    "properties": {
                        "Name": {
                            "title": [{"text": {"content": "Love the coaching!"}}]
                        },
                        "Severity": {"select": {"name": "Just a thought"}},
                        "Category": {"select": {"name": "Praise"}},
                        "Description": {
                            "rich_text": [
                                {"text": {"content": "The AI coach is great"}}
                            ]
                        },
                        "Page/Feature": {"select": {"name": "Coach"}},
                        "Status": {"select": {"name": "New"}},
                    },
                },
            ]
        }

        mock_client = MagicMock()
        mock_client.enabled = True
        mock_client.query_database.return_value = mock_response
        mock_client.update_page.return_value = {}

        with (
            patch.dict("os.environ", {"NOTION_API_KEY": "test-key"}),
            patch(
                "agents.shared.notion_client.NotionClient",
                return_value=mock_client,
            ),
        ):
            findings, insights, xtr = _check_beta_feedback()

        assert len(findings) == 2
        assert findings[0].severity == "high"  # Annoying → high
        assert findings[0].category == "beta_feedback"
        assert "Search is slow" in findings[0].title
        assert findings[1].severity == "low"  # Just a thought → low

        # Summary insight produced
        assert len(insights) == 1
        assert "2 new items" in insights[0].title

        # Both pages marked as Acknowledged
        assert mock_client.update_page.call_count == 2

    def test_routes_partnership_to_gtm(self):
        from product_team.product_lead.product_lead import _check_beta_feedback

        mock_response = {
            "results": [
                {
                    "id": "part1234-1234-1234-1234-123456789abc",
                    "properties": {
                        "Name": {
                            "title": [
                                {"text": {"content": "Partnership with TechCorp"}}
                            ]
                        },
                        "Severity": {"select": {"name": "Minor"}},
                        "Category": {"select": {"name": "Partnership Offer"}},
                        "Description": {"rich_text": []},
                        "Page/Feature": {"select": {"name": "Other"}},
                        "Status": {"select": {"name": "New"}},
                    },
                }
            ]
        }

        mock_client = MagicMock()
        mock_client.enabled = True
        mock_client.query_database.return_value = mock_response
        mock_client.update_page.return_value = {}

        with (
            patch.dict("os.environ", {"NOTION_API_KEY": "test-key"}),
            patch(
                "agents.shared.notion_client.NotionClient",
                return_value=mock_client,
            ),
        ):
            findings, insights, xtr = _check_beta_feedback()

        assert len(xtr) == 1
        assert xtr[0]["team"] == "gtm"

    def test_strips_pii_from_feedback_title(self):
        from product_team.product_lead.product_lead import _check_beta_feedback

        mock_response = {
            "results": [
                {
                    "id": "pii12345-1234-1234-1234-123456789abc",
                    "properties": {
                        "Name": {
                            "title": [
                                {
                                    "text": {
                                        "content": "Bug reported by john@example.com"
                                    }
                                }
                            ]
                        },
                        "Severity": {"select": {"name": "Blocker"}},
                        "Category": {"select": {"name": "Bug"}},
                        "Description": {
                            "rich_text": [
                                {"text": {"content": "Call +65 9123 4567 for details"}}
                            ]
                        },
                        "Page/Feature": {"select": {"name": "Coach"}},
                        "Status": {"select": {"name": "New"}},
                    },
                }
            ]
        }

        mock_client = MagicMock()
        mock_client.enabled = True
        mock_client.query_database.return_value = mock_response
        mock_client.update_page.return_value = {}

        with (
            patch.dict("os.environ", {"NOTION_API_KEY": "test-key"}),
            patch(
                "agents.shared.notion_client.NotionClient",
                return_value=mock_client,
            ),
        ):
            findings, _, _ = _check_beta_feedback()

        assert len(findings) == 1
        assert "john@example.com" not in findings[0].title
        assert "[email]" in findings[0].title
        assert "+65 9123 4567" not in findings[0].detail
        assert "[phone]" in findings[0].detail

    def test_handles_empty_notion_result(self):
        from product_team.product_lead.product_lead import _check_beta_feedback

        mock_client = MagicMock()
        mock_client.enabled = True
        mock_client.query_database.return_value = {"results": []}

        with (
            patch.dict("os.environ", {"NOTION_API_KEY": "test-key"}),
            patch(
                "agents.shared.notion_client.NotionClient",
                return_value=mock_client,
            ),
        ):
            findings, insights, xtr = _check_beta_feedback()

        assert findings == []
        assert insights == []
        assert xtr == []


# ---------------------------------------------------------------------------
# Feature 3: CoS conflict detection and resolution wiring
# ---------------------------------------------------------------------------


class TestDetectConflicts:
    """_detect_conflicts finds conflicts from cross-team requests."""

    def test_no_conflicts_when_empty(self):
        from agents.chief_of_staff.cos_agent import _detect_conflicts

        assert _detect_conflicts([]) == []

    def test_no_conflicts_single_request(self):
        from agents.chief_of_staff.cos_agent import _detect_conflicts

        reqs = [
            {
                "request": "Fix security issue",
                "urgency": "critical",
                "source_agent": "architect",
            }
        ]
        assert _detect_conflicts(reqs) == []

    def test_no_conflict_same_team(self):
        from agents.chief_of_staff.cos_agent import _detect_conflicts

        reqs = [
            {
                "request": "Fix security issue",
                "urgency": "critical",
                "source_agent": "architect",
            },
            {
                "request": "Security audit needed",
                "urgency": "low",
                "source_agent": "architect",
            },
        ]
        assert _detect_conflicts(reqs) == []

    def test_detects_urgency_gap_conflict(self):
        from agents.chief_of_staff.cos_agent import _detect_conflicts

        reqs = [
            {
                "request": "Ship feature launch now",
                "urgency": "critical",
                "source_agent": "gtm_lead",
            },
            {
                "request": "Feature launch blocked by shipping security review",
                "urgency": "low",
                "source_agent": "architect",
            },
        ]
        conflicts = _detect_conflicts(reqs)
        assert len(conflicts) >= 1
        c = conflicts[0]
        assert len(c.teams) == 2
        assert c.resolution_level == 1

    def test_no_conflict_when_urgency_close(self):
        from agents.chief_of_staff.cos_agent import _detect_conflicts

        reqs = [
            {
                "request": "Cost budget alert",
                "urgency": "high",
                "source_agent": "finance_lead",
            },
            {
                "request": "Cost optimization needed",
                "urgency": "medium",
                "source_agent": "ops_lead",
            },
        ]
        # Gap of 1 (high=3, medium=2) < 2 threshold
        assert _detect_conflicts(reqs) == []


class TestResolutionWiring:
    """Resolver produces valid Resolution objects."""

    def test_context_resolution_one_side_no_evidence(self):
        from agents.chief_of_staff.resolver import attempt_resolution
        from agents.chief_of_staff.schemas import Conflict

        conflict = Conflict(
            id="test-001",
            teams=["engineering", "gtm"],
            description="Test conflict",
            positions={"engineering": "Need security review", "gtm": "Ship now"},
            evidence={"engineering": "CVE found in dependency", "gtm": ""},
            resolution_level=1,
        )
        resolution = attempt_resolution(conflict)
        assert resolution.conflict_id == "test-001"
        assert resolution.strategy_used == "context_clarification"
        assert not resolution.escalated
        assert "engineering" in resolution.outcome

    def test_escalation_when_both_have_evidence(self):
        from agents.chief_of_staff.resolver import attempt_resolution
        from agents.chief_of_staff.schemas import Conflict

        conflict = Conflict(
            id="test-002",
            teams=["engineering", "gtm"],
            description="Both have evidence",
            positions={
                "engineering": "Technical elegance matters",
                "gtm": "Technical elegance also",
            },
            evidence={
                "engineering": "Code review shows issues",
                "gtm": "Market data shows urgency",
            },
            resolution_level=4,
        )
        resolution = attempt_resolution(conflict)
        assert resolution.conflict_id == "test-002"
        assert resolution.escalated

    def test_tradeoff_resolution_safety_wins(self):
        from agents.chief_of_staff.resolver import attempt_resolution
        from agents.chief_of_staff.schemas import Conflict

        conflict = Conflict(
            id="test-003",
            teams=["engineering", "gtm"],
            description="Safety vs speed",
            positions={
                "engineering": "This is a privacy and security concern",
                "gtm": "We need to optimize cost efficiency",
            },
            evidence={"engineering": "PII leak found", "gtm": "Budget overrun"},
            resolution_level=2,
        )
        resolution = attempt_resolution(conflict)
        assert resolution.conflict_id == "test-003"
        assert resolution.strategy_used == "tradeoff_framing"
        assert "engineering" in resolution.outcome


class TestFounderBriefSchema:
    """FounderBrief schema supports new fields."""

    def test_founder_requests_field_exists(self):
        from agents.chief_of_staff.schemas import FounderBrief

        brief = FounderBrief(date="2026-01-01")
        assert brief.founder_requests == []

    def test_resolutions_field_exists(self):
        from agents.chief_of_staff.schemas import FounderBrief

        brief = FounderBrief(date="2026-01-01")
        assert brief.resolutions == []

    def test_founder_requests_populated(self):
        from agents.chief_of_staff.schemas import FounderBrief

        brief = FounderBrief(
            date="2026-01-01",
            founder_requests=[{"title": "Focus on NH onboarding", "priority": "P0"}],
        )
        assert len(brief.founder_requests) == 1
        assert brief.founder_requests[0]["priority"] == "P0"

    def test_resolutions_populated(self):
        from agents.chief_of_staff.schemas import FounderBrief

        brief = FounderBrief(
            date="2026-01-01",
            resolutions=[
                {
                    "conflict_id": "c-001",
                    "strategy_used": "context_clarification",
                    "outcome": "Resolved in favor of engineering",
                    "escalated": False,
                }
            ],
        )
        assert len(brief.resolutions) == 1
        assert brief.resolutions[0]["strategy_used"] == "context_clarification"


class TestDailyBriefRendering:
    """synthesize_daily renders founder requests and resolutions."""

    def test_founder_requests_section_rendered(self):
        from agents.shared.report import AgentReport

        from agents.chief_of_staff.synthesizer import synthesize_daily

        report = AgentReport(agent="test", timestamp="2026-01-01T00:00:00Z")
        brief_md, brief_data = synthesize_daily(
            [report],
            founder_requests=[{"title": "Test request", "priority": "P0"}],
        )
        assert "Open requests from you" in brief_md
        assert "Test request" in brief_md
        assert len(brief_data["founder_requests"]) == 1

    def test_resolutions_section_rendered(self):
        from agents.shared.report import AgentReport

        from agents.chief_of_staff.synthesizer import synthesize_daily

        report = AgentReport(agent="test", timestamp="2026-01-01T00:00:00Z")
        brief_md, brief_data = synthesize_daily(
            [report],
            resolutions=[
                {
                    "conflict_id": "c-001",
                    "strategy_used": "compromise",
                    "outcome": "Sequence the work",
                    "escalated": False,
                }
            ],
        )
        assert "Resolved conflicts" in brief_md
        assert "Sequence the work" in brief_md

    def test_escalated_resolution_tagged(self):
        from agents.shared.report import AgentReport

        from agents.chief_of_staff.synthesizer import synthesize_daily

        report = AgentReport(agent="test", timestamp="2026-01-01T00:00:00Z")
        brief_md, _ = synthesize_daily(
            [report],
            resolutions=[
                {
                    "conflict_id": "c-002",
                    "strategy_used": "escalation",
                    "outcome": "Escalated to founder",
                    "escalated": True,
                }
            ],
        )
        assert "escalated to you" in brief_md

    def test_no_sections_when_empty(self):
        from agents.shared.report import AgentReport

        from agents.chief_of_staff.synthesizer import synthesize_daily

        report = AgentReport(agent="test", timestamp="2026-01-01T00:00:00Z")
        brief_md, _ = synthesize_daily([report])
        assert "Open requests from you" not in brief_md
        assert "Resolved conflicts" not in brief_md
