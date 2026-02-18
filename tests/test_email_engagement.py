"""Tests for the email engagement system — model, service, dedup, triggers."""

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
from app.models.enrichment import UsageLog
from app.models.marketplace import IntroFacilitation, MarketplaceListing, NetworkSharingPreferences
from app.models.search_request import SearchRequest
from app.models.user import User
from app.services.email_engagement import (
    send_csv_reminder_d1,
    send_csv_reminder_d3,
    send_first_search_nudge_d2,
    send_intro_pending_reminder,
    send_nh_sharing_reminder_d2,
    send_reengagement_d30,
    send_reengagement_d90,
    send_weekly_digest,
    send_welcome_email_js,
    send_welcome_email_nh,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(
    email: str | None = None,
    user_type: str = "job_seeker",
    created_at: datetime | None = None,
    marketing_opt_out: bool = False,
) -> User:
    return User(
        id=uuid.uuid4(),
        email=email or f"{uuid.uuid4().hex[:8]}@test.com",
        password_hash="hashed",
        full_name="Test User",
        user_type=user_type,
        created_at=created_at or datetime.now(timezone.utc),
        marketing_opt_out=marketing_opt_out,
    )


def _make_csv_upload(user_id: uuid.UUID) -> CsvUpload:
    return CsvUpload(
        user_id=user_id,
        filename="test.csv",
        row_count=10,
        status="completed",
    )


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with TestSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_campaign_log_creation(db: AsyncSession) -> None:
    user = _make_user()
    db.add(user)
    await db.flush()

    log = EmailCampaignLog(
        user_id=user.id,
        email_type="welcome_js",
        sent_date="2026-02-18",
    )
    db.add(log)
    await db.flush()

    result = await db.execute(
        select(EmailCampaignLog).where(EmailCampaignLog.user_id == user.id)
    )
    row = result.scalar_one()
    assert row.email_type == "welcome_js"
    assert row.sent_date == "2026-02-18"
    assert row.opened_at is None


@pytest.mark.asyncio
async def test_email_campaign_log_dedup_constraint(db: AsyncSession) -> None:
    """Same user + email_type + date should fail unique constraint."""
    user = _make_user()
    db.add(user)
    await db.flush()

    log1 = EmailCampaignLog(
        user_id=user.id, email_type="csv_reminder_d1", sent_date="2026-02-18"
    )
    db.add(log1)
    await db.flush()

    log2 = EmailCampaignLog(
        user_id=user.id, email_type="csv_reminder_d1", sent_date="2026-02-18"
    )
    db.add(log2)
    with pytest.raises(Exception):  # IntegrityError
        await db.flush()
    await db.rollback()


# ---------------------------------------------------------------------------
# Welcome email tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_welcome_email_js(mock_send: object, db: AsyncSession) -> None:
    user = _make_user()
    db.add(user)
    await db.flush()

    result = await send_welcome_email_js(user, db)
    assert result is True
    mock_send.assert_called_once()
    assert "Welcome to WarmPath" in mock_send.call_args[0][1]

    # Verify dedup
    result2 = await send_welcome_email_js(user, db)
    assert result2 is False
    assert mock_send.call_count == 1  # not called again


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_welcome_email_nh(mock_send: object, db: AsyncSession) -> None:
    user = _make_user(user_type="network_holder")
    db.add(user)
    await db.flush()

    result = await send_welcome_email_nh(user, db)
    assert result is True
    mock_send.assert_called_once()
    assert "referral bonuses" in mock_send.call_args[0][1]


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_welcome_email_respects_marketing_opt_out(
    mock_send: object, db: AsyncSession
) -> None:
    user = _make_user(marketing_opt_out=True)
    db.add(user)
    await db.flush()

    result = await send_welcome_email_js(user, db)
    assert result is False
    mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# CSV reminder D+1 tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_csv_reminder_d1_finds_eligible_users(
    mock_send: object, db: AsyncSession
) -> None:
    # User created 24h ago with no CSV upload
    user = _make_user(
        created_at=datetime.now(timezone.utc) - timedelta(hours=24)
    )
    db.add(user)
    await db.flush()

    count = await send_csv_reminder_d1(db)
    assert count == 1
    mock_send.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_csv_reminder_d1_skips_users_with_csv(
    mock_send: object, db: AsyncSession
) -> None:
    user = _make_user(
        created_at=datetime.now(timezone.utc) - timedelta(hours=24)
    )
    db.add(user)
    await db.flush()

    # Add a CSV upload
    db.add(_make_csv_upload(user.id))
    await db.flush()

    count = await send_csv_reminder_d1(db)
    assert count == 0
    mock_send.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_csv_reminder_d1_skips_too_new_users(
    mock_send: object, db: AsyncSession
) -> None:
    # User created 2 hours ago — too recent
    user = _make_user(
        created_at=datetime.now(timezone.utc) - timedelta(hours=2)
    )
    db.add(user)
    await db.flush()

    count = await send_csv_reminder_d1(db)
    assert count == 0


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_csv_reminder_d1_dedup(
    mock_send: object, db: AsyncSession
) -> None:
    user = _make_user(
        created_at=datetime.now(timezone.utc) - timedelta(hours=24)
    )
    db.add(user)
    await db.flush()

    count1 = await send_csv_reminder_d1(db)
    assert count1 == 1

    # Second run — already sent today
    count2 = await send_csv_reminder_d1(db)
    assert count2 == 0
    assert mock_send.call_count == 1


