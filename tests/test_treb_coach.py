"""Tests for Treb AI Network Partner service and persona routing."""

from unittest.mock import MagicMock

import pytest_asyncio
from httpx import AsyncClient

from ops_team.treb.treb_coach_service import (
    NH_STAGE_ACTIVE_SHARING,
    NH_STAGE_ONBOARDING,
    NH_STAGE_PASSIVE,
    _determine_nh_stage,
    _detect_nh_topic,
    _mock_nh_briefing,
    _mock_nh_chat_response,
    get_nh_suggested_prompts,
    is_nh_topic,
)
from tests.conftest import TestSessionLocal, create_test_user_in_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def nh_auth_headers(client: AsyncClient) -> dict:
    """Create a test user with sha[RESEND_KEY_REDACTED] intent and return auth headers."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="treb@test.com", full_name="Treb Tester"
        )
    return headers


# ---------------------------------------------------------------------------
# is_nh_topic
# ---------------------------------------------------------------------------


class TestIsNhTopic:
    def test_sharing_network(self):
        assert is_nh_topic("How do I share my network?") is True

    def test_intro_request(self):
        assert is_nh_topic("Show me pending intro request") is True

    def test_referral_bonus(self):
        assert is_nh_topic("How much are referral bonuses worth?") is True

    def test_connector_reputation(self):
        assert is_nh_topic("What's my connector reputation?") is True

    def test_privacy_controls(self):
        assert is_nh_topic("How do I change privacy settings?") is True

    def test_job_search_not_nh(self):
        assert is_nh_topic("Help me find a job at Google") is False

    def test_application_not_nh(self):
        assert is_nh_topic("How is my pipeline looking?") is False

    def test_marketplace_listing(self):
        assert is_nh_topic("How do I see marketplace listings?") is True

    def test_opt_in(self):
        assert is_nh_topic("How do I opt-in to sharing?") is True

    def test_who_requested(self):
        assert is_nh_topic("Who requested an intro?") is True


# ---------------------------------------------------------------------------
# _determine_nh_stage
# ---------------------------------------------------------------------------


class TestDetermineNhStage:
    def test_no_contacts_returns_onboarding(self):
        ctx = {"total_contacts": 0, "listings": {"total": 0}, "intros": {}}
        assert _determine_nh_stage(ctx) == NH_STAGE_ONBOARDING

    def test_contacts_no_listings_returns_passive(self):
        ctx = {
            "total_contacts": 50,
            "listings": {"total": 0, "is_available": 0},
            "intros": {},
            "sharing_preferences": None,
        }
        assert _determine_nh_stage(ctx) == NH_STAGE_PASSIVE

    def test_active_listings_returns_active_sharing(self):
        ctx = {
            "total_contacts": 50,
            "listings": {"total": 10, "is_available": 5},
            "intros": {"pending": 0, "approved": 1},
            "sharing_prefs": {"opt_in_marketplace": True},
        }
        assert _determine_nh_stage(ctx) == NH_STAGE_ACTIVE_SHARING


# ---------------------------------------------------------------------------
# _detect_nh_topic
# ---------------------------------------------------------------------------


class TestDetectNhTopic:
    def test_sharing_topic(self):
        assert _detect_nh_topic("How do I share my contacts?") == "sharing"

    def test_intros_topic(self):
        assert _detect_nh_topic("Show me pending intro requests") == "intros"

    def test_reputation_topic(self):
        assert _detect_nh_topic("What is my connector reputation?") == "reputation"

    def test_credits_topic(self):
        assert _detect_nh_topic("How many credits have I earned?") == "credits"

    def test_privacy_topic(self):
        assert (
            _detect_nh_topic("How do I change my privacy settings?")
            == "privacy_controls"
        )

    def test_unknown_returns_none(self):
        assert _detect_nh_topic("Tell me a joke") is None


# ---------------------------------------------------------------------------
# _mock_nh_briefing
# ---------------------------------------------------------------------------


class TestMockNhBriefing:
    def _base_context(self):
        return {
            "user": {"name": "Alex Chen", "title": "SWE", "company": "Google"},
            "total_contacts": 100,
            "enrichment_coverage": 45.0,
            "listings": {"total": 20, "is_available": 15},
            "intros": {"pending": 2, "approved": 3, "declined": 0, "completed": 1},
            "connector_profile": {
                "intros_facilitated": 4,
                "response_rate": 0.9,
                "avg_rating": 4.5,
            },
            "sharing_preferences": {
                "opt_in": True,
                "paused": False,
                "excluded_count": 5,
            },
            "credits": 150,
        }

    def test_session_1_welcome(self):
        ctx = self._base_context()
        result = _mock_nh_briefing(ctx, session_number=1, stage=NH_STAGE_ONBOARDING)
        assert "Welcome" in result
        assert "Treb" in result

    def test_session_2_returning(self):
        ctx = self._base_context()
        result = _mock_nh_briefing(ctx, session_number=2, stage=NH_STAGE_ACTIVE_SHARING)
        assert "again" in result.lower() or "back" in result.lower()

    def test_active_sharing_mentions_listings(self):
        ctx = self._base_context()
        result = _mock_nh_briefing(ctx, session_number=3, stage=NH_STAGE_ACTIVE_SHARING)
        assert (
            "listing" in result.lower()
            or "shared" in result.lower()
            or "intro" in result.lower()
        )

    def test_pending_intros_mentioned(self):
        ctx = self._base_context()
        ctx["intros"]["pending"] = 3
        result = _mock_nh_briefing(ctx, session_number=3, stage=NH_STAGE_ACTIVE_SHARING)
        assert "pending" in result.lower() or "intro" in result.lower() or "3" in result


# ---------------------------------------------------------------------------
# _mock_nh_chat_response
# ---------------------------------------------------------------------------


class TestMockNhChatResponse:
    def _base_context(self):
        return {
            "user": {"name": "Alex Chen"},
            "total_contacts": 100,
            "enrichment_coverage": 45.0,
            "listings": {"total": 20, "is_available": 15},
            "intros": {"pending": 2, "approved": 3, "declined": 0, "completed": 1},
            "connector_profile": {
                "intros_facilitated": 4,
                "response_rate": 0.9,
                "avg_rating": 4.5,
            },
            "sharing_preferences": {
                "opt_in": True,
                "paused": False,
                "excluded_count": 5,
            },
            "credits": 150,
        }

    def test_sharing_response(self):
        response, topic = _mock_nh_chat_response(
            "How do I share my network?", self._base_context()
        )
        assert topic == "sharing"
        assert len(response) > 20

    def test_intros_response(self):
        response, topic = _mock_nh_chat_response(
            "Show pending intro requests", self._base_context()
        )
        assert topic == "intros"
        assert "intro" in response.lower() or "pending" in response.lower()

    def test_reputation_response(self):
        response, topic = _mock_nh_chat_response(
            "What is my connector reputation?", self._base_context()
        )
        assert topic == "reputation"

    def test_credits_response(self):
        response, topic = _mock_nh_chat_response(
            "How many credits?", self._base_context()
        )
        assert topic == "credits"


# ---------------------------------------------------------------------------
# get_nh_suggested_prompts
# ---------------------------------------------------------------------------


class TestNhSuggestedPrompts:
    def test_no_listings_suggests_sharing(self):
        ctx = {
            "total_contacts": 50,
            "listings": {"total": 0, "is_available": 0},
            "intros": {},
            "connector_profile": None,
        }
        prompts = get_nh_suggested_prompts(ctx)
        assert any("share" in p.lower() or "sharing" in p.lower() for p in prompts)

    def test_pending_intros_suggests_review(self):
        ctx = {
            "total_contacts": 50,
            "listings": {"total": 10, "is_available": 5},
            "intros": {"pending": 3},
            "connector_profile": {"intros_facilitated": 1},
        }
        prompts = get_nh_suggested_prompts(ctx)
        assert any("intro" in p.lower() or "pending" in p.lower() for p in prompts)

    def test_always_includes_referral_bonus(self):
        ctx = {
            "total_contacts": 50,
            "listings": {"total": 10, "is_available": 5},
            "intros": {},
            "connector_profile": None,
        }
        prompts = get_nh_suggested_prompts(ctx)
        assert any("referral" in p.lower() or "bonus" in p.lower() for p in prompts)


# ---------------------------------------------------------------------------
# Persona routing (unit tests — no DB needed)
# ---------------------------------------------------------------------------


class TestPersonaRouting:
    def test_find_referrals_returns_keevs(self):
        from app.api.coach import _resolve_persona

        user = MagicMock()
        user.intent = "find_referrals"
        assert _resolve_persona(user) == "keevs"

    def test_sha[RESEND_KEY_REDACTED](self):
        from app.api.coach import _resolve_persona

        user = MagicMock()
        user.intent = "sha[RESEND_KEY_REDACTED]"
        assert _resolve_persona(user) == "treb"

    def test_explo[RESEND_KEY_REDACTED](self):
        from app.api.coach import _resolve_persona

        user = MagicMock()
        user.intent = "explore"
        assert _resolve_persona(user, "Help me find a job") == "keevs"

    def test_explo[RESEND_KEY_REDACTED](self):
        from app.api.coach import _resolve_persona

        user = MagicMock()
        user.intent = "explore"
        assert _resolve_persona(user, "How do I share my network?") == "treb"

    def test_null_intent_returns_keevs(self):
        from app.api.coach import _resolve_persona

        user = MagicMock()
        user.intent = None
        assert _resolve_persona(user) == "keevs"

    def test_null_intent_nh_topic_returns_treb(self):
        from app.api.coach import _resolve_persona

        user = MagicMock()
        user.intent = None
        assert (
            _resolve_persona(user, "how do i decide who to give my referrals to")
            == "treb"
        )

    def test_give_referrals_detected_as_nh_topic(self):
        assert is_nh_topic("how do i decide who to give my referrals to") is True

    def test_refer_someone_detected_as_nh_topic(self):
        assert is_nh_topic("should I refer someone from my team?") is True

    def test_facilitate_intro_detected_as_nh_topic(self):
        assert is_nh_topic("how do I facilitate an intro?") is True

    def test_making_referral_detected_as_nh_topic(self):
        assert is_nh_topic("tips for making a good referral") is True
