"""Tests for agents/shared/learning.py — backward compat + AgentLearningState."""

from __futu[RESEND_KEY_REDACTED] import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest

# Patch AGENTS_DIR before importing learning so state files go to tmp
_tmp = tempfile.mkdtemp()
_agents_dir = Path(_tmp) / "agents"
_agents_dir.mkdir()


@pytest.fixture(autouse=True)
def _patch_agents_dir(monkeypatch):
    """Redirect all state I/O to a temp directory."""
    monkeypatch.setattr("agents.shared.learning.AGENTS_DIR", _agents_dir)
    # Clean up agent state dirs before each test
    import shutil

    for child in _agents_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
    yield


# ---------------------------------------------------------------------------
# Import after patching setup
# ---------------------------------------------------------------------------
from agents.shared.learning import (
    AgentLearningState,
    AttentionWeight,
    FindingSeverity,
    FixEffectivenessRecord,
    HealthSnapshot,
    MethodologyRecord,
    ResolutionType,
    _load_state,
    _migrate_state,
    _save_state,
    get_attention_weights,
    get_learning_state,
    get_recurrence_count,
    get_total_scans,
    get_trend,
    record_finding,
    record_resolution,
    record_scan,
    update_attention_weights,
)


# ===========================================================================
# TestDataStructures
# ===========================================================================


class TestDataStructures:
    """Verify enums and dataclasses can be created."""

    def test_resolution_type_values(self):
        assert ResolutionType.FIXED == "fixed"
        assert ResolutionType.DEFERRED == "deferred"
        assert ResolutionType.IGNORED == "ignored"
        assert ResolutionType.FALSE_POSITIVE == "false_positive"
        assert ResolutionType.WONT_FIX == "wont_fix"

    def test_finding_severity_values(self):
        assert FindingSeverity.CRITICAL == "critical"
        assert FindingSeverity.HIGH == "high"
        assert FindingSeverity.MEDIUM == "medium"
        assert FindingSeverity.LOW == "low"
        assert FindingSeverity.INFO == "info"

    def test_attention_weight_dataclass(self):
        aw = AttentionWeight(file="foo.py", weight=2.5)
        assert aw.file == "foo.py"
        assert aw.weight == 2.5
        assert aw.last_updated  # auto-filled

    def test_methodology_record_dataclass(self):
        mr = MethodologyRecord(name="TDD", source="internal", effectiveness=0.8)
        assert mr.name == "TDD"
        assert mr.adopted_at  # auto-filled

    def test_fix_effectiveness_record(self):
        fer = FixEffectivenessRecord(
            finding_id="f1", resolution_type="fixed", resolved_at="2026-01-01"
        )
        assert fer.effective is True
        assert fer.recurred is False

    def test_health_snapshot(self):
        hs = HealthSnapshot(score=85.0, finding_counts={"critical": 0, "high": 2})
        assert hs.score == 85.0
        assert hs.timestamp  # auto-filled


# ===========================================================================
# TestStateMigration
# ===========================================================================


class TestStateMigration:
    """Verify old state schemas get migrated without data loss."""

    def test_migrate_old_schema(self):
        """Old v1 state should gain new keys, existing keys untouched."""
        old_state = {
            "last_scan": "2026-01-01T00:00:00",
            "total_scans": 5,
            "finding_history": [{"id": "f1", "severity": "high"}],
            "attention_weights": {"foo.py": 1.5},
            "metrics_history": [],
            "resolutions": {"f1": {"type": "fixed", "timestamp": "2026-01-01"}},
        }
        migrated = _migrate_state(old_state)
        # Old keys preserved
        assert migrated["total_scans"] == 5
        assert len(migrated["finding_history"]) == 1
        assert migrated["resolutions"]["f1"]["type"] == "fixed"
        # New keys added
        assert migrated["recurring_patterns"] == {}
        assert migrated["severity_calibration"] == {}
        assert migrated["tool_accuracy"] == {}
        assert migrated["methodologies"] == []
        assert migrated["codebase_health_history"] == []

    def test_fresh_state_has_all_keys(self):
        """Loading a non-existent agent should return all keys."""
        state = _load_state("nonexistent_agent_xyz")
        assert "recurring_patterns" in state
        assert "severity_calibration" in state
        assert "tool_accuracy" in state
        assert "methodologies" in state
        assert "codebase_health_history" in state
        assert "finding_history" in state

    def test_corrupt_state_resets(self):
        """Corrupt JSON should reset to defaults."""
        agent = "corrupt_agent"
        path = _agents_dir / agent
        path.mkdir(parents=True, exist_ok=True)
        (path / "state.json").write_text("NOT VALID JSON {{{")

        state = _load_state(agent)
        assert state["total_scans"] == 0
        assert state["finding_history"] == []
        assert "recurring_patterns" in state

    def test_migrate_idempotent(self):
        """Migrating an already-migrated state is a no-op."""
        state = _load_state("fresh_agent")
        migrated_once = _migrate_state(state)
        migrated_twice = _migrate_state(migrated_once)
        assert migrated_once == migrated_twice


