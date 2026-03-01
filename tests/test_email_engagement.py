"""Tests for the email engagement system — model, service, dedup, triggers."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import TestSessionLocal

from app.models.contact import CsvUpload
from app.models.email_campaign import EmailCampaignLog
from app.models.enrichment import UsageLog
from app.models.marketplace import (
    IntroFacilitation,
    MarketplaceListing,
    NetworkSharingPreferences,
)
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
    intent: str | None = "find_referrals",
    created_at: datetime | None = None,
    marketing_opt_out: bool = False,
) -> User:
    return User(
        id=uuid.uuid4(),
        email=email or f"{uuid.uuid4().hex[:8]}@test.com",
        full_name="Test User",
        intent=intent,
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
async def db(truncate_tables) -> AsyncSession:
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
    with pytest.raises(IntegrityError):
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
    assert "welcome credits" in mock_send.call_args[0][1].lower()

    # Verify dedup
    result2 = await send_welcome_email_js(user, db)
    assert result2 is False
    assert mock_send.call_count == 1  # not called again


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_welcome_email_nh(mock_send: object, db: AsyncSession) -> None:
    user = _make_user(intent="share_network")
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
    user = _make_user(created_at=datetime.now(timezone.utc) - timedelta(hours=24))
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
    user = _make_user(created_at=datetime.now(timezone.utc) - timedelta(hours=24))
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
    user = _make_user(created_at=datetime.now(timezone.utc) - timedelta(hours=2))
    db.add(user)
    await db.flush()

    count = await send_csv_reminder_d1(db)
    assert count == 0


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_csv_reminder_d1_dedup(mock_send: object, db: AsyncSession) -> None:
    user = _make_user(created_at=datetime.now(timezone.utc) - timedelta(hours=24))
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
    user = _make_user(created_at=datetime.now(timezone.utc) - timedelta(hours=72))
    db.add(user)
    await db.flush()

    # D3 requires D1 to have been sent first
    d1_log = EmailCampaignLog(
        user_id=user.id,
        email_type="csv_reminder_d1",
        sent_date=(datetime.now(timezone.utc) - timedelta(hours=48)).strftime(
            "%Y-%m-%d"
        ),
    )
    db.add(d1_log)
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
        intent="share_network",
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
        intent="share_network",
        created_at=datetime.now(timezone.utc) - timedelta(hours=72),
    )
    db.add(user)
    await db.flush()

    db.add(_make_csv_upload(user.id))
    db.add(NetworkSharingPreferences(user_id=user.id, opt_in_marketplace=True))
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
async def test_intro_pending_reminder(mock_send: object, db: AsyncSession) -> None:
    from app.models.company import Company
    from app.models.contact import Contact

    nh = _make_user(intent="share_network")
    js = _make_user(intent="find_referrals")
    db.add_all([nh, js])
    await db.flush()

    # Create company + contact + listing chain
    company = Company(id=uuid.uuid4(), name="TestCo", domain="test.com")
    db.add(company)
    await db.flush()

    contact = Contact(
        user_id=nh.id,
        company_id=company.id,
        first_name="c",
        last_name="t",
        full_name="c t",
    )
    db.add(contact)
    await db.flush()

    listing = MarketplaceListing(
        network_holder_id=nh.id,
        contact_id=contact.id,
        company_id=company.id,
        role_level="mid",
        department_category="engineering",
        warm_score_range="60-80",
        connection_recency="recent",
    )
    db.add(listing)
    await db.flush()

    intro = IntroFacilitation(
        job_seeker_id=js.id,
        network_holder_id=nh.id,
        marketplace_listing_id=listing.id,
        status="requested",
        requested_at=datetime.now(timezone.utc) - timedelta(hours=26),
    )
    db.add(intro)
    await db.flush()

    count = await send_intro_pending_reminder(db)
    assert count == 1
    assert "intro request" in mock_send.call_args[0][2]


# ---------------------------------------------------------------------------
# Intro request immediate notification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_intro_request_notification_sends_email_to_nh(
    mock_send: object, db: AsyncSession
) -> None:
    """When a job seeker requests an intro, NH gets an immediate email with company name."""
    from app.models.company import Company
    from app.models.contact import Contact
    from app.services.email_engagement import send_intro_request_notification

    nh = _make_user(intent="share_network")
    js = _make_user(intent="find_referrals")
    db.add_all([nh, js])
    await db.flush()

    company = Company(id=uuid.uuid4(), name="Stripe", domain="stripe.com")
    db.add(company)
    await db.flush()

    contact = Contact(
        user_id=nh.id,
        company_id=company.id,
        first_name="c",
        last_name="t",
        full_name="c t",
    )
    db.add(contact)
    await db.flush()

    listing = MarketplaceListing(
        network_holder_id=nh.id,
        contact_id=contact.id,
        company_id=company.id,
        role_level="senior",
        department_category="engineering",
        warm_score_range="60-80",
        connection_recency="recent",
    )
    db.add(listing)
    await db.flush()

    intro = IntroFacilitation(
        job_seeker_id=js.id,
        network_holder_id=nh.id,
        marketplace_listing_id=listing.id,
        status="requested",
        job_seeker_profile_snapshot={"full_name": "Test Seeker"},
    )
    db.add(intro)
    await db.flush()

    result = await send_intro_request_notification(
        nh_user=nh,
        company_name="Stripe",
        role_level="senior",
        job_seeker_snapshot={"full_name": "Test Seeker"},
        facilitation_id=intro.id,
        db=db,
    )

    assert result is True
    mock_send.assert_called_once()
    html = mock_send.call_args[0][2]
    assert "Stripe" in html
    assert "referral" in html.lower()


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_intro_request_notification_skips_opted_out_nh(
    mock_send: object, db: AsyncSession
) -> None:
    """NH with marketing_opt_out=True should not receive the email."""
    from app.services.email_engagement import send_intro_request_notification

    nh = _make_user(intent="share_network", marketing_opt_out=True)
    db.add(nh)
    await db.flush()

    result = await send_intro_request_notification(
        nh_user=nh,
        company_name="Stripe",
        role_level="senior",
        job_seeker_snapshot={},
        facilitation_id=uuid.uuid4(),
        db=db,
    )

    assert result is False
    mock_send.assert_not_called()


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
        send_weekly_digest,
    )

    assert callable(send_csv_reminder_d1)
    assert callable(send_weekly_digest)


# ---------------------------------------------------------------------------
# Intro relay email tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_intro_relay_email_sends_with_correct_from_and_reply_to(
    mock_send: object, db: AsyncSession
) -> None:
    """Intro relay email uses NH name in from and NH email as reply-to."""
    from app.services.email_engagement import send_intro_relay_email

    mock_send.return_value = "resend-msg-123"

    facilitation_id = uuid.uuid4()
    eid = await send_intro_relay_email(
        to_email="contact@example.com",
        nh_name="Alice Wong",
        nh_email="alice@company.com",
        job_seeker_name="Bob Smith",
        job_seeker_role="Senior Engineer",
        target_company="Stripe",
        intro_message="<p>Hi, I'd like to introduce Bob...</p>",
        nh_referral_code="ALICE123",
        db=db,
        facilitation_id=facilitation_id,
    )

    assert eid == "resend-msg-123"
    mock_send.assert_called_once()

    # Verify positional args: to, subject, html
    call_args = mock_send.call_args
    assert call_args[0][0] == "contact@example.com"
    assert "Introduction: Bob Smith" in call_args[0][1]
    assert "Senior Engineer at Stripe" in call_args[0][1]

    # Verify keyword args: reply_to and from_email
    assert call_args[1]["reply_to"] == "alice@company.com"
    assert "Alice Wong via WarmPath" in call_args[1]["from_email"]
    assert "intro@majiq.agency" in call_args[1]["from_email"]


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_intro_relay_email_html_contains_stop_opt_out(
    mock_send: object, db: AsyncSession
) -> None:
    """Relay email HTML must contain the STOP opt-out text."""
    from app.services.email_engagement import send_intro_relay_email

    mock_send.return_value = "msg-1"

    await send_intro_relay_email(
        to_email="contact@example.com",
        nh_name="Alice Wong",
        nh_email="alice@company.com",
        job_seeker_name="Bob Smith",
        job_seeker_role="Senior Engineer",
        target_company="Stripe",
        intro_message="<p>Hello there</p>",
        nh_referral_code="ALICE123",
        db=db,
        facilitation_id=uuid.uuid4(),
    )

    html = mock_send.call_args[0][2]
    assert "STOP" in html
    assert "opt out" in html.lower()


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_intro_relay_email_html_contains_share_network_cta(
    mock_send: object, db: AsyncSession
) -> None:
    """Relay email footer should recruit new NHs with referral link."""
    from app.services.email_engagement import send_intro_relay_email

    mock_send.return_value = "msg-2"

    await send_intro_relay_email(
        to_email="contact@example.com",
        nh_name="Alice Wong",
        nh_email="alice@company.com",
        job_seeker_name="Bob Smith",
        job_seeker_role="Senior Engineer",
        target_company="Stripe",
        intro_message="<p>Hello there</p>",
        nh_referral_code="ALICE123",
        db=db,
        facilitation_id=uuid.uuid4(),
    )

    html = mock_send.call_args[0][2]
    assert "Share your network" in html
    assert "/join?ref=ALICE123" in html


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_intro_relay_email_html_contains_intro_message_body(
    mock_send: object, db: AsyncSession
) -> None:
    """The AI-drafted intro message should appear in the email body."""
    from app.services.email_engagement import send_intro_relay_email

    mock_send.return_value = "msg-3"

    intro_text = "<p>Hi, Bob is a great engineer with 7 years of experience.</p>"
    await send_intro_relay_email(
        to_email="contact@example.com",
        nh_name="Alice Wong",
        nh_email="alice@company.com",
        job_seeker_name="Bob Smith",
        job_seeker_role="Senior Engineer",
        target_company="Stripe",
        intro_message=intro_text,
        nh_referral_code="ALICE123",
        db=db,
        facilitation_id=uuid.uuid4(),
    )

    html = mock_send.call_args[0][2]
    assert intro_text in html


@pytest.mark.asyncio
@patch("app.services.email_engagement._send_email")
async def test_intro_relay_email_dedup_prevents_duplicate_send(
    mock_send: object, db: AsyncSession
) -> None:
    """Second send for the same facilitation_id should be skipped."""
    from app.services.email_engagement import send_intro_relay_email

    mock_send.return_value = "msg-first"
    facilitation_id = uuid.uuid4()

    kwargs = dict(
        to_email="contact@example.com",
        nh_name="Alice Wong",
        nh_email="alice@company.com",
        job_seeker_name="Bob Smith",
        job_seeker_role="Senior Engineer",
        target_company="Stripe",
        intro_message="<p>Hello</p>",
        nh_referral_code="ALICE123",
        db=db,
        facilitation_id=facilitation_id,
    )

    eid1 = await send_intro_relay_email(**kwargs)
    assert eid1 == "msg-first"
    assert mock_send.call_count == 1

    # Second call — same facilitation_id
    eid2 = await send_intro_relay_email(**kwargs)
    assert eid2 is None
    assert mock_send.call_count == 1  # not called again
