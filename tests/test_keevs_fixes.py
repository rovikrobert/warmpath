"""Tests verifying Keevs review fixes (dead links, edge cases, session tracking)."""

from ops_team.keevs.coach_service import (
    STAGE_ACTIVE_SEARCH,
    STAGE_NETWORK_BUILDING,
    STAGE_STALLED,
    _determine_coaching_stage,
    _mock_briefing,
    get_suggested_prompts,
)


# ---------------------------------------------------------------------------
# Dead link fixes
# ---------------------------------------------------------------------------


class TestPreferencesLinkCorrected:
    def test_mock_briefing_no_preferences_link(self):
        """All /preferences links should be /settings?tab=profile."""
        ctx = {
            "user": {"name": "Test User"},
            "preferences": None,
            "network": {"total_contacts": 5, "top_companies": []},
            "pipeline": {"status_counts": {}, "follow_ups_needed": 0, "total": 0},
            "recent_searches": [],
            "credits": 0,
            "market": None,
        }
        result = _mock_briefing(ctx, session_number=2, stage=STAGE_NETWORK_BUILDING)
        assert "/preferences" not in result
        assert "/settings?tab=profile" in result

    def test_mock_briefing_late_session_no_preferences_link(self):
        ctx = {
            "user": {"name": "Test User"},
            "preferences": None,
            "network": {"total_contacts": 5, "top_companies": []},
            "pipeline": {"status_counts": {}, "follow_ups_needed": 0, "total": 0},
            "recent_searches": [],
            "credits": 0,
            "market": None,
        }
        result = _mock_briefing(ctx, session_number=5, stage=STAGE_STALLED)
        assert "/preferences" not in result


# ---------------------------------------------------------------------------
# Stage transitions
# ---------------------------------------------------------------------------


class TestNetworkBuildingTransitionsToStalled:
    def test_no_prefs_no_apps_no_searches_is_stalled(self):
        ctx = {
            "network": {"total_contacts": 10},
            "preferences": None,
            "pipeline": {"total": 0},
            "recent_searches": [],
        }
        assert _determine_coaching_stage(ctx) == STAGE_STALLED

    def test_no_prefs_with_apps_is_network_building(self):
        ctx = {
            "network": {"total_contacts": 10},
            "preferences": None,
            "pipeline": {"total": 2},
            "recent_searches": [],
        }
        assert _determine_coaching_stage(ctx) == STAGE_NETWORK_BUILDING

    def test_no_prefs_with_searches_is_network_building(self):
        ctx = {
            "network": {"total_contacts": 10},
            "preferences": None,
            "pipeline": {"total": 0},
            "recent_searches": [{"query": "Google"}],
        }
        assert _determine_coaching_stage(ctx) == STAGE_NETWORK_BUILDING


# ---------------------------------------------------------------------------
# Stage-aware greetings
# ---------------------------------------------------------------------------


class TestStalledGreetingNotMomentum:
    def test_stalled_session_3_says_get_things_moving(self):
        ctx = {
            "user": {"name": "Test User"},
            "preferences": None,
            "network": {"total_contacts": 5, "top_companies": []},
            "pipeline": {"status_counts": {}, "follow_ups_needed": 0, "total": 0},
            "recent_searches": [],
            "credits": 0,
            "market": None,
        }
        result = _mock_briefing(ctx, session_number=4, stage=STAGE_STALLED)
        assert "get things moving" in result
        assert "building momentum" not in result

    def test_active_search_session_4_says_momentum(self):
        ctx = {
            "user": {"name": "Test User"},
            "preferences": {"target_role": "SWE"},
            "network": {
                "total_contacts": 50,
                "top_companies": [{"company": "Google", "count": 10}],
            },
            "pipeline": {
                "status_counts": {"message_sent": 2},
                "follow_ups_needed": 0,
                "total": 2,
            },
            "recent_searches": [{"query": "Google"}],
            "credits": 100,
            "market": None,
        }
        result = _mock_briefing(ctx, session_number=4, stage=STAGE_ACTIVE_SEARCH)
        assert "building momentum" in result


# ---------------------------------------------------------------------------
# All-rejected pipeline empathy
# ---------------------------------------------------------------------------