# ===========================================================================
# TestBackwardCompat
# ===========================================================================


class TestBackwardCompat:
    """All 8 module-level functions work exactly as before."""

    def test_record_finding(self):
        agent = "test_compat"
        record_finding(
            agent,
            {
                "id": "f1",
                "severity": "high",
                "category": "security",
                "file": "app/main.py",
                "line": 42,
                "title": "Test finding",
            },
        )
        state = _load_state(agent)
        assert len(state["finding_history"]) == 1
        assert state["finding_history"][0]["id"] == "f1"
        assert state["finding_history"][0]["severity"] == "high"

    def test_get_recurrence_count(self):
        agent = "test_recurrence"
        record_finding(agent, {"id": "f1", "category": "lint", "file": "a.py"})
        record_finding(agent, {"id": "f2", "category": "lint", "file": "a.py"})
        record_finding(agent, {"id": "f3", "category": "lint", "file": "b.py"})
        assert get_recurrence_count(agent, "lint") == 3
        assert get_recurrence_count(agent, "lint", "a.py") == 2
        assert get_recurrence_count(agent, "lint", "c.py") == 0

    def test_get_trend_insufficient_data(self):
        assert get_trend("no_data_agent", "some_metric") == "insufficient_data"

    def test_get_trend_with_data(self):
        agent = "trend_agent"
        # Record two scans with increasing metric
        now = datetime.now(timezone.utc)
        state = _load_state(agent)
        state["metrics_history"] = [
            {
                "timestamp": (now - timedelta(days=5)).isoformat(),
                "metrics": {"score": 10},
            },
            {
                "timestamp": (now - timedelta(days=4)).isoformat(),
                "metrics": {"score": 12},
            },
            {
                "timestamp": (now - timedelta(days=3)).isoformat(),
                "metrics": {"score": 14},
            },
            {
                "timestamp": (now - timedelta(days=2)).isoformat(),
                "metrics": {"score": 20},
            },
        ]
        _save_state(agent, state)
        result = get_trend(agent, "score")
        assert result in ("up", "down", "stable")

    def test_update_attention_weights(self):
        agent = "attn_agent"
        update_attention_weights(agent, {"foo.py": 3, "bar.py": 1})
        weights = get_attention_weights(agent)
        assert "foo.py" in weights
        assert "bar.py" in weights
        assert isinstance(weights["foo.py"], float)
        assert isinstance(weights["bar.py"], float)

    def test_get_attention_weights_empty(self):
        assert get_attention_weights("empty_agent") == {}

    def test_record_scan(self):
        agent = "scan_agent"
        record_scan(agent, {"coverage": 85.0})
        state = _load_state(agent)
        assert state["total_scans"] == 1
        assert state["last_scan"] is not None
        assert len(state["metrics_history"]) == 1

    def test_record_resolution(self):
        agent = "resolve_agent"
        record_resolution(agent, "f1", "fixed")
        state = _load_state(agent)
        assert state["resolutions"]["f1"]["type"] == "fixed"

    def test_get_total_scans(self):
        agent = "scans_agent"
        assert get_total_scans(agent) == 0
        record_scan(agent, {"x": 1})
        assert get_total_scans(agent) == 1
        record_scan(agent, {"x": 2})
        assert get_total_scans(agent) == 2

    def test_record_finding_keeps_last_500(self):
        agent = "overflow_agent"
        for i in range(510):
            record_finding(agent, {"id": f"f{i}", "category": "test"})
        state = _load_state(agent)
        assert len(state["finding_history"]) == 500

    def test_attention_weights_ema_formula(self):
        """Verify the backward-compat EMA matches the original formula."""
        agent = "ema_agent"
        # First update: current=1.0, count=2
        # new = 1.0 * 0.7 + (1.0 + 2 * 0.3) * 0.3 = 0.7 + 1.6 * 0.3 = 0.7 + 0.48 = 1.18
        update_attention_weights(agent, {"test.py": 2})
        weights = get_attention_weights(agent)
        assert weights["test.py"] == 1.18