# ---------------------------------------------------------------------------
# CSV reminder D+3 tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_csv_reminder_d3_finds_eligible(
    mock_send: object, db: AsyncSession
) -> None:
    user = _make_user(
        created_at=datetime.now(timezone.utc) - timedelta(hours=72)
    )
    db.add(user)
    await db.flush()

    count = await send_csv_reminder_d3(db)
    assert count == 1


# ---------------------------------------------------------------------------
# NH sharing reminder tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_nh_sharing_reminder_finds_eligible(
    mock_send: object, db: AsyncSession
) -> None:
    user = _make_user(
        user_type="network_holder",
        created_at=datetime.now(timezone.utc) - timedelta(hours=72),
    )
    db.add(user)
    await db.flush()

    # Has CSV but no sharing prefs
    db.add(_make_csv_upload(user.id))
    await db.flush()

    count = await send_nh_sharing_reminder_d2(db)
    assert count == 1


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_nh_sharing_reminder_skips_opted_in(
    mock_send: object, db: AsyncSession
) -> None:
    user = _make_user(
        user_type="network_holder",
        created_at=datetime.now(timezone.utc) - timedelta(hours=72),
    )
    db.add(user)
    await db.flush()

    db.add(_make_csv_upload(user.id))
    db.add(NetworkSharingPreferences(
        user_id=user.id, opt_in_marketplace=True
    ))
    await db.flush()

    count = await send_nh_sharing_reminder_d2(db)
    assert count == 0


# ---------------------------------------------------------------------------
# First search nudge tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_first_search_nudge_finds_eligible(
    mock_send: object, db: AsyncSession
) -> None:
    user = _make_user(
        created_at=datetime.now(timezone.utc) - timedelta(hours=72),
    )
    db.add(user)
    await db.flush()

    db.add(_make_csv_upload(user.id))
    await db.flush()

    count = await send_first_search_nudge_d2(db)
    assert count == 1


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_first_search_nudge_skips_searched(
    mock_send: object, db: AsyncSession
) -> None:
    user = _make_user(
        created_at=datetime.now(timezone.utc) - timedelta(hours=72),
    )
    db.add(user)
    await db.flush()

    db.add(_make_csv_upload(user.id))
    db.add(SearchRequest(user_id=user.id, name="test search"))
    await db.flush()

    count = await send_first_search_nudge_d2(db)
    assert count == 0


# ---------------------------------------------------------------------------
# Intro pending reminder tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_intro_pending_reminder(
    mock_send: object, db: AsyncSession
) -> None:
    from app.models.company import Company
    from app.models.contact import Contact

    nh = _make_user(user_type="network_holder")
    js = _make_user(user_type="job_seeker")
    db.add_all([nh, js])
    await db.flush()

    # Create company + contact + listing chain
    company = Company(id=uuid.uuid4(), name="TestCo", domain="test.com")
    db.add(company)
    await db.flush()

    contact = Contact(
        user_id=nh.id, company_id=company.id,
        first_name="c", last_name="t", full_name="c t",
    )
    db.add(contact)
    await db.flush()

    listing = MarketplaceListing(
        network_holder_id=nh.id, contact_id=contact.id,
        company_id=company.id, role_level="mid",
        department_category="engineering",
        warm_score_range="60-80", connection_recency="recent",
    )
    db.add(listing)
    await db.flush()

    intro = IntroFacilitation(
        job_seeker_id=js.id, network_holder_id=nh.id,
        marketplace_listing_id=listing.id, status="requested",
        requested_at=datetime.now(timezone.utc) - timedelta(hours=26),
    )
    db.add(intro)
    await db.flush()

    count = await send_intro_pending_reminder(db)
    assert count == 1
    assert "pending intro request" in mock_send.call_args[0][2]


