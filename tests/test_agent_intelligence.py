"""Tests for agents/shared/intelligence.py — backward compat + ExternalIntelligence."""

from __futu[RESEND_KEY_REDACTED] import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest

# Patch INTEL_CACHE before importing intelligence so it writes to tmp
_tmp = tempfile.mkdtemp()
_intel_cache = Path(_tmp) / "intel_cache.json"


@pytest.fixture(autouse=True)
def _patch_intel_cache(monkeypatch):
    """Redirect intel cache to temp file and clean between tests."""
    monkeypatch.setattr("agents.shared.intelligence.INTEL_CACHE", _intel_cache)
    if _intel_cache.exists():
        _intel_cache.unlink()
    yield


from agents.shared.intelligence import (
    INTEL_CATEGORIES,
    ExternalIntelligence,
    IntelligenceItem,
    _is_stale,
    _load_cache,
    _save_cache,
    fetch_api_status,
    fetch_framework_updates,
    fetch_python_advisories,
    get_agent_intel,
    get_all_intelligence,
)
from agents.shared.config import AGENT_NAMES


# ===========================================================================
# TestIntelligenceItem
# ===========================================================================


class TestIntelligenceItem:
    """Verify dataclass creation and defaults."""

    def test_defaults(self):
        item = IntelligenceItem()
        assert item.id  # auto-generated
        assert item.fetched_at  # auto-filled
        assert item.severity == "info"
        assert item.adopted is False
        assert item.adopted_by == ""
        assert item.relevant_agents == []

    def test_explicit_values(self):
        item = IntelligenceItem(
            id="test-1",
            category="python_advisories",
            title="CVE-2026-0001",
            summary="Critical vuln in requests",
            severity="critical",
            relevant_agents=["deps_manager", "security"],
        )
        assert item.id == "test-1"
        assert item.category == "python_advisories"
        assert item.severity == "critical"
        assert len(item.relevant_agents) == 2

    def test_custom_fetched_at_preserved(self):
        item = IntelligenceItem(fetched_at="2026-01-01T00:00:00")
        assert item.fetched_at == "2026-01-01T00:00:00"


# ===========================================================================
# TestIntelCategories
# ===========================================================================


class TestIntelCategories:
    """Validate the 13 categories have required fields and valid agents."""

    def test_exactly_13_categories(self):
        assert len(INTEL_CATEGORIES) == 13

    def test_all_categories_have_required_fields(self):
        for name, meta in INTEL_CATEGORIES.items():
            assert "refresh_hours" in meta, f"{name} missing refresh_hours"
            assert "agents" in meta, f"{name} missing agents"
            assert "source" in meta, f"{name} missing source"
            assert "description" in meta, f"{name} missing description"
            assert isinstance(meta["agents"], list), f"{name} agents should be list"
            assert len(meta["agents"]) >= 1, f"{name} should have at least 1 agent"

    def test_all_referenced_agents_exist(self):
        for name, meta in INTEL_CATEGORIES.items():
            for agent in meta["agents"]:
                assert agent in AGENT_NAMES, (
                    f"Category '{name}' references unknown agent '{agent}'"
                )

    def test_refresh_hours_a[RESEND_KEY_REDACTED](self):
        for name, meta in INTEL_CATEGORIES.items():
            assert meta["refresh_hours"] > 0, f"{name} refresh_hours must be > 0"


# ===========================================================================
# TestBackwardCompat
# ===========================================================================


