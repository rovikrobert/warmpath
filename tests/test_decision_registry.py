"""Tests for decision registry and Finding serialization."""

from dataclasses import asdict
from unittest.mock import patch

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
            "future_field": "should_be_ignored",
            "another_new": 42,
        }
        f = Finding.from_dict(data)
        assert f.id == "TEST-1"
        assert not hasattr(f, "future_field")

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
