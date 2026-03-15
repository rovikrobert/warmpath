"""Tests for decision registry and Finding serialization."""

from dataclasses import asdict
from unittest.mock import patch

import pytest

from agents.shared.decision_registry import (
    PendingDecision,
    find_decision,
    load_pending_decisions,
    mark_executed,
    save_pending_decisions,
)
from agents.shared.report import Finding


class TestFindingFromDict:
    def test_round_trip_preserves_all_fields(self):
        """asdict → from_dict preserves every field including timestamps."""
        original = Finding(
            id="CVE-2026-001",
            severity="high",
            category="dependency-vulnerability",
            title="SSRF in langchain-core",
            detail="Fix available in v1.2.11",
            file="requirements.txt",
            line=35,
            recommendation="Bump langchain-core>=1.2.11",
            effort_hours=0.5,
            auto_fixable=True,
            first_seen="2026-03-10",
            last_validated_at="2026-03-13",
        )
        reconstructed = Finding.from_dict(asdict(original))
        assert reconstructed.id == original.id
        assert reconstructed.file == original.file
        assert reconstructed.auto_fixable is True
        assert reconstructed.first_seen == "2026-03-10"
        assert reconstructed.last_validated_at == "2026-03-13"

    def test_unknown_fields_ignored(self):
        """Extra keys from future schema versions don't crash."""
        data = {
            "id": "TEST-1",
            "severity": "low",
            "category": "test",
            "title": "Test",
            "detail": "d",
            "futu[RESEND_KEY_REDACTED]": "should_be_ignored",
            "another_new": 42,
        }
        f = Finding.from_dict(data)
        assert f.id == "TEST-1"
        assert not hasattr(f, "futu[RESEND_KEY_REDACTED]")

    def test_missing_optional_fields_get_defaults(self):
        """Minimal dict (required fields only) produces valid Finding."""
        data = {
            "id": "MIN-1",
            "severity": "medium",
            "category": "security",
            "title": "Minimal",
            "detail": "d",
        }
        f = Finding.from_dict(data)
        assert f.file is None
        assert f.auto_fixable is False
        assert f.first_seen != ""  # __post_init__ fills this


def _make_decision(number: int = 1, finding_id: str = "CVE-001") -> PendingDecision:
    return PendingDecision(
        number=number,
        finding_id=finding_id,
        finding={
            "id": finding_id,
            "severity": "high",
            "category": "dependency-vulnerability",
            "title": "Test finding",
            "detail": "d",
        },
        brief_date="2026-03-13",
        tier="auto_pr",
        action_plan="Bump dep to fix CVE",
    )


