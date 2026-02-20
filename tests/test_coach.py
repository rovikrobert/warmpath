"""Tests for Keevs AI Job Coach endpoints and service logic."""

import uuid as uuid_mod
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from httpx import AsyncClient

from ops_team.keevs.coach_service import (
    STAGE_ACTIVE_SEARCH,
    STAGE_NETWORK_BUILDING,
    STAGE_ONBOARDING,
    STAGE_STALLED,
    _assemble_context,
    _build_chat_messages,
    _detect_topic,
    _determine_coaching_stage,
    _mock_briefing,
    _mock_chat_response,
)
from tests.conftest import TestSessionLocal, create_test_user_in_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    """Create a test user and return auth headers."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="keevs@test.com", full_name="Keevs Tester"
        )
    return headers


@pytest_asyncio.fixture
async def user_with_data(auth_headers: dict, client: AsyncClient) -> dict:
    """Create contacts, preferences, and an application."""
    # Contacts
    contacts_data = [
        {
            "first_name": "Alice",
            "last_name": "Eng",
            "company": "Google",
            "position": "SWE",
        },
        {"first_name": "Bob", "last_name": "PM", "company": "Stripe", "position": "PM"},
        {
            "first_name": "Carol",
            "last_name": "DS",
            "company": "Stripe",
            "position": "Data Scientist",
        },
    ]
    await client.post(
        "/api/v1/contacts/manual/bulk",
        headers=auth_headers,
        json={"contacts": contacts_data},
    )
    # Preferences
    await client.put(
        "/api/v1/preferences/job",
        headers=auth_headers,
        json={
            "target_role": "Software Engineer",
            "target_seniority": "Senior",
            "target_locations": ["Singapore"],
        },
    )
    # Application
    await client.post(
        "/api/v1/applications",
        headers=auth_headers,
        json={"company_name": "Stripe", "role_title": "SWE", "status": "message_sent"},
    )
    return auth_headers


# ---------------------------------------------------------------------------
# TestCoachBriefingEndpoint
# ---------------------------------------------------------------------------


class TestCoachBriefingEndpoint:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/coach/briefing")
        assert resp.status_code in (401, 403)

    async def test_returns_briefing(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/coach/briefing", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data["briefing"], str)
        assert len(data["briefing"]) > 0

    async def test_response_envelope(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/coach/briefing", headers=auth_headers)
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        data = body["data"]
        assert "briefing" in data
        assert "context_snapshot" in data
        assert "suggested_prompts" in data
        assert "generated_at" in data

    async def test_context_snapshot_keys(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/coach/briefing", headers=auth_headers)
        ctx = resp.json()["data"]["context_snapshot"]
        assert "user" in ctx
        assert "preferences" in ctx
        assert "network" in ctx
        assert "pipeline" in ctx
        assert "credits" in ctx
        assert "market" in ctx
        assert "recent_searches" in ctx

    async def test_briefing_cached(self, client: AsyncClient, auth_headers: dict):
        """Second call uses cache — _assemble_context called only once."""
        with patch(
            "ops_team.keevs.coach_service._assemble_context",
            new_callable=AsyncMock,
            return_value={
                "user": {
                    "name": "Cache Test",
                    "title": None,
                    "company": None,
                    "location": None,
                },
                "preferences": None,
                "network": None,
                "pipeline": {"status_counts": {}, "follow_ups_needed": 0, "total": 0},
                "recent_searches": [],
                "credits": 0,
                "market": None,
            },
        ) as mock_ctx:
            resp1 = await client.get("/api/v1/coach/briefing", headers=auth_headers)
            assert resp1.status_code == 200

            resp2 = await client.get("/api/v1/coach/briefing", headers=auth_headers)
            assert resp2.status_code == 200

            assert mock_ctx.call_count == 1

    async def test_briefing_with_data(self, client: AsyncClient, user_with_data: dict):
        resp = await client.get("/api/v1/coach/briefing", headers=user_with_data)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["briefing"]) > 20
        # Should reference the user's name
        assert "Keevs" in data["briefing"]

    async def test_suggested_prompts_returned(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.get("/api/v1/coach/briefing", headers=auth_headers)
        prompts = resp.json()["data"]["suggested_prompts"]
        assert isinstance(prompts, list)
        assert len(prompts) >= 1


# ---------------------------------------------------------------------------
# TestCoachChatEndpoint
# ---------------------------------------------------------------------------


class TestCoachChatEndpoint:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/coach/chat",
            json={"message": "hello"},
        )
        assert resp.status_code in (401, 403)

    async def test_returns_response(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            "/api/v1/coach/chat",
            headers=auth_headers,
            json={"message": "What should I focus on today?"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data["response"], str)
        assert len(data["response"]) > 0

    async def test_chat_uses_context(self, client: AsyncClient, auth_headers: dict):
        """Passing context_snapshot still returns a valid response."""
        resp = await client.post(
            "/api/v1/coach/chat",
            headers=auth_headers,
            json={
                "message": "Tell me about my network",
                "context_snapshot": {
                    "user": {
                        "name": "Test",
                        "title": None,
                        "company": None,
                        "location": None,
                    },
                    "preferences": None,
                    "network": {
                        "total_contacts": 42,
                        "top_companies": [{"company": "Google", "count": 10}],
                        "summary": "42 contacts",
                    },
                    "pipeline": {
                        "status_counts": {},
                        "follow_ups_needed": 0,
                        "total": 0,
                    },
                    "recent_searches": [],
                    "credits": 100,
                    "market": None,
                },
            },
        )
        assert resp.status_code == 200
        response_text = resp.json()["data"]["response"]
        # Mock should reference network data
        assert "42" in response_text or "network" in response_text.lower()

    async def test_chat_with_history(self, client: AsyncClient, auth_headers: dict):
        """Conversation history is accepted."""
        resp = await client.post(
            "/api/v1/coach/chat",
            headers=auth_headers,
            json={
                "message": "Thanks, what else?",
                "conversation_history": [
                    {"role": "keevs", "content": "Here's your briefing."},
                    {"role": "user", "content": "Tell me about credits"},
                    {"role": "keevs", "content": "You have 50 credits."},
                ],
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["response"]


# ---------------------------------------------------------------------------
# TestContextAssembly
# ---------------------------------------------------------------------------


class TestContextAssembly:
    async def test_context_shape(self, client: AsyncClient, auth_headers: dict):
        """Verify all keys are present in assembled context."""
        me_resp = await client.get("/api/v1/auth/me", headers=auth_headers)
        user_id = uuid_mod.UUID(me_resp.json()["data"]["id"])

        async with TestSessionLocal() as db:
            ctx = await _assemble_context(user_id, db)

        assert "user" in ctx
        assert "preferences" in ctx
        assert "network" in ctx
        assert "pipeline" in ctx
        assert "recent_searches" in ctx
        assert "credits" in ctx
        assert "market" in ctx
        assert ctx["user"]["name"] == "Keevs Tester"

    async def test_context_with_applications(
        self, client: AsyncClient, user_with_data: dict
    ):
        """Context includes pipeline data from applications."""
        me_resp = await client.get("/api/v1/auth/me", headers=user_with_data)
        user_id = uuid_mod.UUID(me_resp.json()["data"]["id"])

        async with TestSessionLocal() as db:
            ctx = await _assemble_context(user_id, db)

        assert ctx["pipeline"]["total"] >= 1
        assert len(ctx["pipeline"]["status_counts"]) >= 1


# ---------------------------------------------------------------------------
# TestMockResponses
# ---------------------------------------------------------------------------


class TestMockResponses:
    def test_mock_briefing_includes_name(self):
        context = {
            "user": {
                "name": "Alice Smith",
                "title": None,
                "company": None,
                "location": None,
            },
            "preferences": None,
            "network": None,
            "pipeline": {"status_counts": {}, "follow_ups_needed": 0, "total": 0},
            "recent_searches": [],
            "credits": 0,
            "market": None,
        }
        briefing = _mock_briefing(context)
        assert "Alice" in briefing

    def test_mock_briefing_with_follow_ups(self):
        context = {
            "user": {"name": "Bob", "title": None, "company": None, "location": None},
            "preferences": None,
            "network": None,
            "pipeline": {
                "status_counts": {"message_sent": 2},
                "follow_ups_needed": 2,
                "total": 2,
            },
            "recent_searches": [],
            "credits": 0,
            "market": None,
        }
        briefing = _mock_briefing(context)
        assert "2" in briefing
        assert "follow-up" in briefing.lower()

    def test_mock_chat_response_network(self):
        context = {
            "user": {"name": "Test", "title": None, "company": None, "location": None},
            "preferences": None,
            "network": {
                "total_contacts": 50,
                "top_companies": [{"company": "Google", "count": 10}],
            },
            "pipeline": {"status_counts": {}, "follow_ups_needed": 0, "total": 0},
            "recent_searches": [],
            "credits": 0,
            "market": None,
        }
        response_text, topic = _mock_chat_response("Tell me about my network", context)
        assert "50" in response_text
        assert "Google" in response_text
        assert topic == "network"

    def test_build_chat_messages_structure(self):
        context = {
            "user": {"name": "Test"},
            "preferences": None,
        }
        history = [
            {"role": "user", "content": "Hi"},
            {"role": "keevs", "content": "Hello!"},
        ]
        messages = _build_chat_messages("New question", history, context)
        # Context injection pair + 2 history + 1 current = 5 messages
        assert len(messages) == 5
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert messages[-1]["content"] == "New question"


# ---------------------------------------------------------------------------
# TestCoachChatStreamEndpoint
# ---------------------------------------------------------------------------


class TestCoachChatStreamEndpoint:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/coach/chat/stream",
            json={"message": "hello"},
        )
        assert resp.status_code in (401, 403)

    async def test_stream_returns_sse(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            "/api/v1/coach/chat/stream",
            headers=auth_headers,
            json={"message": "What should I focus on?"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        body = resp.text
        assert "data: " in body
        assert "[DONE]" in body

    async def test_stream_contains_mock_response(
        self, client: AsyncClient, auth_headers: dict
    ):
        """SSE data events should contain the mock chat response text."""
        resp = await client.post(
            "/api/v1/coach/chat/stream",
            headers=auth_headers,
            json={"message": "How do I get started?"},
        )
        assert resp.status_code == 200
        # Mock response for "get started" should contain game plan text
        assert "game plan" in resp.text.lower() or "upload" in resp.text.lower()

    async def test_stream_ignores_client_context_snapshot(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Stream endpoint ignores client-supplied context_snapshot for security."""
        resp = await client.post(
            "/api/v1/coach/chat/stream",
            headers=auth_headers,
            json={
                "message": "Tell me about my credits",
                "context_snapshot": {
                    "user": {
                        "name": "Injected",
                        "title": None,
                        "company": None,
                        "location": None,
                    },
                    "preferences": None,
                    "network": None,
                    "pipeline": {
                        "status_counts": {},
                        "follow_ups_needed": 0,
                        "total": 0,
                    },
                    "recent_searches": [],
                    "credits": 75,
                    "market": None,
                },
            },
        )
        assert resp.status_code == 200
        # Server assembles its own context; user has 50 credits from signup bonus
        assert "credit" in resp.text.lower()


