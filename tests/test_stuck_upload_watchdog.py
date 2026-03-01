"""Tests for the stuck upload watchdog — detects and fails stale CSV uploads."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import TestSessionLocal

from app.models.contact import CsvUpload
from app.models.email_campaign import EmailCampaignLog
from app.models.user import User
from app.tasks.infra_tasks import detect_and_fail_stuck_uploads


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db(truncate_tables) -> AsyncSession:
    async with TestSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(email: str | None = None) -> User:
    return User(
        id=uuid.uuid4(),
        email=email or f"{uuid.uuid4().hex[:8]}@test.com",
        full_name="Test User",
        intent="find_referrals",
        created_at=datetime.now(timezone.utc) - timedelta(days=7),
    )


def _make_upload(
    user_id: uuid.UUID,
    status: str = "queued",
    created_at: datetime | None = None,
    started_at: datetime | None = None,
    batch_job_name: str | None = None,
) -> CsvUpload:
    return CsvUpload(
        user_id=user_id,
        filename="Connections.csv",
        status=status,
        created_at=created_at or datetime.now(timezone.utc) - timedelta(hours=1),
        started_at=started_at,
        batch_job_name=batch_job_name,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_watchdog_fails_stuck_queued_upload(mock_send, db: AsyncSession):
    """Upload stuck in 'queued' for >10 min gets marked failed + user notified."""
    user = _make_user()
    db.add(user)
    await db.flush()

    upload = _make_upload(
        user.id,
        status="queued",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=15),
    )
    db.add(upload)
    await db.flush()

    failed, notified = await detect_and_fail_stuck_uploads(db)

    assert failed == 1
    assert notified == 1
    await db.refresh(upload)
    assert upload.status == "failed"
    assert upload.completed_at is not None
    assert "timed out" in upload.error_message

    # User should have been emailed
    log_result = await db.execute(
        select(EmailCampaignLog).where(
            EmailCampaignLog.user_id == user.id,
            EmailCampaignLog.email_type == "upload_failed",
        )
    )
    assert log_result.scalar_one_or_none() is not None
    assert mock_send.call_count == 1


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_watchdog_fails_stuck_processing_upload(mock_send, db: AsyncSession):
    """Upload stuck in 'processing' for >15 min gets marked failed."""
    user = _make_user()
    db.add(user)
    await db.flush()

    upload = _make_upload(
        user.id,
        status="processing",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=20),
        started_at=datetime.now(timezone.utc) - timedelta(minutes=18),
    )
    db.add(upload)
    await db.flush()

    failed, notified = await detect_and_fail_stuck_uploads(db)

    assert failed == 1
    assert notified == 1
    await db.refresh(upload)
    assert upload.status == "failed"
    assert mock_send.call_count == 1


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_watchdog_ignores_recent_upload(mock_send, db: AsyncSession):
    """Upload queued 2 min ago should NOT be marked failed."""
    user = _make_user()
    db.add(user)
    await db.flush()

    upload = _make_upload(
        user.id,
        status="queued",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    db.add(upload)
    await db.flush()

    failed, _ = await detect_and_fail_stuck_uploads(db)

    assert failed == 0
    await db.refresh(upload)
    assert upload.status == "queued"
    assert mock_send.call_count == 0


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_watchdog_ignores_completed_upload(mock_send, db: AsyncSession):
    """Completed uploads should not be touched."""
    user = _make_user()
    db.add(user)
    await db.flush()

    upload = _make_upload(
        user.id,
        status="completed",
        created_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    upload.completed_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.add(upload)
    await db.flush()

    failed, _ = await detect_and_fail_stuck_uploads(db)

    assert failed == 0
    await db.refresh(upload)
    assert upload.status == "completed"
    assert mock_send.call_count == 0


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_watchdog_dedupes_notification_per_upload(mock_send, db: AsyncSession):
    """Once an upload is failed, second watchdog run doesn't touch it."""
    user = _make_user()
    db.add(user)
    await db.flush()

    upload = _make_upload(
        user.id,
        status="queued",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=15),
    )
    db.add(upload)
    await db.flush()

    # First run — should fail it and notify
    failed1, _ = await detect_and_fail_stuck_uploads(db)
    assert failed1 == 1
    assert mock_send.call_count == 1

    # Upload is now 'failed', so second run shouldn't find it
    mock_send.reset_mock()
    failed2, _ = await detect_and_fail_stuck_uploads(db)
    assert failed2 == 0
    assert mock_send.call_count == 0


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_watchdog_batch_upload_longer_threshold(mock_send, db: AsyncSession):
    """Batch uploads (Gemini API) get a 2-hour threshold, not 10 min."""
    user = _make_user()
    db.add(user)
    await db.flush()

    # 30 min old batch upload — should still be OK
    upload = _make_upload(
        user.id,
        status="processing",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        started_at=datetime.now(timezone.utc) - timedelta(minutes=28),
        batch_job_name="batch_abc123",
    )
    db.add(upload)
    await db.flush()

    failed, _ = await detect_and_fail_stuck_uploads(db)

    assert failed == 0
    await db.refresh(upload)
    assert upload.status == "processing"  # Not failed — within 2hr threshold
    assert mock_send.call_count == 0