class TestAllRejectedPipelineEmpathy:
    def test_all_rejected_shows_encouragement(self):
        ctx = {
            "user": {"name": "Test User"},
            "preferences": {"target_role": "SWE"},
            "network": {"total_contacts": 50, "top_companies": []},
            "pipeline": {
                "status_counts": {"rejected": 5},
                "follow_ups_needed": 0,
                "total": 5,
            },
            "recent_searches": [{"query": "test"}],
            "credits": 100,
            "market": None,
        }
        result = _mock_briefing(ctx, session_number=3, stage=STAGE_ACTIVE_SEARCH)
        assert "Every" in result and "no" in result.lower()
        assert "0 active" not in result


# ---------------------------------------------------------------------------
# Follow-up urgency
# ---------------------------------------------------------------------------


class TestFollowUpUrgency:
    def test_three_or_more_followups_shows_urgent(self):
        ctx = {
            "user": {"name": "Test User"},
            "preferences": {"target_role": "SWE"},
            "network": {"total_contacts": 50, "top_companies": []},
            "pipeline": {
                "status_counts": {"message_sent": 3},
                "follow_ups_needed": 3,
                "total": 3,
            },
            "recent_searches": [{"query": "test"}],
            "credits": 100,
            "market": None,
        }
        result = _mock_briefing(ctx, session_number=3, stage=STAGE_ACTIVE_SEARCH)
        assert "Urgent" in result

    def test_one_followup_no_urgent(self):
        ctx = {
            "user": {"name": "Test User"},
            "preferences": {"target_role": "SWE"},
            "network": {"total_contacts": 50, "top_companies": []},
            "pipeline": {
                "status_counts": {"message_sent": 1},
                "follow_ups_needed": 1,
                "total": 1,
            },
            "recent_searches": [{"query": "test"}],
            "credits": 100,
            "market": None,
        }
        result = _mock_briefing(ctx, session_number=3, stage=STAGE_ACTIVE_SEARCH)
        assert "Urgent" not in result
        assert "follow-up" in result.lower()


# ---------------------------------------------------------------------------
# Suggested prompt dedup
# ---------------------------------------------------------------------------


class TestSuggestedPromptNoDuplicateFocus:
    def test_no_duplicate_focus_prompt(self):
        ctx = {
            "network": {"total_contacts": 0, "top_companies": []},
            "preferences": None,
            "pipeline": {"total": 0, "follow_ups_needed": 0},
            "recent_searches": [],
            "credits": 0,
        }
        prompts = get_suggested_prompts(ctx)
        focus_count = sum(1 for p in prompts if p == "What should I focus on today?")
        assert focus_count <= 1


# ---------------------------------------------------------------------------
# Gate market prompt behind contacts
# ---------------------------------------------------------------------------


class TestMarketPromptGatedBehindContacts:
    def test_no_contacts_no_market_prompt(self):
        ctx = {
            "network": {"total_contacts": 0, "top_companies": []},
            "preferences": {"target_role": "SWE"},
            "pipeline": {"total": 0, "follow_ups_needed": 0},
            "recent_searches": [],
            "credits": 0,
        }
        prompts = get_suggested_prompts(ctx)
        assert not any("market" in p.lower() for p in prompts)

    def test_with_contacts_has_market_prompt(self):
        ctx = {
            "network": {
                "total_contacts": 50,
                "top_companies": [{"company": "Google", "count": 10}],
            },
            "preferences": {"target_role": "SWE"},
            "pipeline": {"total": 0, "follow_ups_needed": 0},
            "recent_searches": [],
            "credits": 0,
        }
        prompts = get_suggested_prompts(ctx)
        assert any("market" in p.lower() for p in prompts)


# ---------------------------------------------------------------------------
# Stalled escalation tiers
# ---------------------------------------------------------------------------


class TestStalledEscalation:
    def _stalled_ctx(self):
        return {
            "user": {"name": "Test User"},
            "preferences": None,
            "network": {"total_contacts": 5, "top_companies": []},
            "pipeline": {"status_counts": {}, "follow_ups_needed": 0, "total": 0},
            "recent_searches": [],
            "credits": 0,
            "market": None,
        }

    def test_session_5_gentle_nudge(self):
        result = _mock_briefing(
            self._stalled_ctx(), session_number=5, stage=STAGE_STALLED
        )
        assert "slowed down" in result

    def test_session_7_marketplace_nudge(self):
        result = _mock_briefing(
            self._stalled_ctx(), session_number=7, stage=STAGE_STALLED
        )
        assert "marketplace" in result.lower() or "browsing" in result.lower()

    def test_session_10_trajectory_nudge(self):
        result = _mock_briefing(
            self._stalled_ctx(), session_number=10, stage=STAGE_STALLED
        )
        assert "trajectory" in result.lower() or "warm intro" in result.lower()