class TestBackwardCompat:
    """All 5 existing module-level functions return expected types."""

    def test_fetch_python_advisories_returns_list(self):
        with mock.patch("agents.shared.intelligence.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("pip-audit not installed")
            result = fetch_python_advisories()
        assert isinstance(result, list)

    def test_fetch_api_status_returns_dict(self):
        result = fetch_api_status()
        assert isinstance(result, dict)
        assert "anthropic" in result
        assert "stripe" in result

    def test_fetch_framework_updates_returns_list(self):
        result = fetch_framework_updates()
        assert isinstance(result, list)
        assert len(result) == 4

    def test_get_all_intelligence_returns_dict(self):
        with mock.patch("agents.shared.intelligence.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            result = get_all_intelligence()
        assert isinstance(result, dict)
        assert "advisories" in result
        assert "api_status" in result
        assert "framework_updates" in result

    def test_cache_prevents_refetch(self):
        """Once fetched, cache should prevent re-execution."""
        fetch_api_status()  # first call — writes cache
        # Verify cache file exists
        assert _intel_cache.exists()
        # Second call should use cache
        result = fetch_api_status()
        assert "anthropic" in result


# ===========================================================================
# TestExternalIntelligence
# ===========================================================================


class TestExternalIntelligence:
    """Test ExternalIntelligence class methods."""

    def _make_ei(self) -> ExternalIntelligence:
        return ExternalIntelligence()

    def _add_sample_items(self, ei: ExternalIntelligence) -> list[str]:
        """Add sample items and return their IDs."""
        items = [
            IntelligenceItem(
                id="item-1",
                category="python_advisories",
                title="CVE in requests",
                severity="critical",
                relevant_agents=["deps_manager", "security"],
            ),
            IntelligenceItem(
                id="item-2",
                category="testing_patterns",
                title="New pytest plugin",
                severity="info",
                relevant_agents=["test_engineer"],
            ),
            IntelligenceItem(
                id="item-3",
                category="performance_patterns",
                title="SQLAlchemy batch optimization",
                severity="medium",
                relevant_agents=["perf_monitor"],
            ),
            IntelligenceItem(
                id="item-4",
                category="security_best_practices",
                title="OWASP Top 10 update",
                severity="high",
                relevant_agents=["security", "privy"],
            ),
        ]
        for item in items:
            ei.add_item(item)
        return [i.id for i in items]

    def test_add_and_fetch_all(self):
        ei = self._make_ei()
        self._add_sample_items(ei)
        all_items = ei.fetch_all()
        total = sum(len(v) for v in all_items.values())
        assert total == 4

    def test_fetch_category(self):
        ei = self._make_ei()
        self._add_sample_items(ei)
        items = ei.fetch_category("python_advisories")
        assert len(items) == 1
        assert items[0].title == "CVE in requests"

    def test_fetch_category_empty(self):
        ei = self._make_ei()
        items = ei.fetch_category("nonexistent")
        assert items == []

    def test_get_for_agent(self):
        ei = self._make_ei()
        self._add_sample_items(ei)

        deps_items = ei.get_for_agent("deps_manager")
        assert len(deps_items) == 1  # item-1

        security_items = ei.get_for_agent("security")
        assert len(security_items) == 2  # item-1 and item-4

        test_items = ei.get_for_agent("test_engineer")
        assert len(test_items) == 1  # item-2

    def test_get_for_agent_no_matches(self):
        ei = self._make_ei()
        self._add_sample_items(ei)
        items = ei.get_for_agent("doc_keeper")
        assert items == []

    def test_get_urgent(self):
        ei = self._make_ei()
        self._add_sample_items(ei)
        urgent = ei.get_urgent()
        assert len(urgent) == 2  # critical + high
        severities = {u.severity for u in urgent}
        assert severities == {"critical", "high"}

    def test_get_unadopted(self):
        ei = self._make_ei()
        self._add_sample_items(ei)
        unadopted = ei.get_unadopted()
        assert len(unadopted) == 4  # none adopted yet

    def test_mark_adopted(self):
        ei = self._make_ei()
        ids = self._add_sample_items(ei)

        assert ei.mark_adopted("item-1", "deps_manager") is True
        # Reload to verify persistence
        ei2 = ExternalIntelligence()
        unadopted = ei2.get_unadopted()
        assert len(unadopted) == 3

    def test_mark_adopted_nonexistent(self):
        ei = self._make_ei()
        assert ei.mark_adopted("nonexistent", "security") is False

    def test_check_freshness_all_stale(self):
        ei = self._make_ei()
        freshness = ei.check_freshness()
        assert len(freshness) == 13
        # All should be stale since cache is empty
        assert all(v is False for v in freshness.values())

    def test_check_freshness_with_cached_data(self):
        # Pre-populate cache with fresh data
        cache = {
            "python_advisories": {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "data": [],
            }
        }
        _save_cache(cache)

        ei = ExternalIntelligence()
        freshness = ei.check_freshness()
        assert freshness["python_advisories"] is True

    def test_generate_research_agenda(self):
        ei = self._make_ei()
        agenda = ei.generate_research_agenda()
        assert len(agenda) == 13  # all stale → all in agenda
        # High priority items should come first
        assert agenda[0]["priority"] == "high"

    def test_generate_research_agenda_with_fresh(self):
        # Pre-populate one category as fresh
        cache = {
            "python_advisories": {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "data": [],
            }
        }
        _save_cache(cache)

        ei = ExternalIntelligence()
        agenda = ei.generate_research_agenda()
        categories = [a["category"] for a in agenda]
        assert "python_advisories" not in categories
        assert len(agenda) == 12

    def test_items_capped_at_200(self):
        ei = self._make_ei()
        for i in range(210):
            ei.add_item(IntelligenceItem(id=f"item-{i}", category="test"))
        # Reload
        ei2 = ExternalIntelligence()
        all_items = ei2.fetch_all()
        total = sum(len(v) for v in all_items.values())
        assert total == 200


# ===========================================================================
# TestGetAgentIntel
# ===========================================================================


class TestGetAgentIntel:
    """Test convenience function."""

    def test_returns_list(self):
        result = get_agent_intel("architect")
        assert isinstance(result, list)

    def test_returns_relevant_items(self):
        ei = ExternalIntelligence()
        ei.add_item(
            IntelligenceItem(
                id="conv-1",
                category="ai_sdk_updates",
                relevant_agents=["architect"],
            )
        )
        result = get_agent_intel("architect")
        assert len(result) == 1
        assert result[0].id == "conv-1"


# ===========================================================================
# TestStalenessCheck
# ===========================================================================


class TestStalenessCheck:
    """Test _is_stale with custom TTL."""

    def test_stale_when_no_entry(self):
        assert _is_stale({}, "missing_key") is True

    def test_stale_when_old(self):
        old_time = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
        cache = {"test_key": {"fetched_at": old_time}}
        assert _is_stale(cache, "test_key", ttl_hours=24) is True

    def test_fresh_when_recent(self):
        recent = datetime.now(timezone.utc).isoformat()
        cache = {"test_key": {"fetched_at": recent}}
        assert _is_stale(cache, "test_key", ttl_hours=24) is False

    def test_stale_with_custom_ttl(self):
        two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        cache = {"test_key": {"fetched_at": two_hours_ago}}
        assert _is_stale(cache, "test_key", ttl_hours=1) is True
        assert _is_stale(cache, "test_key", ttl_hours=3) is False
