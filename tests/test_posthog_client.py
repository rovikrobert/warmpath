"""Tests for the PostHog analytics client utility."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


# ---------------------------------------------------------------------------
# 1. Unconfigured — all methods return gracefully with configured: False
# ---------------------------------------------------------------------------
class TestPostHogUnconfigured:
    """When POSTHOG_API_KEY or POSTHOG_PROJECT_ID are empty, every public
    method must return immediately with ``configured: False`` and never
    make an HTTP request."""

    @pytest.mark.asyncio
    async def test_query_funnel_unconfigured(self):
        with patch("app.utils.posthog_client.settings") as mock_settings:
            mock_settings.POSTHOG_API_KEY = ""
            mock_settings.POSTHOG_PROJECT_ID = ""
            from app.utils.posthog_client import query_funnel

            result = await query_funnel(["$pageview", "signup"])
        assert result["configured"] is False
        assert result["steps"] == []
        assert result["overall_conversion"] is None

    @pytest.mark.asyncio
    async def test_query_trends_unconfigured(self):
        with patch("app.utils.posthog_client.settings") as mock_settings:
            mock_settings.POSTHOG_API_KEY = ""
            mock_settings.POSTHOG_PROJECT_ID = ""
            from app.utils.posthog_client import query_trends

            result = await query_trends(["$pageview"])
        assert result["configured"] is False
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_query_referral_sources_unconfigured(self):
        with patch("app.utils.posthog_client.settings") as mock_settings:
            mock_settings.POSTHOG_API_KEY = ""
            mock_settings.POSTHOG_PROJECT_ID = ""
            from app.utils.posthog_client import query_referral_sources

            result = await query_referral_sources()
        assert result["configured"] is False
        assert result["sources"] == []


# ---------------------------------------------------------------------------
# Helper: patch settings to look "configured"
# ---------------------------------------------------------------------------
def _configured_settings():
    mock = MagicMock()
    mock.POSTHOG_API_KEY = "phx_testkey123"
    mock.POSTHOG_PROJECT_ID = "12345"
    mock.POSTHOG_HOST = "https://app.posthog.com"
    return mock


# ---------------------------------------------------------------------------
# 2. Configured — methods call the HTTP API with the right payload
# ---------------------------------------------------------------------------
class TestPostHogConfigured:
    """When PostHog credentials are present, verify each method builds the
    correct payload and calls the PostHog insights API."""

    @pytest.mark.asyncio
    async def test_query_funnel_calls_api(self):
        fake_response = {"result": [{"count": 100}]}
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_response
        mock_resp.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_resp
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.utils.posthog_client.settings", _configured_settings()),
            patch(
                "app.utils.posthog_client.httpx.AsyncClient",
                return_value=mock_client_instance,
            ),
        ):
            from app.utils.posthog_client import query_funnel

            result = await query_funnel(["$pageview", "signup"], date_to="-1d")

        assert result == fake_response
        mock_client_instance.post.assert_called_once()
        call_kwargs = mock_client_instance.post.call_args
        payload = call_kwargs.kwargs["json"]
        assert payload["insight"] == "FUNNELS"
        assert len(payload["events"]) == 2
        assert payload["date_to"] == "-1d"
        assert payload["funnel_window_days"] == 14

    @pytest.mark.asyncio
    async def test_query_trends_calls_api(self):
        fake_response = {"result": [{"data": [1, 2, 3]}]}
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_response
        mock_resp.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_resp
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.utils.posthog_client.settings", _configured_settings()),
            patch(
                "app.utils.posthog_client.httpx.AsyncClient",
                return_value=mock_client_instance,
            ),
        ):
            from app.utils.posthog_client import query_trends

            result = await query_trends(
                ["signup", "csv_upload"], interval="week", date_to="-7d"
            )

        assert result == fake_response
        call_kwargs = mock_client_instance.post.call_args
        payload = call_kwargs.kwargs["json"]
        assert payload["insight"] == "TRENDS"
        assert payload["interval"] == "week"
        assert payload["date_to"] == "-7d"
        assert len(payload["events"]) == 2

    @pytest.mark.asyncio
    async def test_query_referral_sources_calls_api(self):
        fake_response = {"result": [{"breakdown_value": "google.com"}]}
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_response
        mock_resp.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_resp
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.utils.posthog_client.settings", _configured_settings()),
            patch(
                "app.utils.posthog_client.httpx.AsyncClient",
                return_value=mock_client_instance,
            ),
        ):
            from app.utils.posthog_client import query_referral_sources

            result = await query_referral_sources(date_to="-1d")

        assert result == fake_response
        call_kwargs = mock_client_instance.post.call_args
        payload = call_kwargs.kwargs["json"]
        assert payload["breakdown"] == "$referring_domain"
        assert payload["breakdown_type"] == "event"
        assert payload["events"][0]["id"] == "$pageview"
        assert payload["date_to"] == "-1d"

    @pytest.mark.asyncio
    async def test_query_url_uses_settings(self):
        """Verify the URL is assembled from POSTHOG_HOST + POSTHOG_PROJECT_ID."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_resp
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.utils.posthog_client.settings", _configured_settings()),
            patch(
                "app.utils.posthog_client.httpx.AsyncClient",
                return_value=mock_client_instance,
            ),
        ):
            from app.utils.posthog_client import query_trends

            await query_trends(["$pageview"])

        call_args = mock_client_instance.post.call_args
        url = call_args.args[0]
        assert url == "https://app.posthog.com/api/projects/12345/insights/trend/"
        headers = call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer phx_testkey123"


# ---------------------------------------------------------------------------
# 3. HTTP errors — methods return error dict gracefully
# ---------------------------------------------------------------------------
class TestPostHogHTTPErrors:
    """When the HTTP request fails, methods must return an error dict
    with ``error`` and ``results`` keys — never raise."""

    @pytest.mark.asyncio
    async def test_http_error_returns_error_dict(self):
        mock_client_instance = AsyncMock()
        mock_client_instance.post.side_effect = httpx.HTTPError("connection refused")
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.utils.posthog_client.settings", _configured_settings()),
            patch(
                "app.utils.posthog_client.httpx.AsyncClient",
                return_value=mock_client_instance,
            ),
        ):
            from app.utils.posthog_client import query_funnel

            result = await query_funnel(["$pageview", "signup"])

        assert "error" in result
        assert "connection refused" in result["error"]
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_http_status_error_returns_error_dict(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401 Unauthorized",
            request=MagicMock(),
            response=mock_resp,
        )

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_resp
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.utils.posthog_client.settings", _configured_settings()),
            patch(
                "app.utils.posthog_client.httpx.AsyncClient",
                return_value=mock_client_instance,
            ),
        ):
            from app.utils.posthog_client import query_trends

            result = await query_trends(["$pageview"])

        assert "error" in result
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_timeout_returns_error_dict(self):
        mock_client_instance = AsyncMock()
        mock_client_instance.post.side_effect = httpx.TimeoutException("timed out")
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.utils.posthog_client.settings", _configured_settings()),
            patch(
                "app.utils.posthog_client.httpx.AsyncClient",
                return_value=mock_client_instance,
            ),
        ):
            from app.utils.posthog_client import query_referral_sources

            result = await query_referral_sources()

        assert "error" in result
        assert result["results"] == []