# ---------------------------------------------------------------------------
# TestCoachingStages (P1)
# ---------------------------------------------------------------------------


class TestCoachingStages:
    def _base_context(self, **overrides) -> dict:
        ctx = {
            "user": {"name": "Test", "title": None, "company": None, "location": None},
            "preferences": None,
            "network": None,
            "pipeline": {"status_counts": {}, "follow_ups_needed": 0, "total": 0},
            "recent_searches": [],
            "credits": 0,
            "market": None,
        }
        ctx.update(overrides)
        return ctx

    def test_onboarding_no_contacts(self):
        ctx = self._base_context()
        assert _determine_coaching_stage(ctx) == STAGE_ONBOARDING

    def test_network_building_has_contacts_no_prefs(self):
        ctx = self._base_context(
            network={"total_contacts": 50, "top_companies": []},
        )
        assert _determine_coaching_stage(ctx) == STAGE_NETWORK_BUILDING

    def test_stalled_has_contacts_prefs_but_no_activity(self):
        ctx = self._base_context(
            network={"total_contacts": 50, "top_companies": []},
            preferences={"target_role": "SWE"},
        )
        assert _determine_coaching_stage(ctx) == STAGE_STALLED

    def test_active_search(self):
        ctx = self._base_context(
            network={"total_contacts": 50, "top_companies": []},
            preferences={"target_role": "SWE"},
            pipeline={
                "status_counts": {"applied": 2},
                "follow_ups_needed": 0,
                "total": 2,
            },
        )
        assert _determine_coaching_stage(ctx) == STAGE_ACTIVE_SEARCH

    def test_active_search_via_recent_searches(self):
        ctx = self._base_context(
            network={"total_contacts": 50, "top_companies": []},
            preferences={"target_role": "SWE"},
            recent_searches=[{"name": "Google", "status": "completed"}],
        )
        assert _determine_coaching_stage(ctx) == STAGE_ACTIVE_SEARCH