# ===========================================================================
# TestAgentLearningState
# ===========================================================================


class TestAgentLearningState:
    """Test the new AgentLearningState class methods."""

    def _make_ls(self, agent: str = "test_agent") -> AgentLearningState:
        return AgentLearningState(agent)

    def test_init_fresh_agent(self):
        ls = self._make_ls("fresh")
        assert ls.agent == "fresh"
        assert ls.state["total_scans"] == 0
        assert ls.state["recurring_patterns"] == {}

    def test_record_finding_updates_patterns(self):
        ls = self._make_ls("pat_agent")
        ls.record_finding({"id": "f1", "category": "lint", "file": "x.py"})
        ls.load()  # reload from disk
        pattern = ls.state["recurring_patterns"].get("lint:x.py")
        assert pattern is not None
        assert pattern["count"] == 1
        assert pattern["auto_escalated"] is False

    def test_record_resolution_with_enum(self):
        ls = self._make_ls("enum_agent")
        ls.record_finding({"id": "f1", "severity": "high", "category": "sec"})
        ls.record_resolution("f1", ResolutionType.FIXED)
        ls.load()
        assert ls.state["resolutions"]["f1"]["type"] == "fixed"

    def test_record_resolution_with_string(self):
        ls = self._make_ls("str_agent")
        ls.record_finding({"id": "f1", "severity": "medium", "category": "lint"})
        ls.record_resolution("f1", "deferred")
        ls.load()
        assert ls.state["resolutions"]["f1"]["type"] == "deferred"

    def test_check_fix_effectiveness_no_resolution(self):
        ls = self._make_ls("eff1")
        assert ls.check_fix_effectiveness("nonexistent") is None

    def test_check_fix_effectiveness_no_recurrence(self):
        ls = self._make_ls("eff2")
        ls.record_finding({"id": "f1", "category": "sec", "file": "a.py"})
        ls.record_resolution("f1", "fixed")
        result = ls.check_fix_effectiveness("f1")
        assert result is not None
        assert result.effective is True
        assert result.recurred is False

    def test_check_fix_effectiveness_with_recurrence(self):
        ls = self._make_ls("eff3")
        # Record finding
        ls.record_finding({"id": "f1", "category": "sec", "file": "a.py"})
        ls.record_resolution("f1", "fixed")
        # Record same-category finding after resolution
        ls.record_finding({"id": "f2", "category": "sec", "file": "a.py"})
        result = ls.check_fix_effectiveness("f1")
        assert result is not None
        assert result.recurred is True
        assert result.effective is False
        assert result.recurrence_count_after >= 1

    def test_detect_recurring_pattern_empty(self):
        ls = self._make_ls("empty_pat")
        result = ls.detect_recurring_pattern("lint", "foo.py")
        assert result["count"] == 0
        assert result["auto_escalated"] is False

    def test_detect_recurring_pattern_with_data(self):
        ls = self._make_ls("data_pat")
        for i in range(3):
            ls.record_finding({"id": f"f{i}", "category": "lint", "file": "foo.py"})
        result = ls.detect_recurring_pattern("lint", "foo.py")
        assert result["count"] == 3
        assert result["auto_escalated"] is False

    def test_get_recurrence_count_class(self):
        ls = self._make_ls("rc_agent")
        ls.record_finding({"id": "f1", "category": "sec", "file": "a.py"})
        ls.record_finding({"id": "f2", "category": "sec", "file": "a.py"})
        assert ls.get_recurrence_count("sec", "a.py") == 2
        assert ls.get_recurrence_count("sec") == 2
        assert ls.get_recurrence_count("lint") == 0

    def test_update_attention_weights_class(self):
        ls = self._make_ls("attn_cls")
        ls.update_attention_weights({"foo.py": 3})
        spots = ls.get_hot_spots(top_n=1)
        assert len(spots) == 1
        assert spots[0].file == "foo.py"
        assert spots[0].weight > 1.0

    def test_get_hot_spots(self):
        ls = self._make_ls("spots_agent")
        ls.update_attention_weights({"a.py": 5, "b.py": 1, "c.py": 10})
        spots = ls.get_hot_spots(top_n=2)
        assert len(spots) == 2
        # Highest weight first
        assert spots[0].weight >= spots[1].weight

    def test_get_stable_areas(self):
        ls = self._make_ls("stable_agent")
        # Manually set weights
        ls.state["attention_weights"] = {
            "a.py": {"weight": 0.5, "last_updated": "2026-01-01"},
            "b.py": {"weight": 2.0, "last_updated": "2026-01-01"},
            "c.py": {"weight": 1.0, "last_updated": "2026-01-01"},
        }
        stable = ls.get_stable_areas(threshold=1.0)
        assert "a.py" in stable
        assert "c.py" in stable
        assert "b.py" not in stable

    def test_severity_calibration(self):
        ls = self._make_ls("sev_cal")
        ls.record_severity_calibration("high")
        ls.record_severity_calibration("high")
        ls.record_severity_calibration("high", was_overridden=True)
        cal = ls.get_severity_calibration()
        assert cal["high"]["total"] == 3
        assert cal["high"]["overridden"] == 1

    def test_tool_accuracy(self):
        ls = self._make_ls("tool_agent")
        ls.record_tool_accuracy("ruff", "f1", confirmed=True)
        ls.record_tool_accuracy("ruff", "f2", confirmed=True)
        ls.record_tool_accuracy("ruff", "f3", confirmed=False)
        reliability = ls.get_tool_reliability()
        assert "ruff" in reliability
        assert abs(reliability["ruff"] - 0.667) < 0.01

    def test_tool_reliability_no_data(self):
        ls = self._make_ls("no_tool")
        assert ls.get_tool_reliability() == {}

    def test_record_methodology(self):
        ls = self._make_ls("method_agent")
        ls.record_methodology("TDD", "best_practices", effectiveness=0.9)
        ls.load()
        assert len(ls.state["methodologies"]) == 1
        assert ls.state["methodologies"][0]["name"] == "TDD"

    def test_health_snapshot(self):
        ls = self._make_ls("health_agent")
        ls.record_health_snapshot(85.0, {"critical": 0, "high": 2})
        ls.load()
        assert len(ls.state["codebase_health_history"]) == 1
        assert ls.state["codebase_health_history"][0]["score"] == 85.0

    def test_health_trajectory_insufficient(self):
        ls = self._make_ls("traj1")
        assert ls.get_health_trajectory() == "insufficient_data"

    def test_health_trajectory_improving(self):
        ls = self._make_ls("traj2")
        now = datetime.now(timezone.utc)
        ls.state["codebase_health_history"] = [
            {"score": 60.0, "timestamp": (now - timedelta(days=10)).isoformat()},
            {"score": 62.0, "timestamp": (now - timedelta(days=8)).isoformat()},
            {"score": 80.0, "timestamp": (now - timedelta(days=3)).isoformat()},
            {"score": 85.0, "timestamp": (now - timedelta(days=1)).isoformat()},
        ]
        assert ls.get_health_trajectory() == "improving"

    def test_health_trajectory_degrading(self):
        ls = self._make_ls("traj3")
        now = datetime.now(timezone.utc)
        ls.state["codebase_health_history"] = [
            {"score": 90.0, "timestamp": (now - timedelta(days=10)).isoformat()},
            {"score": 88.0, "timestamp": (now - timedelta(days=8)).isoformat()},
            {"score": 60.0, "timestamp": (now - timedelta(days=3)).isoformat()},
            {"score": 55.0, "timestamp": (now - timedelta(days=1)).isoformat()},
        ]
        assert ls.get_health_trajectory() == "degrading"

    def test_health_trajectory_stable(self):
        ls = self._make_ls("traj4")
        now = datetime.now(timezone.utc)
        ls.state["codebase_health_history"] = [
            {"score": 80.0, "timestamp": (now - timedelta(days=10)).isoformat()},
            {"score": 81.0, "timestamp": (now - timedelta(days=8)).isoformat()},
            {"score": 80.0, "timestamp": (now - timedelta(days=3)).isoformat()},
            {"score": 80.5, "timestamp": (now - timedelta(days=1)).isoformat()},
        ]
        assert ls.get_health_trajectory() == "stable"

    def test_generate_meta_learning_report(self):
        ls = self._make_ls("meta_agent")
        ls.record_finding(
            {"id": "f1", "severity": "high", "category": "sec", "file": "a.py"}
        )
        ls.record_resolution("f1", "fixed")
        ls.record_tool_accuracy("ruff", "f1", confirmed=True)
        ls.record_health_snapshot(85.0, {"high": 1})

        report = ls.generate_meta_learning_report()
        assert report["agent"] == "meta_agent"
        assert report["total_findings_tracked"] == 1
        assert "hot_spots" in report
        assert "escalated_patterns" in report
        assert "systemic_patterns" in report
        assert "fix_effectiveness_rate" in report
        assert "tool_reliability" in report
        assert "severity_calibration" in report
        assert "health_trajectory" in report
        assert "methodologies_adopted" in report

    def test_save_and_load_roundtrip(self):
        ls = self._make_ls("roundtrip")
        ls.record_finding({"id": "f1", "category": "test"})
        ls.record_methodology("DDD", "book")

        ls2 = AgentLearningState("roundtrip")
        assert len(ls2.state["finding_history"]) == 1
        assert len(ls2.state["methodologies"]) == 1

    def test_get_learning_state_convenience(self):
        ls = get_learning_state("conv_agent")
        assert isinstance(ls, AgentLearningState)
        assert ls.agent == "conv_agent"


