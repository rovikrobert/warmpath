"""Tests for Adzuna job aggregator client."""

from unittest.mock import AsyncMock, patch

import httpx

from app.services.job_aggregator import (
    _resolve_country,
    search_jobs_by_company,
)


def _mock_response(json_data, status_code=200):
    return httpx.Response(
        status_code=status_code,
        json=json_data,
        request=httpx.Request("GET", "https://api.adzuna.com/v1/api/jobs/sg/search/1"),
    )


# ---------------------------------------------------------------------------
# Country resolution
# ---------------------------------------------------------------------------


class TestCountryResolution:
    def test_singapo[RESEND_KEY_REDACTED](self):
        assert _resolve_country("Singapore") == "sg"

    def test_india_resolves_to_in(self):
        assert _resolve_country("India") == "in"

    def test_australia_resolves_to_au(self):
        assert _resolve_country("Australia") == "au"

    def test_us_resolves_to_us(self):
        assert _resolve_country("United States") == "us"

    def test_none_defaults_to_sg(self):
        assert _resolve_country(None) == "sg"

    def test_unknown_defaults_to_sg(self):
        assert _resolve_country("Mars") == "sg"


# ---------------------------------------------------------------------------
# Adzuna API client
# ---------------------------------------------------------------------------

ADZUNA_RESPONSE = {
    "results": [
        {
            "id": "12345",
            "title": "Senior Software Engineer",
            "company": {"display_name": "Grab"},
            "location": {"display_name": "Singapore, Central"},
            "category": {"label": "IT Jobs"},
            "redirect_url": "https://adzuna.sg/jobs/12345",
            "created": "2026-01-15T10:00:00Z",
        },
        {
            "id": "12346",
            "title": "Marketing Manager",
            "company": {"display_name": "Grab Holdings"},
            "location": {"display_name": "Remote"},
            "category": {"label": "Marketing"},
            "redirect_url": "https://adzuna.sg/jobs/12346",
            "created": "2026-01-20T08:00:00Z",
        },
        {
            "id": "99999",
            "title": "Unrelated Job",
            "company": {"display_name": "Other Corp"},
            "location": {"display_name": "Singapore"},
            "category": {"label": "IT Jobs"},
            "redirect_url": "https://adzuna.sg/jobs/99999",
        },
    ]
}


class TestAdzunaClient:
    async def test_returns_empty_when_not_configured(self):
        with patch("app.services.job_aggregator.settings") as mock_settings:
            mock_settings.ADZUNA_APP_ID = ""
            mock_settings.ADZUNA_APP_KEY = ""
            jobs = await search_jobs_by_company("Grab")
        assert jobs == []

    async def test_parses_and_filters_by_company(self):
        with (
            patch("app.services.job_aggregator.settings") as mock_settings,
            patch("app.services.job_aggregator.httpx.AsyncClient") as MockClient,
        ):
            mock_settings.ADZUNA_APP_ID = "test-id"
            mock_settings.ADZUNA_APP_KEY = "test-key"

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response(ADZUNA_RESPONSE))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            jobs = await search_jobs_by_company("Grab", "Singapore")

        # Should include Grab and Grab Holdings, exclude Other Corp
        assert len(jobs) == 2
        assert jobs[0]["title"] == "Senior Software Engineer"
        assert jobs[0]["source"] == "adzuna"
        assert jobs[0]["source_job_id"] == "12345"
        assert jobs[0]["department"] == "IT Jobs"
        assert jobs[0]["location"] == "Singapore, Central"
        assert jobs[1]["is_remote"] is True

    async def test_handles_http_error_gracefully(self):
        with (
            patch("app.services.job_aggregator.settings") as mock_settings,
            patch("app.services.job_aggregator.httpx.AsyncClient") as MockClient,
        ):
            mock_settings.ADZUNA_APP_ID = "test-id"
            mock_settings.ADZUNA_APP_KEY = "test-key"

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.HTTPError("Connection failed")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            jobs = await search_jobs_by_company("Grab")

        assert jobs == []

    async def test_handles_empty_results(self):
        with (
            patch("app.services.job_aggregator.settings") as mock_settings,
            patch("app.services.job_aggregator.httpx.AsyncClient") as MockClient,
        ):
            mock_settings.ADZUNA_APP_ID = "test-id"
            mock_settings.ADZUNA_APP_KEY = "test-key"

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response({"results": []}))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            jobs = await search_jobs_by_company("NonexistentCorp123")

        assert jobs == []