# ---------------------------------------------------------------------------
# Weekly digest tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_weekly_digest_for_active_user(
    mock_send: object, db: AsyncSession
) -> None:
    user = _make_user()
    db.add(user)
    await db.flush()

    # Add recent activity
    db.add(UsageLog(user_id=user.id, action="search"))
    await db.flush()

    count = await send_weekly_digest(db)
    assert count == 1
    assert "weekly digest" in mock_send.call_args[0][1].lower()


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_weekly_digest_skips_inactive(
    mock_send: object, db: AsyncSession
) -> None:
    user = _make_user()
    db.add(user)
    await db.flush()

    # No usage logs — no digest
    count = await send_weekly_digest(db)
    assert count == 0


# ---------------------------------------------------------------------------
# Re-engagement tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_reengagement_d30(mock_send: object, db: AsyncSession) -> None:
    user = _make_user()
    db.add(user)
    await db.flush()

    # Usage log from 30 days ago (in window)
    log = UsageLog(user_id=user.id, action="search")
    db.add(log)
    await db.flush()
    # Manually set created_at to 30 days ago
    from sqlalchemy import update
    await db.execute(
        update(UsageLog)
        .where(UsageLog.id == log.id)
        .values(created_at=datetime.now(timezone.utc) - timedelta(days=30))
    )
    await db.flush()

    count = await send_reengagement_d30(db)
    assert count == 1
    assert "month" in mock_send.call_args[0][2].lower()


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_reengagement_d30_skips_recent_users(
    mock_send: object, db: AsyncSession
) -> None:
    user = _make_user()
    db.add(user)
    await db.flush()

    # Usage log from today — still active
    db.add(UsageLog(user_id=user.id, action="search"))
    await db.flush()

    count = await send_reengagement_d30(db)
    assert count == 0


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_reengagement_d90(mock_send: object, db: AsyncSession) -> None:
    user = _make_user()
    db.add(user)
    await db.flush()

    log = UsageLog(user_id=user.id, action="search")
    db.add(log)
    await db.flush()
    from sqlalchemy import update
    await db.execute(
        update(UsageLog)
        .where(UsageLog.id == log.id)
        .values(created_at=datetime.now(timezone.utc) - timedelta(days=90))
    )
    await db.flush()

    count = await send_reengagement_d90(db)
    assert count == 1


# ---------------------------------------------------------------------------
# Marketing opt-out across batch functions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_batch_emails_respect_marketing_opt_out(
    mock_send: object, db: AsyncSession
) -> None:
    user = _make_user(
        marketing_opt_out=True,
        created_at=datetime.now(timezone.utc) - timedelta(hours=24),
    )
    db.add(user)
    await db.flush()

    count = await send_csv_reminder_d1(db)
    assert count == 0
    mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# Celery beat schedule test
# ---------------------------------------------------------------------------


def test_celery_beat_schedule_registered() -> None:
    from app.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "csv-reminder-d1" in schedule
    assert "csv-reminder-d3" in schedule
    assert "nh-sharing-d2" in schedule
    assert "first-search-d2" in schedule
    assert "intro-pending-24h" in schedule
    assert "weekly-digest" in schedule
    assert "reengagement-d30" in schedule
    assert "reengagement-d90" in schedule


def test_celery_tasks_importable() -> None:
    from app.tasks.email_tasks import (
        send_csv_reminder_d1,
        send_csv_reminder_d3,
        send_first_search_d2,
        send_intro_pending_24h,
        send_nh_sharing_d2,
        send_reengagement_d30,
        send_reengagement_d90,
        send_weekly_digest,
    )

    assert callable(send_csv_reminder_d1)
    assert callable(send_weekly_digest)