# ---------------------------------------------------------------------------
# TestSessionBranching (P2)
# ---------------------------------------------------------------------------


class TestSessionBranching:
    def _base_context(self) -> dict:
        return {
            "user": {
                "name": "Alice Smith",
                "title": None,
                "company": None,
                "location": None,
            },
            "preferences": None,
            "network": None,
            "pipeline": {"status_counts": {}, "follow_ups_needed": 0, "total": 0},
            "recent_searches": [],
            "credits": 0,
            "market": None,
        }

    def test_session_1_welcome(self):
        briefing = _mock_briefing(self._base_context(), session_number=1)
        assert "Welcome" in briefing

    def test_session_2_returnee(self):
        briefing = _mock_briefing(self._base_context(), session_number=2)
        assert "again" in briefing.lower()

    def test_session_4_momentum(self):
        briefing = _mock_briefing(self._base_context(), session_number=4)
        assert "#4" in briefing

    def test_session_10_welcome_back(self):
        briefing = _mock_briefing(self._base_context(), session_number=10)
        assert "#10" in briefing


# ---------------------------------------------------------------------------
# TestDynamicBriefingSections (P3)
# ---------------------------------------------------------------------------


class TestDynamicBriefingSections:
    def test_onboarding_session1_shows_explanation(self):
        ctx = {
            "user": {
                "name": "New User",
                "title": None,
                "company": None,
                "location": None,
            },
            "preferences": None,
            "network": None,
            "pipeline": {"status_counts": {}, "follow_ups_needed": 0, "total": 0},
            "recent_searches": [],
            "credits": 0,
            "market": None,
        }
        briefing = _mock_briefing(ctx, session_number=1, stage=STAGE_ONBOARDING)
        assert "how warmpath works" in briefing.lower()

    def test_onboarding_late_session_nudge(self):
        ctx = {
            "user": {
                "name": "Lazy User",
                "title": None,
                "company": None,
                "location": None,
            },
            "preferences": None,
            "network": None,
            "pipeline": {"status_counts": {}, "follow_ups_needed": 0, "total": 0},
            "recent_searches": [],
            "credits": 0,
            "market": None,
        }
        briefing = _mock_briefing(ctx, session_number=5, stage=STAGE_ONBOARDING)
        assert "still haven't uploaded" in briefing.lower()

    def test_pipeline_shown_when_apps_exist(self):
        ctx = {
            "user": {
                "name": "Active User",
                "title": None,
                "company": None,
                "location": None,
            },
            "preferences": {"target_role": "SWE"},
            "network": {
                "total_contacts": 50,
                "top_companies": [{"company": "Google", "count": 10}],
            },
            "pipeline": {
                "status_counts": {"applied": 2, "message_sent": 1},
                "follow_ups_needed": 0,
                "total": 3,
            },
            "recent_searches": [],
            "credits": 100,
            "market": None,
        }
        briefing = _mock_briefing(ctx, session_number=3, stage=STAGE_ACTIVE_SEARCH)
        assert "active application" in briefing.lower()

    def test_stalled_user_gets_nudge(self):
        ctx = {
            "user": {
                "name": "Stalled User",
                "title": None,
                "company": None,
                "location": None,
            },
            "preferences": {"target_role": "PM"},
            "network": {"total_contacts": 100, "top_companies": []},
            "pipeline": {"status_counts": {}, "follow_ups_needed": 0, "total": 0},
            "recent_searches": [],
            "credits": 50,
            "market": None,
        }
        briefing = _mock_briefing(ctx, session_number=5, stage=STAGE_STALLED)
        assert "slowed down" in briefing.lower()

    def test_follow_ups_shown_when_due(self):
        ctx = {
            "user": {
                "name": "Busy User",
                "title": None,
                "company": None,
                "location": None,
            },
            "preferences": {"target_role": "SWE"},
            "network": None,
            "pipeline": {
                "status_counts": {"message_sent": 3},
                "follow_ups_needed": 3,
                "total": 3,
            },
            "recent_searches": [],
            "credits": 0,
            "market": None,
        }
        briefing = _mock_briefing(ctx, session_number=3, stage=STAGE_ACTIVE_SEARCH)
        assert "follow-up" in briefing.lower()
        assert "3" in briefing


