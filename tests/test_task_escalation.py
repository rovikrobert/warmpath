"""Tests for Celery task failure escalation utility."""

from unittest.mock import AsyncMock, patch

import pytest

from app.utils.task_escalation import escalate_task_failure


@pytest.mark.asyncio
async def test_escalate_new_finding_sends_telegram():
    """New task failure triggers Telegram alert."""
    mock_store = AsyncMock()
    mock_store.classify_findings.return_value = (
        [{"finding_state": "new", "finding_hash": "abc"}],
        [],
    )

    with (
        patch("app.utils.task_escalation._get_finding_store", return_value=mock_store),
        patch(
            "app.utils.task_escalation._send_telegram_alert", new_callable=AsyncMock
        ) as mock_tg,
    ):
        await escalate_task_failure(
            task_name="test_task", error=ValueError("boom"), severity="high"
        )

    mock_store.classify_findings.assert_called_once()
    mock_tg.assert_called_once()
    assert "test_task" in mock_tg.call_args[0][0]


@pytest.mark.asyncio
async def test_escalate_known_finding_skips_telegram():
    """Known (duplicate) task failure does not send Telegram alert."""
    mock_store = AsyncMock()
    mock_store.classify_findings.return_value = (
        [],
        [{"finding_state": "known", "finding_hash": "abc", "seen_count": 2}],
    )

    with (
        patch("app.utils.task_escalation._get_finding_store", return_value=mock_store),
        patch(
            "app.utils.task_escalation._send_telegram_alert", new_callable=AsyncMock
        ) as mock_tg,
    ):
        await escalate_task_failure(
            task_name="test_task", error=ValueError("boom"), severity="high"
        )

    mock_tg.assert_not_called()


@pytest.mark.asyncio
async def test_escalate_degrades_gracefully_on_redis_failure():
    """Escalation still sends Telegram when FindingStore is unavailable."""
    with (
        patch(
            "app.utils.task_escalation._get_finding_store",
            side_effect=ConnectionError("redis down"),
        ),
        patch(
            "app.utils.task_escalation._send_telegram_alert", new_callable=AsyncMock
        ) as mock_tg,
    ):
        await escalate_task_failure(
            task_name="test_task", error=RuntimeError("oops"), severity="medium"
        )

    # When FindingStore fails, is_new defaults to True → Telegram sent
    mock_tg.assert_called_once()


@pytest.mark.asyncio
async def test_escalate_includes_error_details_in_finding():
    """Finding dict includes task name, error type, and severity."""
    mock_store = AsyncMock()
    mock_store.classify_findings.return_value = ([{"finding_state": "new"}], [])

    with (
        patch("app.utils.task_escalation._get_finding_store", return_value=mock_store),
        patch("app.utils.task_escalation._send_telegram_alert", new_callable=AsyncMock),
    ):
        await escalate_task_failure(
            task_name="send_digest", error=TypeError("bad arg"), severity="high"
        )

    finding = mock_store.classify_findings.call_args[0][0][0]
    assert finding["source_team"] == "engineering"
    assert finding["category"] == "celery_task_failure"
    assert "send_digest" in finding["title"]
    assert "TypeError" in finding["title"]
    assert finding["severity"] == "high"
