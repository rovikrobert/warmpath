"""Tests for JobSpy job fetcher fallback."""

from datetime import datetime, timezone
from unittest.mock import patch

from app.services.jobspy_fetcher import (
    _make_source_job_id,
    _parse_date,
    _scrape_sync,
    search_jobs_via_jobspy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_df(rows: list[dict]):
    """Create a mock DataFrame-like object from a list of dicts."""
    import pandas as pd

    return pd.DataFrame(rows)


SAMPLE_ROWS = [
    {
        "title": "Senior Software Engineer",
        "company": "Stripe",
        "location": "San Francisco, CA",
        "job_url": "https://indeed.com/jobs/stripe-sse-123",
        "site": "indeed",
        "date_posted": datetime(2026, 2, 20, tzinfo=timezone.utc),
        "is_remote": False,
    },
    {
        "title": "Product Manager",
        "company": "Stripe, Inc.",
        "location": "Remote",
        "job_url": "https://indeed.com/jobs/stripe-pm-456",
        "site": "indeed",
        "date_posted": datetime(2026, 2, 19, tzinfo=timezone.utc),
        "is_remote": True,
    },
    {
        "title": "Marketing Analyst",
        "company": "Other Corp",
        "location": "New York, NY",
        "job_url": "https://indeed.com/jobs/othercorp-ma-789",
        "site": "indeed",
        "date_posted": None,
        "is_remote": False,
    },
]


# ---------------------------------------------------------------------------
# _make_source_job_id
# ---------------------------------------------------------------------------


class TestMakeSourceJobId:
    def test_produces_16_char_hex(self):
        result = _make_source_job_id("https://example.com/job/123")
        assert len(result) == 16
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic_for_same_url(self):
        url = "https://indeed.com/jobs/stripe-sse-123"
        assert _make_source_job_id(url) == _make_source_job_id(url)

    def test_different_urls_produce_different_ids(self):
        id1 = _make_source_job_id("https://indeed.com/job/1")
        id2 = _make_source_job_id("https://indeed.com/job/2")
        assert id1 != id2


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------


class TestParseDate:
    def test_returns_none_for_none(self):
        assert _parse_date(None) is None

    def test_parses_aware_datetime(self):
        dt = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
        assert _parse_date(dt) == dt

    def test_adds_utc_to_naive_datetime(self):
        dt = datetime(2026, 1, 15, 10, 0)
        result = _parse_date(dt)
        assert result is not None
        assert result.tzinfo == timezone.utc

    def test_parses_iso_string(self):
        result = _parse_date("2026-01-15T10:00:00Z")
        assert result is not None
        assert result.year == 2026
        assert result.month == 1

    def test_returns_none_for_empty_string(self):
        assert _parse_date("") is None


# ---------------------------------------------------------------------------
# _scrape_sync
# ---------------------------------------------------------------------------


class TestScrapeSync:
    @patch("app.services.jobspy_fetcher.settings")
    def test_normalizes_results_and_filters_by_company(self, mock_settings):
        mock_settings.JOBSPY_SEARCH_ALL_SITES = False
        mock_settings.JOBSPY_ENABLED = True
        df = _make_mock_df(SAMPLE_ROWS)

        with patch("jobspy.scrape_jobs", return_value=df):
            jobs = _scrape_sync("Stripe")

        # Should include Stripe and Stripe, Inc. — exclude Other Corp
        assert len(jobs) == 2
        assert jobs[0]["title"] == "Senior Software Engineer"
        assert jobs[0]["source"] == "indeed"
        assert jobs[0]["location"] == "San Francisco, CA"
        assert jobs[0]["is_remote"] is False
        assert len(jobs[0]["source_job_id"]) == 16

        assert jobs[1]["title"] == "Product Manager"
        assert jobs[1]["is_remote"] is True

    @patch("app.services.jobspy_fetcher.settings")
    def test_returns_empty_on_empty_dataframe(self, mock_settings):
        mock_settings.JOBSPY_SEARCH_ALL_SITES = False
        mock_settings.JOBSPY_ENABLED = True

        import pandas as pd

        with patch("jobspy.scrape_jobs", return_value=pd.DataFrame()):
            jobs = _scrape_sync("NonexistentCorp")

        assert jobs == []

    @patch("app.services.jobspy_fetcher.settings")
    def test_returns_empty_on_scrape_exception(self, mock_settings):
        mock_settings.JOBSPY_SEARCH_ALL_SITES = False
        mock_settings.JOBSPY_ENABLED = True

        with patch("jobspy.scrape_jobs", side_effect=RuntimeError("Network error")):
            jobs = _scrape_sync("Stripe")

        assert jobs == []

    @patch("app.services.jobspy_fetcher.settings")
    def test_returns_empty_when_jobspy_not_installed(self, mock_settings):
        mock_settings.JOBSPY_SEARCH_ALL_SITES = False
        mock_settings.JOBSPY_ENABLED = True

        with patch.dict("sys.modules", {"jobspy": None}):
            jobs = _scrape_sync("Stripe")

        assert jobs == []

    @patch("app.services.jobspy_fetcher.settings")
    def test_skips_rows_with_blank_title(self, mock_settings):
        mock_settings.JOBSPY_SEARCH_ALL_SITES = False
        mock_settings.JOBSPY_ENABLED = True
        rows = [
            {
                "title": "",
                "company": "Stripe",
                "location": "SF",
                "job_url": "https://x.com/1",
                "site": "indeed",
                "date_posted": None,
                "is_remote": False,
            }
        ]
        df = _make_mock_df(rows)
        with patch("jobspy.scrape_jobs", return_value=df):
            jobs = _scrape_sync("Stripe")
        assert jobs == []

    @patch("app.services.jobspy_fetcher.settings")
    def test_uses_all_sites_when_flag_enabled(self, mock_settings):
        mock_settings.JOBSPY_SEARCH_ALL_SITES = True
        mock_settings.JOBSPY_ENABLED = True

        import pandas as pd

        with patch("jobspy.scrape_jobs", return_value=pd.DataFrame()) as mock_scrape:
            _scrape_sync("Stripe")

        call_kwargs = mock_scrape.call_args
        sites = call_kwargs.kwargs.get("site_name") or call_kwargs[1].get("site_name")
        assert len(sites) == 5
        assert "indeed" in sites
        assert "linkedin" in sites


# ---------------------------------------------------------------------------
# search_jobs_via_jobspy (async wrapper)
# ---------------------------------------------------------------------------


class TestSearchJobsViaJobspy:
    async def test_returns_empty_when_disabled(self):
        with patch("app.services.jobspy_fetcher.settings") as mock_settings:
            mock_settings.JOBSPY_ENABLED = False
            jobs = await search_jobs_via_jobspy("Stripe")
        assert jobs == []

    async def test_delegates_to_thread_when_enabled(self):
        expected = [{"title": "Engineer", "source": "indeed"}]
        with (
            patch("app.services.jobspy_fetcher.settings") as mock_settings,
            patch(
                "app.services.jobspy_fetcher._scrape_sync", return_value=expected
            ) as mock_scrape,
        ):
            mock_settings.JOBSPY_ENABLED = True
            jobs = await search_jobs_via_jobspy("Stripe", max_results=10)

        assert jobs == expected
        mock_scrape.assert_called_once_with("Stripe", 10)


# ---------------------------------------------------------------------------
# Source mapping
# ---------------------------------------------------------------------------


class TestSourceMapping:
    @patch("app.services.jobspy_fetcher.settings")
    def test_all_five_sources_mapped(self, mock_settings):
        mock_settings.JOBSPY_SEARCH_ALL_SITES = True
        mock_settings.JOBSPY_ENABLED = True

        rows = [
            {
                "title": f"Role {site}",
                "company": "Stripe",
                "location": "SF",
                "job_url": f"https://example.com/{site}",
                "site": site,
                "date_posted": None,
                "is_remote": False,
            }
            for site in ["indeed", "linkedin", "glassdoor", "zip_recruiter", "google"]
        ]
        df = _make_mock_df(rows)

        with patch("jobspy.scrape_jobs", return_value=df):
            jobs = _scrape_sync("Stripe")

        sources = {j["source"] for j in jobs}
        assert sources == {
            "indeed",
            "linkedin_jobspy",
            "glassdoor",
            "ziprecruiter",
            "google_jobs",
        }

    @patch("app.services.jobspy_fetcher.settings")
    def test_unknown_site_uses_raw_value(self, mock_settings):
        mock_settings.JOBSPY_SEARCH_ALL_SITES = False
        mock_settings.JOBSPY_ENABLED = True

        rows = [
            {
                "title": "Role",
                "company": "Stripe",
                "location": "SF",
                "job_url": "https://example.com/new",
                "site": "new_board",
                "date_posted": None,
                "is_remote": False,
            }
        ]
        df = _make_mock_df(rows)

        with patch("jobspy.scrape_jobs", return_value=df):
            jobs = _scrape_sync("Stripe")

        assert jobs[0]["source"] == "new_board"