# ---------------------------------------------------------------------------
# TestTopicDetection (P4)
# ---------------------------------------------------------------------------


class TestTopicDetection:
    def test_detects_follow_ups(self):
        assert _detect_topic("How should I follow up with Google?") == "follow_ups"

    def test_detects_network(self):
        assert _detect_topic("Tell me about my network") == "network"

    def test_detects_targeting(self):
        assert _detect_topic("Which companies should I target?") == "targeting"

    def test_detects_credits(self):
        assert _detect_topic("How do I use my credits?") == "credits"

    def test_detects_getting_started(self):
        assert _detect_topic("How do I get started?") == "getting_started"

    def test_detects_pipeline(self):
        assert _detect_topic("How's my pipeline looking?") == "pipeline"

    def test_returns_none_for_unknown(self):
        assert _detect_topic("What's the weather like?") is None


# ---------------------------------------------------------------------------
# TestAntiRepetition (P4)
# ---------------------------------------------------------------------------


class TestAntiRepetition:
    def _base_context(self) -> dict:
        return {
            "user": {"name": "Test", "title": None, "company": None, "location": None},
            "preferences": {"target_role": "SWE"},
            "network": {
                "total_contacts": 50,
                "top_companies": [{"company": "Google", "count": 10}],
            },
            "pipeline": {
                "status_counts": {"applied": 2},
                "follow_ups_needed": 1,
                "total": 2,
            },
            "recent_searches": [],
            "credits": 100,
            "market": None,
        }

    def test_fresh_topic_response(self):
        text, topic = _mock_chat_response(
            "Tell me about my network", self._base_context(), recent_topics=set()
        )
        assert "50" in text
        assert topic == "network"

    def test_repeated_topic_gives_varied_response(self):
        fresh_text, _ = _mock_chat_response(
            "Tell me about my network", self._base_context(), recent_topics=set()
        )
        varied_text, _ = _mock_chat_response(
            "Tell me about my network", self._base_context(), recent_topics={"network"}
        )
        # Responses should differ when topic was recently discussed
        assert fresh_text != varied_text

    def test_credits_anti_repetition(self):
        fresh, _ = _mock_chat_response(
            "How do I use credits?", self._base_context(), recent_topics=set()
        )
        varied, _ = _mock_chat_response(
            "How do I use credits?", self._base_context(), recent_topics={"credits"}
        )
        assert fresh != varied

    def test_targeting_anti_repetition(self):
        fresh, _ = _mock_chat_response(
            "Which companies should I target?",
            self._base_context(),
            recent_topics=set(),
        )
        varied, _ = _mock_chat_response(
            "Which companies should I target?",
            self._base_context(),
            recent_topics={"targeting"},
        )
        assert fresh != varied

    def test_follow_ups_anti_repetition(self):
        fresh, _ = _mock_chat_response(
            "What follow-ups do I have?", self._base_context(), recent_topics=set()
        )
        varied, _ = _mock_chat_response(
            "What follow-ups do I have?",
            self._base_context(),
            recent_topics={"follow_ups"},
        )
        assert fresh != varied

    def test_getting_started_anti_repetition(self):
        fresh, _ = _mock_chat_response(
            "How do I get started?", self._base_context(), recent_topics=set()
        )
        varied, _ = _mock_chat_response(
            "How do I get started?",
            self._base_context(),
            recent_topics={"getting_started"},
        )
        assert fresh != varied

    def test_pipeline_anti_repetition(self):
        fresh, _ = _mock_chat_response(
            "How's my pipeline?", self._base_context(), recent_topics=set()
        )
        varied, _ = _mock_chat_response(
            "How's my pipeline?", self._base_context(), recent_topics={"pipeline"}
        )
        assert fresh != varied

    def test_fallback_returns_none_topic(self):
        text, topic = _mock_chat_response("What's the weather?", self._base_context())
        assert topic is None
        assert len(text) > 20