# ===========================================================================
# TestAttentionWeightDecay
# ===========================================================================


class TestAttentionWeightDecay:
    """Verify time-based decay in AgentLearningState.update_attention_weights."""

    def test_decay_reduces_old_weights(self):
        ls = AgentLearningState("decay_agent")
        # Set an old weight (10 days ago)
        old_time = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        ls.state["attention_weights"] = {
            "old_file.py": {
                "weight": 3.0,
                "last_updated": old_time,
                "reason": "old scan",
            }
        }
        ls.save()

        ls2 = AgentLearningState("decay_agent")
        ls2.update_attention_weights({"old_file.py": 1})

        spots = ls2.get_hot_spots(top_n=1)
        # Weight should be less than 3.0 due to decay before EMA
        assert spots[0].weight < 3.0

    def test_no_decay_for_recent_weights(self):
        ls = AgentLearningState("recent_agent")
        # Set a recent weight (today)
        now_iso = datetime.now(timezone.utc).isoformat()
        ls.state["attention_weights"] = {
            "recent.py": {
                "weight": 2.0,
                "last_updated": now_iso,
                "reason": "recent",
            }
        }
        ls.save()

        ls2 = AgentLearningState("recent_agent")
        ls2.update_attention_weights({"recent.py": 1})

        spots = ls2.get_hot_spots(top_n=1)
        # EMA: 2.0 * 0.7 + (1.0 + 1 * 0.3) * 0.3 = 1.4 + 0.39 = 1.79
        assert abs(spots[0].weight - 1.79) < 0.05


