"""Tests for job scan anomaly detection (Phase 0).

Covers the 4 anomaly rules in _detect_job_anomaly, the dispatch pipeline,
and the Telegram notification formatting/dedup.
"""

import unittest.mock as mock

import fakeredis.aioredis
import pytest

from app.agent_runtime.notifications import (
    _format_job_scan_alert,
    notify_job_scan_anomalies,
)
from app.tasks.job_scan_tasks import _detect_job_anomaly


# ---------------------------------------------------------------------------
# _detect_job_anomaly — the 4 rules
# ---------------------------------------------------------------------------


class TestDetectJobAnomaly:
    def test_ats_api_failu[RESEND_KEY_REDACTED](self):
        """ATS board registered but 0 jobs → high severity."""
        result = _detect_job_anomaly(
            "stripe", {"greenhouse": "stripe"}, job_count=0, prev_count=100
        )
        assert result is not None
        assert result["severity"] == "high"
        assert "ATS API returned 0 jobs" in result["title"]
        assert result["source_team"] == "engineering"
        assert result["category"] == "job_scan_anomaly"

    def test_ats_with_jobs_returns_none(self):
        """ATS board returned results → no anomaly."""
        result = _detect_job_anomaly(
            "stripe", {"greenhouse": "stripe"}, job_count=50, prev_count=60
        )
        assert result is None

    def test_spa_scrape_failu[RESEND_KEY_REDACTED](self):
        """Career page only, returned < threshold → medium severity."""
        result = _detect_job_anomaly(
            "google",
            {"career_page": "https://careers.google.com"},
            job_count=2,
            prev_count=0,
        )
        assert result is not None
        assert result["severity"] == "medium"
        assert "career page scrape" in result["title"]
        assert "2 jobs" in result["title"]

    def test_spa_scrape_with_ats_skipped(self):
        """Career page + ATS board — SPA rule does not apply (ATS takes priority)."""
        result = _detect_job_anomaly(
            "example",
            {"greenhouse": "example", "career_page": "https://example.com/careers"},
            job_count=3,
            prev_count=0,
        )
        # Should NOT trigger SPA rule since ATS is present
        # (ATS rule doesn't trigger either since job_count > 0)
        assert result is None

    def test_spa_scrape_zero_is_total_zero_not_spa(self):
        """Career page only, 0 jobs → total zero rule, not SPA rule."""
        result = _detect_job_anomaly(
            "meta",
            {"career_page": "https://careers.meta.com"},
            job_count=0,
            prev_count=0,
        )
        assert result is not None
        assert "0 jobs from all sources" in result["title"]
        assert result["severity"] == "medium"

    def test_major_drop_returns_high(self):
        """Job count dropped below 1/3 of previous → high severity."""
        result = _detect_job_anomaly(
            "grab", {"greenhouse": "grab"}, job_count=5, prev_count=50
        )
        assert result is not None
        assert result["severity"] == "high"
        assert "dropped" in result["title"]
        assert "50" in result["title"] and "5" in result["title"]

    def test_major_drop_needs_minimum_prev_count(self):
        """Previous count < 10 → major drop rule does not apply."""
        result = _detect_job_anomaly(
            "small_co", {"greenhouse": "small_co"}, job_count=1, prev_count=5
        )
        # prev_count=5 is below the 10 threshold, so no drop anomaly
        # job_count=1 with ATS → not zero so no ATS failure either
        assert result is None

    def test_total_zero_no_ats_returns_medium(self):
        """No ATS, 0 jobs from all sources → medium severity."""
        result = _detect_job_anomaly(
            "unknown_co",
            {"career_page": "https://unknown.com/jobs"},
            job_count=0,
            prev_count=0,
        )
        assert result is not None
        assert result["severity"] == "medium"
        assert "0 jobs from all sources" in result["title"]

    def test_healthy_career_page_returns_none(self):
        """Career page returned enough jobs → no anomaly."""
        result = _detect_job_anomaly(
            "bytedance",
            {"career_page": "https://jobs.bytedance.com"},
            job_count=30,
            prev_count=25,
        )
        assert result is None

    def test_ats_failu[RESEND_KEY_REDACTED](self):
        """ATS API failure (rule 1) fires before major drop (rule 3)."""
        result = _detect_job_anomaly(
            "stripe", {"greenhouse": "stripe"}, job_count=0, prev_count=100
        )
        assert result is not None
        assert "ATS API" in result["title"]


# ---------------------------------------------------------------------------
# Notification formatting
# ---------------------------------------------------------------------------


class TestFormatJobScanAlert:
    def test_single_anomaly(self):
        msg = _format_job_scan_alert(
            [{"severity": "high", "title": "stripe: ATS API returned 0 jobs"}]
        )
        assert "1 issue detected" in msg
        assert "[HIGH]" in msg
        assert "stripe" in msg
        assert "Next scan" in msg

    def test_multiple_anomalies(self):
        anomalies = [
            {"severity": "high", "title": "stripe: ATS failure"},
            {"severity": "medium", "title": "google: SPA scrape"},
        ]
        msg = _format_job_scan_alert(anomalies)
        assert "2 issues" in msg
        assert "[HIGH]" in msg
        assert "[MEDIUM]" in msg

    def test_empty_anomalies(self):
        msg = _format_job_scan_alert([])
        assert "0 issues" in msg


# ---------------------------------------------------------------------------
# Notification dedup
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_notify_job_scan_sends_alert(fake_redis):
    """Job scan anomaly alert is sent on first call."""
    with (
        mock.patch("redis.asyncio.from_url", return_value=fake_redis),
        mock.patch("app.agent_runtime.notifications._send_telegram") as mock_send,
    ):
        await notify_job_scan_anomalies(
            anomalies=[{"severity": "high", "title": "stripe: ATS failure"}],
            redis_url="redis://fake",
        )
    mock_send.assert_called_once()
    assert "Job Scan Anomaly" in mock_send.call_args[0][0]


@pytest.mark.asyncio
async def test_notify_job_scan_deduped_second_call(fake_redis):
    """Second job scan alert on same day is skipped."""
    with (
        mock.patch("redis.asyncio.from_url", return_value=fake_redis),
        mock.patch("app.agent_runtime.notifications._send_telegram") as mock_send,
    ):
        await notify_job_scan_anomalies(
            anomalies=[{"severity": "high", "title": "stripe: ATS failure"}],
            redis_url="redis://fake",
        )
        await notify_job_scan_anomalies(
            anomalies=[{"severity": "medium", "title": "google: SPA scrape"}],
            redis_url="redis://fake",
        )
    assert mock_send.call_count == 1


@pytest.mark.asyncio
async def test_notify_job_scan_empty_list_skipped():
    """Empty anomaly list does not send or touch Redis."""
    with mock.patch("app.agent_runtime.notifications._send_telegram") as mock_send:
        await notify_job_scan_anomalies(anomalies=[], redis_url="redis://fake")
    mock_send.assert_not_called()