# ---------------------------------------------------------------------------
# TestSessionTracking (integration)
# ---------------------------------------------------------------------------


class TestSessionTracking:
    async def test_briefing_includes_session_fields(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Briefing response should include session_number and coaching_stage."""
        resp = await client.get("/api/v1/coach/briefing", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "session_number" in data
        assert "coaching_stage" in data
        assert data["session_number"] >= 1
        assert data["coaching_stage"] in (
            STAGE_ONBOARDING,
            STAGE_NETWORK_BUILDING,
            STAGE_ACTIVE_SEARCH,
            STAGE_STALLED,
        )


# ---------------------------------------------------------------------------
# TestContactSearchDetection
# ---------------------------------------------------------------------------


class TestContactSearchDetection:
    """Test is_contact_search_query() pattern matching."""

    def test_who_do_i_know_at(self):
        from ops_team.keevs.coach_service import is_contact_search_query

        assert is_contact_search_query("who do I know at Google?") is True

    def test_contacts_at(self):
        from ops_team.keevs.coach_service import is_contact_search_query

        assert is_contact_search_query("my contacts at Stripe") is True

    def test_show_people(self):
        from ops_team.keevs.coach_service import is_contact_search_query

        assert is_contact_search_query("show me my connections at Meta") is True

    def test_anyone_at(self):
        from ops_team.keevs.coach_service import is_contact_search_query

        assert is_contact_search_query("anyone at Amazon?") is True

    def test_find_contacts(self):
        from ops_team.keevs.coach_service import is_contact_search_query

        assert is_contact_search_query("find contacts at Netflix") is True

    def test_search_network(self):
        from ops_team.keevs.coach_service import is_contact_search_query

        assert is_contact_search_query("search my network at Apple") is True

    def test_senior_engineers(self):
        from ops_team.keevs.coach_service import is_contact_search_query

        assert is_contact_search_query("senior engineers at Google") is True

    def test_company_contacts(self):
        from ops_team.keevs.coach_service import is_contact_search_query

        assert is_contact_search_query("Google contacts") is True

    def test_generic_question_not_detected(self):
        from ops_team.keevs.coach_service import is_contact_search_query

        assert is_contact_search_query("How's my pipeline looking?") is False

    def test_credits_question_not_detected(self):
        from ops_team.keevs.coach_service import is_contact_search_query

        assert is_contact_search_query("How many credits do I have?") is False

    def test_weather_not_detected(self):
        from ops_team.keevs.coach_service import is_contact_search_query

        assert is_contact_search_query("What's the weather like?") is False

    def test_reversed_order_who_have_at(self):
        from ops_team.keevs.coach_service import is_contact_search_query

        assert is_contact_search_query("who have I got at Stripe?") is True

    def test_detect_topic_returns_contact_search(self):
        assert _detect_topic("who do I know at Google?") == "contact_search"

    def test_detect_topic_contact_search_overrides_network(self):
        """Contact search should take priority over generic 'network' topic."""
        assert _detect_topic("show me my contacts at Stripe") == "contact_search"


# ---------------------------------------------------------------------------
# TestContactSearchMockFormatting
# ---------------------------------------------------------------------------


class TestContactSearchMockFormatting:
    """Test mock chat response formatting with contact results."""

    def _base_context(self) -> dict:
        return {
            "user": {"name": "Test", "title": None, "company": None, "location": None},
            "preferences": None,
            "network": {"total_contacts": 50, "top_companies": []},
            "pipeline": {"status_counts": {}, "follow_ups_needed": 0, "total": 0},
            "recent_searches": [],
            "credits": 0,
            "market": None,
        }

    def _sample_contact_results(self, count: int = 3) -> dict:
        results = []
        for i in range(count):
            results.append(
                {
                    "full_name": f"Contact {i}",
                    "current_company": "Google",
                    "current_title": f"Engineer L{i + 3}",
                    "warm_score": 80 - i * 10,
                    "nlp_match_score": 90 - i * 5,
                    "relationship_type": "former_colleague",
                    "location": "Singapore",
                }
            )
        return {
            "results": results,
            "interpretation": {"raw_query": "engineers at Google"},
            "total_scanned": 50,
            "total_matched": count,
        }

    def test_contact_names_appear_in_response(self):
        contact_results = self._sample_contact_results(3)
        text, topic = _mock_chat_response(
            "who do I know at Google?",
            self._base_context(),
            contact_results=contact_results,
        )
        assert "Contact 0" in text
        assert "Contact 1" in text
        assert "Contact 2" in text
        assert topic == "contact_search"

    def test_warm_sco[RESEND_KEY_REDACTED](self):
        contact_results = self._sample_contact_results(1)
        text, _ = _mock_chat_response(
            "who do I know at Google?",
            self._base_context(),
            contact_results=contact_results,
        )
        assert "warm score: 80" in text

    def test_caps_at_ten_results(self):
        from ops_team.keevs.coach_service import _format_contact_results_markdown

        contact_results = self._sample_contact_results(15)
        text = _format_contact_results_markdown(contact_results)
        # Should show overflow message
        assert "Showing 10 of 15" in text
        # Should not show all 15
        assert "Contact 14" not in text

    def test_overflow_text_when_mo[RESEND_KEY_REDACTED](self):
        from ops_team.keevs.coach_service import _format_contact_results_markdown

        contact_results = self._sample_contact_results(12)
        text = _format_contact_results_markdown(contact_results)
        assert "Showing 10 of 12" in text
        assert "/contacts" in text

    def test_no_overflow_when_within_limit(self):
        from ops_team.keevs.coach_service import _format_contact_results_markdown

        contact_results = self._sample_contact_results(5)
        text = _format_contact_results_markdown(contact_results)
        assert "Showing" not in text

    def test_zero_results_returns_helpful_message(self):
        from ops_team.keevs.coach_service import _format_contact_results_markdown

        contact_results = {
            "results": [],
            "interpretation": {"raw_query": "CTOs at Acme"},
            "total_scanned": 50,
            "total_matched": 0,
        }
        text = _format_contact_results_markdown(contact_results)
        assert "No contacts found" in text

    def test_referral_cta_in_response(self):
        contact_results = self._sample_contact_results(2)
        text, _ = _mock_chat_response(
            "who do I know at Google?",
            self._base_context(),
            contact_results=contact_results,
        )
        assert "referral message" in text.lower()

    def test_no_contact_results_falls_through_to_network(self):
        """When contact_results is None, contact_search remaps to network topic."""
        text, topic = _mock_chat_response(
            "who do I know at Google?",
            self._base_context(),
            contact_results=None,
        )
        # Should fall through to network handler
        assert topic == "network"
        assert len(text) > 0

    def test_build_chat_messages_includes_contact_results(self):
        context = {"user": {"name": "Test"}, "preferences": None}
        contact_results = self._sample_contact_results(2)
        messages = _build_chat_messages(
            "who do I know at Google?", [], context, contact_results
        )
        # Should have: context pair (2) + contact pair (2) + current msg (1) = 5
        assert len(messages) == 5
        # The contact injection message should mention "CONTACT SEARCH RESULTS"
        assert any("CONTACT SEARCH RESULTS" in m["content"] for m in messages)

    def test_build_chat_messages_without_contact_results(self):
        context = {"user": {"name": "Test"}, "preferences": None}
        messages = _build_chat_messages("hello", [], context, None)
        # Should have: context pair (2) + current msg (1) = 3
        assert len(messages) == 3


# ---------------------------------------------------------------------------
# TestCoachContactSearchIntegration
# ---------------------------------------------------------------------------


class TestCoachContactSearchIntegration:
    """Integration tests: POST /coach/chat with contact search queries."""

    async def test_contact_names_in_chat_response(
        self, client: AsyncClient, user_with_data: dict
    ):
        """'who do I know at Google?' returns actual contact names."""
        resp = await client.post(
            "/api/v1/coach/chat",
            headers=user_with_data,
            json={"message": "who do I know at Google?"},
        )
        assert resp.status_code == 200
        response_text = resp.json()["data"]["response"]
        # user_with_data creates Alice Eng at Google
        assert "Alice" in response_text

    async def test_contact_names_in_stream_response(
        self, client: AsyncClient, user_with_data: dict
    ):
        """Streaming endpoint also includes contact names."""
        resp = await client.post(
            "/api/v1/coach/chat/stream",
            headers=user_with_data,
            json={"message": "who do I know at Google?"},
        )
        assert resp.status_code == 200
        assert "Alice" in resp.text

    async def test_no_match_query_returns_generic_response(
        self, client: AsyncClient, user_with_data: dict
    ):
        """Query for a company with no contacts still returns a response."""
        resp = await client.post(
            "/api/v1/coach/chat",
            headers=user_with_data,
            json={"message": "who do I know at Netflix?"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]["response"]) > 0