# ===========================================================================
# TestRecurringPatternEscalation
# ===========================================================================


class TestRecurringPatternEscalation:
    """Verify auto-escalation at threshold boundaries."""

    def test_below_threshold_not_escalated(self):
        ls = AgentLearningState("esc1")
        for i in range(4):
            ls.record_finding({"id": f"f{i}", "category": "lint", "file": "x.py"})
        pattern = ls.detect_recurring_pattern("lint", "x.py")
        assert pattern["count"] == 4
        assert pattern["auto_escalated"] is False
        assert pattern["systemic"] is False

    def test_at_threshold_auto_escalated(self):
        ls = AgentLearningState("esc2")
        for i in range(5):
            ls.record_finding({"id": f"f{i}", "category": "lint", "file": "x.py"})
        pattern = ls.detect_recurring_pattern("lint", "x.py")
        assert pattern["count"] == 5
        assert pattern["auto_escalated"] is True
        assert pattern["systemic"] is False

    def test_systemic_threshold(self):
        ls = AgentLearningState("esc3")
        for i in range(10):
            ls.record_finding({"id": f"f{i}", "category": "lint", "file": "x.py"})
        pattern = ls.detect_recurring_pattern("lint", "x.py")
        assert pattern["count"] == 10
        assert pattern["auto_escalated"] is True
        assert pattern["systemic"] is True

    def test_pattern_key_without_file(self):
        """Category-only patterns use just the category as key."""
        ls = AgentLearningState("esc4")
        for i in range(5):
            ls.record_finding({"id": f"f{i}", "category": "type_error"})
        pattern = ls.detect_recurring_pattern("type_error")
        assert pattern["count"] == 5
        assert pattern["auto_escalated"] is True

    def test_different_files_different_patterns(self):
        ls = AgentLearningState("esc5")
        for i in range(3):
            ls.record_finding({"id": f"fa{i}", "category": "lint", "file": "a.py"})
        for i in range(3):
            ls.record_finding({"id": f"fb{i}", "category": "lint", "file": "b.py"})
        pa = ls.detect_recurring_pattern("lint", "a.py")
        pb = ls.detect_recurring_pattern("lint", "b.py")
        assert pa["count"] == 3
        assert pb["count"] == 3
        assert pa["auto_escalated"] is False
        assert pb["auto_escalated"] is False