class TestDecisionRegistry:
    @pytest.mark.smoke
    def test_save_and_load_round_trip(self, tmp_path):
        """Saved decisions can be loaded back identically."""
        decisions = [_make_decision(1, "A"), _make_decision(2, "B")]
        path = tmp_path / "pending_decisions.json"
        with patch("agents.shared.decision_registry.DECISIONS_PATH", path):
            save_pending_decisions(decisions)
            loaded = load_pending_decisions()
        assert len(loaded) == 2
        assert loaded[0].finding_id == "A"
        assert loaded[1].number == 2

    @pytest.mark.smoke
    def test_find_decision_by_number(self, tmp_path):
        """find_decision returns the matching decision or None."""
        decisions = [_make_decision(1, "A"), _make_decision(2, "B")]
        path = tmp_path / "pending_decisions.json"
        with patch("agents.shared.decision_registry.DECISIONS_PATH", path):
            save_pending_decisions(decisions)
            found = find_decision(2)
            missing = find_decision(9)
        assert found is not None
        assert found.finding_id == "B"
        assert missing is None

    @pytest.mark.smoke
    def test_mark_executed_sets_timestamp_and_summary(self, tmp_path):
        """mark_executed stamps executed_at and result_summary."""
        path = tmp_path / "pending_decisions.json"
        with patch("agents.shared.decision_registry.DECISIONS_PATH", path):
            save_pending_decisions([_make_decision(1)])
            mark_executed(1, "PR opened: https://github.com/test/1")
            loaded = load_pending_decisions()
        assert loaded[0].executed_at is not None
        assert "PR opened" in loaded[0].result_summary

    def test_double_execution_detected(self, tmp_path):
        """find_decision returns decision with executed_at set after marking."""
        path = tmp_path / "pending_decisions.json"
        with patch("agents.shared.decision_registry.DECISIONS_PATH", path):
            save_pending_decisions([_make_decision(1)])
            mark_executed(1, "Done")
            found = find_decision(1)
        assert found is not None
        assert found.executed_at is not None

    def test_rejection_marks_as_executed(self, tmp_path):
        """Rejecting a decision sets executed_at with rejection summary."""
        path = tmp_path / "pending_decisions.json"
        with patch("agents.shared.decision_registry.DECISIONS_PATH", path):
            save_pending_decisions([_make_decision(1)])
            mark_executed(1, "Rejected by founder")
            found = find_decision(1)
        assert "Rejected" in found.result_summary

    def test_load_missing_file_returns_empty(self, tmp_path):
        """Loading when no file exists returns empty list."""
        path = tmp_path / "nonexistent.json"
        with patch("agents.shared.decision_registry.DECISIONS_PATH", path):
            loaded = load_pending_decisions()
        assert loaded == []

    def test_save_caps_at_three_decisions(self, tmp_path):
        """Only first 3 decisions are saved (matches Telegram display cap)."""
        decisions = [_make_decision(i) for i in range(1, 6)]
        path = tmp_path / "pending_decisions.json"
        with patch("agents.shared.decision_registry.DECISIONS_PATH", path):
            save_pending_decisions(decisions)
            loaded = load_pending_decisions()
        assert len(loaded) == 3

    def test_pending_decision_includes_failu[RESEND_KEY_REDACTED](self):
        """PendingDecision should store failu[RESEND_KEY_REDACTED] and rollback_plan."""
        d = PendingDecision(
            number=1,
            finding_id="CVE-001",
            finding={
                "id": "CVE-001",
                "severity": "high",
                "category": "dep",
                "title": "t",
                "detail": "d",
            },
            brief_date="2026-03-15",
            tier="auto_pr",
            action_plan="Bump dep",
            failu[RESEND_KEY_REDACTED]=["Breaks API compat if new version drops method"],
            rollback_plan="Revert bump commit, pin to previous version",
        )
        assert d.failu[RESEND_KEY_REDACTED] == ["Breaks API compat if new version drops method"]
        assert d.rollback_plan == "Revert bump commit, pin to previous version"

    def test_pending_decision_failu[RESEND_KEY_REDACTED](self):
        """failu[RESEND_KEY_REDACTED] defaults to empty list, rollback_plan to empty string."""
        d = _make_decision(1)
        assert d.failu[RESEND_KEY_REDACTED] == []
        assert d.rollback_plan == ""

    def test_failu[RESEND_KEY_REDACTED](self, tmp_path):
        """failu[RESEND_KEY_REDACTED] and rollback_plan persist through save/load cycle."""
        d = PendingDecision(
            number=1,
            finding_id="A",
            finding={
                "id": "A",
                "severity": "high",
                "category": "t",
                "title": "t",
                "detail": "d",
            },
            brief_date="2026-03-15",
            tier="escalate",
            action_plan="Fix auth bypass",
            failu[RESEND_KEY_REDACTED]=["Could break SSO", "May invalidate sessions"],
            rollback_plan="Revert PR, re-enable old auth middleware",
        )
        path = tmp_path / "pending_decisions.json"
        with patch("agents.shared.decision_registry.DECISIONS_PATH", path):
            save_pending_decisions([d])
            loaded = load_pending_decisions()
        assert loaded[0].failu[RESEND_KEY_REDACTED] == ["Could break SSO", "May invalidate sessions"]
        assert loaded[0].rollback_plan == "Revert PR, re-enable old auth middleware"

    @pytest.mark.smoke
    def test_from_dict_ignores_unknown_fields(self):
        """from_dict drops unknown keys from future schema versions."""
        data = {
            "number": 1,
            "finding_id": "F1",
            "finding": {
                "id": "F1",
                "severity": "low",
                "category": "t",
                "title": "t",
                "detail": "d",
            },
            "brief_date": "2026-03-15",
            "tier": "auto_pr",
            "action_plan": "Fix it",
            "futu[RESEND_KEY_REDACTED]": "should be ignored",
            "another_new": 42,
        }
        d = PendingDecision.from_dict(data)
        assert d.finding_id == "F1"
        assert d.failu[RESEND_KEY_REDACTED] == []
        assert not hasattr(d, "futu[RESEND_KEY_REDACTED]")

    @pytest.mark.smoke
    def test_load_survives_futu[RESEND_KEY_REDACTED](self, tmp_path):
        """JSON with unknown fields from a future version loads without data loss."""
        import json

        path = tmp_path / "pending_decisions.json"
        futu[RESEND_KEY_REDACTED] = [
            {
                "number": 1,
                "finding_id": "FUT-1",
                "finding": {
                    "id": "FUT-1",
                    "severity": "high",
                    "category": "t",
                    "title": "t",
                    "detail": "d",
                },
                "brief_date": "2026-04-01",
                "tier": "escalate",
                "action_plan": "Do something",
                "failu[RESEND_KEY_REDACTED]": ["risk A"],
                "rollback_plan": "revert",
                "executed_at": None,
                "result_summary": None,
                "new_futu[RESEND_KEY_REDACTED]": "from v2",
            }
        ]
        path.write_text(json.dumps(futu[RESEND_KEY_REDACTED]))
        with patch("agents.shared.decision_registry.DECISIONS_PATH", path):
            loaded = load_pending_decisions()
        assert len(loaded) == 1
        assert loaded[0].finding_id == "FUT-1"
        assert loaded[0].failu[RESEND_KEY_REDACTED] == ["risk A"]

    def test_find_decision_by_finding_id(self, tmp_path):
        """find_decision returns the matching decision by stable finding_id."""
        decisions = [_make_decision(1, "sec-001"), _make_decision(2, "lint-042")]
        path = tmp_path / "pending_decisions.json"
        with patch("agents.shared.decision_registry.DECISIONS_PATH", path):
            save_pending_decisions(decisions)
            found = find_decision(finding_id="lint-042")
            missing = find_decision(finding_id="nonexistent")
        assert found is not None
        assert found.number == 2
        assert found.finding_id == "lint-042"
        assert missing is None

    def test_find_decision_finding_id_stable_across_reorder(self, tmp_path):
        """finding_id lookup is stable even if positional number changes."""
        decisions = [_make_decision(1, "sec-001"), _make_decision(2, "lint-042")]
        path = tmp_path / "pending_decisions.json"
        with patch("agents.shared.decision_registry.DECISIONS_PATH", path):
            save_pending_decisions(decisions)
            # Simulate brief regeneration: same finding_id but different number
            reordered = [_make_decision(1, "lint-042"), _make_decision(2, "sec-001")]
            save_pending_decisions(reordered)
            found = find_decision(finding_id="sec-001")
        assert found is not None
        assert found.number == 2  # position changed but lookup still works
        assert found.finding_id == "sec-001"
