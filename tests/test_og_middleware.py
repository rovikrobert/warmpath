"""Tests for social bot OG tag middleware in the SPA catch-all."""

import pytest
from httpx import AsyncClient

from app.main import _get_og_config, _is_social_bot, _serve_og_html


# ---------------------------------------------------------------------------
# Unit tests: _is_social_bot
# ---------------------------------------------------------------------------


class _FakeRequest:
    """Minimal request stub with headers for testing _is_social_bot."""

    def __init__(self, user_agent: str = ""):
        self.headers = {"user-agent": user_agent}


@pytest.mark.parametrize(
    "ua",
    [
        "facebookexternalhit/1.1",
        "Twitterbot/1.0",
        "LinkedInBot/1.0 (compatible; Mozilla/5.0)",
        "Slackbot-LinkExpanding 1.0",
        "Discordbot/2.0",
        "WhatsApp/2.23.20.0",
    ],
)
def test_is_social_bot_detects_all_six_bots(ua: str):
    """_is_social_bot returns True for all six supported social bot UAs."""
    assert _is_social_bot(_FakeRequest(ua)) is True


def test_is_social_bot_rejects_googlebot():
    """_is_social_bot does NOT match Googlebot (Google handles JS SPAs fine)."""
    assert _is_social_bot(_FakeRequest("Googlebot/2.1")) is False


def test_is_social_bot_rejects_normal_browser():
    """_is_social_bot returns False for a normal browser UA."""
    assert (
        _is_social_bot(_FakeRequest("Mozilla/5.0 (Macintosh; Intel Mac OS X)")) is False
    )


def test_is_social_bot_handles_empty_ua():
    """_is_social_bot returns False when User-Agent is empty."""
    assert _is_social_bot(_FakeRequest("")) is False


def test_is_social_bot_handles_missing_ua():
    """_is_social_bot returns False when User-Agent header is absent."""

    class _NoUARequest:
        headers: dict[str, str] = {}

    assert _is_social_bot(_NoUARequest()) is False


# ---------------------------------------------------------------------------
# Unit tests: _get_og_config
# ---------------------------------------------------------------------------


def test_get_og_config_join_default_returns_network_holder_copy():
    """Default /join OG config targets network holders (share your network)."""
    config = _get_og_config("join", {})
    assert config is not None
    assert "Share Your Network" in config["title"]
    assert "referral bonus" in config["description"]


def test_get_og_config_join_seeker_intent_returns_seeker_copy():
    """/join?intent=seeker OG config targets job seekers."""
    config = _get_og_config("join", {"intent": "seeker"})
    assert config is not None
    assert "Stop Applying Cold" in config["title"]
    assert "10-40%" in config["description"]


def test_get_og_config_intro_prefix_returns_intro_copy():
    """/intro/sometoken returns the intro OG config."""
    config = _get_og_config("intro/abc123", {})
    assert config is not None
    assert "Introduction via WarmPath" in config["title"]
    assert "network" in config["description"]


def test_get_og_config_intro_bare_returns_intro_copy():
    """Bare /intro path also matches."""
    config = _get_og_config("intro", {})
    assert config is not None
    assert "Introduction via WarmPath" in config["title"]


def test_get_og_config_unknown_path_returns_none():
    """Unknown paths return None (no OG override)."""
    assert _get_og_config("coach", {}) is None
    assert _get_og_config("contacts", {}) is None
    assert _get_og_config("", {}) is None


# ---------------------------------------------------------------------------
# Unit tests: _serve_og_html
# ---------------------------------------------------------------------------


def test_serve_og_html_contains_all_required_meta_tags():
    """OG HTML response includes og:title, og:description, og:image, og:url,
    og:type, twitter:card, twitter:title, twitter:description, twitter:image,
    and a meta refresh redirect."""
    resp = _serve_og_html("join", {})
    html = resp.body.decode()

    # OG tags
    assert "og:title" in html
    assert "og:description" in html
    assert "og:image" in html
    assert "og:url" in html
    assert "og:type" in html

    # Twitter card tags
    assert "twitter:card" in html
    assert "twitter:title" in html
    assert "twitter:description" in html
    assert "twitter:image" in html
    assert "summary_large_image" in html

    # Meta refresh
    assert 'http-equiv="refresh"' in html

    # Image URL
    assert "og-image.png" in html


def test_serve_og_html_includes_query_params_in_url():
    """OG page URL includes query parameters when present."""
    resp = _serve_og_html("join", {"intent": "seeker"})
    html = resp.body.decode()
    assert "intent=seeker" in html


def test_serve_og_html_returns_htmlresponse():
    """_serve_og_html returns an HTMLResponse."""
    from fastapi.responses import HTMLResponse

    resp = _serve_og_html("join", {})
    assert isinstance(resp, HTMLResponse)


# ---------------------------------------------------------------------------
# Integration tests: SPA catch-all with bot detection
# ---------------------------------------------------------------------------


async def test_bot_ua_on_join_gets_og_html(client: AsyncClient):
    """Social bot requesting /join receives OG HTML, not the SPA."""
    resp = await client.get(
        "/join",
        headers={"User-Agent": "facebookexternalhit/1.1"},
    )
    # If frontend/dist doesn't exist, the SPA catch-all isn't registered
    # and we get 404. If it is registered, we get OG HTML.
    if resp.status_code == 200:
        html = resp.text
        assert "og:title" in html
        assert "Share Your Network" in html
        assert "og:image" in html
    else:
        # SPA catch-all not registered (no frontend/dist) — test the
        # functions directly instead (covered by unit tests above)
        pytest.skip("SPA catch-all not registered (no frontend/dist)")


async def test_bot_ua_on_join_seeker_gets_seeker_og(client: AsyncClient):
    """Social bot requesting /join?intent=seeker gets seeker-specific OG tags."""
    resp = await client.get(
        "/join",
        params={"intent": "seeker"},
        headers={"User-Agent": "LinkedInBot/1.0"},
    )
    if resp.status_code == 200:
        html = resp.text
        assert "Stop Applying Cold" in html
        assert "twitter:card" in html
    else:
        pytest.skip("SPA catch-all not registered (no frontend/dist)")


async def test_bot_ua_on_intro_token_gets_intro_og(client: AsyncClient):
    """Social bot requesting /intro/sometoken gets intro OG tags."""
    resp = await client.get(
        "/intro/abc123token",
        headers={"User-Agent": "Slackbot-LinkExpanding 1.0"},
    )
    if resp.status_code == 200:
        html = resp.text
        assert "Introduction via WarmPath" in html
        assert "og:description" in html
    else:
        pytest.skip("SPA catch-all not registered (no frontend/dist)")


async def test_normal_ua_on_join_does_not_get_og_html(client: AsyncClient):
    """Normal browser requesting /join gets the SPA, not the bot OG HTML."""
    resp = await client.get(
        "/join",
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
    )
    if resp.status_code == 200:
        html = resp.text
        # The bot-specific OG title should NOT appear; the SPA index.html
        # has its own generic og:title which is fine — we just verify the
        # bot-served variant is absent.
        assert "Share Your Network" not in html
        assert 'http-equiv="refresh"' not in html
    else:
        pytest.skip("SPA catch-all not registered (no frontend/dist)")


async def test_api_routes_unaffected_by_og_middleware(client: AsyncClient):
    """API routes still work normally even with a bot User-Agent."""
    resp = await client.get(
        "/health",
        headers={"User-Agent": "facebookexternalhit/1.1"},
    )
    # Health endpoint is registered before the SPA catch-all, so it should
    # return JSON regardless of User-Agent.
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert body["data"]["status"] in ("healthy", "degraded")