# ===========================================================================
# TestMixedWeightFormats
# ===========================================================================


class TestMixedWeightFormats:
    """Backward compat handles both flat floats and dict weights."""

    def test_flat_float_weights(self):
        """Old-format flat float weights are handled by get_attention_weights."""
        agent = "flat_agent"
        state = _load_state(agent)
        state["attention_weights"] = {"a.py": 1.5, "b.py": 2.0}
        _save_state(agent, state)

        weights = get_attention_weights(agent)
        assert weights["a.py"] == 1.5
        assert weights["b.py"] == 2.0

    def test_dict_weights(self):
        """New-format dict weights are normalized by get_attention_weights."""
        agent = "dict_agent"
        state = _load_state(agent)
        state["attention_weights"] = {
            "a.py": {"weight": 1.5, "last_updated": "2026-01-01"},
        }
        _save_state(agent, state)

        weights = get_attention_weights(agent)
        assert weights["a.py"] == 1.5

    def test_update_on_flat_preserves_flat(self):
        """Backward-compat update_attention_weights stores flat floats."""
        agent = "flat_update"
        update_attention_weights(agent, {"x.py": 2})
        state = _load_state(agent)
        # Should be flat float, not dict
        assert isinstance(state["attention_weights"]["x.py"], float)

    def test_class_update_stores_dict(self):
        """AgentLearningState.update_attention_weights stores dict format."""
        ls = AgentLearningState("cls_update")
        ls.update_attention_weights({"y.py": 2})
        ls.load()
        assert isinstance(ls.state["attention_weights"]["y.py"], dict)
        assert "weight" in ls.state["attention_weights"]["y.py"]
