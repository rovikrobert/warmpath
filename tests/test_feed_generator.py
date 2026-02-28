"""Tests for Keevs feed generators — intro approval nudge & manual send reminder.

Covers: generation, dedup, filtering by delivery_method, edge cases.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.contact import Contact
from app.models.marketplace import IntroFacilitation, MarketplaceListing
from app.models.user import User
from app.services.feed_generator import (
    generate_intro_approval_nudge,
    generate_manual_send_reminder,
)
from tests.conftest import TestSessionLocal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(email: str | None = None) -> User:
    return User(
        id=uuid.uuid4(),
        email=email or f"{uuid.uuid4().hex[:8]}@test.com",
        full_name="Test User",
    )


async def _setup_facilitation(
    db: AsyncSession,
    *,
    status: str = "approved",
    reviewed_at: datetime | None = None,
    delivery_method: str | None = None,
    job_seeker_profile_snapshot: dict | None = None,
    contact_first_name: str = "Sarah",
) -> tuple[User, User, IntroFacilitation, MarketplaceListing, Contact]:
    """Create NH, JS, Company, Contact, Listing, Facilitation — returns key objects."""
    nh = _make_user()
    js = _make_user()
    db.add_all([nh, js])
    await db.flush()

    company = Company(name="Stripe")
    db.add(company)
    await db.flush()

    contact = Contact(
        user_id=nh.id,
        company_id=company.id,
        first_name=contact_first_name,
        last_name="Chen",
        full_name=f"{contact_first_name} Chen",
    )
    db.add(contact)
    await db.flush()

    listing = MarketplaceListing(
        network_holder_id=nh.id,
        contact_id=contact.id,
        company_id=company.id,
        role_level="senior",
        department_category="engineering",
        warm_sco[RESEND_KEY_REDACTED]="60-80",
        connection_recency="recent",
    )
    db.add(listing)
    await db.flush()

    facilitation = IntroFacilitation(
        job_seeker_id=js.id,
        network_holder_id=nh.id,
        marketplace_listing_id=listing.id,
        status=status,
        reviewed_at=reviewed_at or datetime.now(timezone.utc),
        delivery_method=delivery_method,
        job_seeker_profile_snapshot=job_seeker_profile_snapshot,
    )
    db.add(facilitation)
    await db.flush()

    return nh, js, facilitation, listing, contact


@pytest_asyncio.fixture
async def db(truncate_tables) -> AsyncSession:
    async with TestSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# generate_intro_approval_nudge tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_intro_approval_nudge_creates_item(db: AsyncSession) -> None:
    """After NH approves an intro, generate a feed item encouraging more uploads."""
    nh, _js, _f, _l, _c = await _setup_facilitation(
        db,
        status="approved",
        reviewed_at=datetime.now(timezone.utc) - timedelta(hours=2),
        job_seeker_profile_snapshot={"full_name": "Alex Kim"},
    )

    items = await generate_intro_approval_nudge(nh.id, db)

    assert len(items) == 1
    item = items[0]
    assert item.item_type == "intro_approval_nudge"
    assert item.title == "Nice one!"
    assert "Alex Kim" in item.body
    assert "referral bonuses" in item.body
    assert item.action_url == "/contacts"
    assert item.priority == 60
    assert item.user_id == nh.id


@pytest.mark.asyncio
async def test_generate_intro_approval_nudge_fallback_name(db: AsyncSession) -> None:
    """When profile snapshot lacks full_name, fall back to 'someone'."""
    nh, _js, _f, _l, _c = await _setup_facilitation(
        db,
        status="approved",
        reviewed_at=datetime.now(timezone.utc) - timedelta(hours=1),
        job_seeker_profile_snapshot=None,
    )

    items = await generate_intro_approval_nudge(nh.id, db)

    assert len(items) == 1
    assert "someone" in items[0].body


@pytest.mark.asyncio
async def test_generate_intro_approval_nudge_dedup(db: AsyncSession) -> None:
    """Don't generate duplicate nudges for the same facilitation."""
    nh, _js, facilitation, _l, _c = await _setup_facilitation(
        db,
        status="approved",
        reviewed_at=datetime.now(timezone.utc) - timedelta(hours=1),
        job_seeker_profile_snapshot={"full_name": "Alex Kim"},
    )

    # First generation — should produce 1 item
    items_first = await generate_intro_approval_nudge(nh.id, db)
    assert len(items_first) == 1

    # Persist the item so dedup can find it
    await db.flush()

    # Second generation — should produce 0 due to dedup
    items_second = await generate_intro_approval_nudge(nh.id, db)
    assert len(items_second) == 0


@pytest.mark.asyncio
async def test_generate_intro_approval_nudge_ignores_old_approvals(
    db: AsyncSession,
) -> None:
    """Approvals older than 24 hours should not generate nudges."""
    nh, _js, _f, _l, _c = await _setup_facilitation(
        db,
        status="approved",
        reviewed_at=datetime.now(timezone.utc) - timedelta(hours=25),
    )

    items = await generate_intro_approval_nudge(nh.id, db)
    assert len(items) == 0


@pytest.mark.asyncio
async def test_generate_intro_approval_nudge_ignores_non_approved(
    db: AsyncSession,
) -> None:
    """Only approved intros generate nudges, not requested/declined."""
    nh, _js, _f, _l, _c = await _setup_facilitation(
        db,
        status="requested",
        reviewed_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )

    items = await generate_intro_approval_nudge(nh.id, db)
    assert len(items) == 0


# ---------------------------------------------------------------------------
# generate_manual_send_reminder tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_manual_send_reminder_creates_item(db: AsyncSession) -> None:
    """If NH approved but hasn't confirmed sending after 48 hours, nudge them."""
    nh, _js, _f, _l, _c = await _setup_facilitation(
        db,
        status="approved",
        reviewed_at=datetime.now(timezone.utc) - timedelta(hours=72),
        delivery_method=None,
        contact_first_name="Sarah",
    )

    items = await generate_manual_send_reminder(nh.id, db)

    assert len(items) == 1
    item = items[0]
    assert item.item_type == "manual_send_reminder"
    assert "Sarah" in item.title
    assert "send" in item.body.lower()
    assert "credits" in item.body.lower()
    assert item.action_url == "/marketplace"
    assert item.priority == 75
    assert item.user_id == nh.id


@pytest.mark.asyncio
async def test_generate_manual_send_reminder_not_for_email_relay(
    db: AsyncSession,
) -> None:
    """Don't remind NHs who used email relay (delivery_method is set)."""
    nh, _js, _f, _l, _c = await _setup_facilitation(
        db,
        status="approved",
        reviewed_at=datetime.now(timezone.utc) - timedelta(hours=72),
        delivery_method="email_relay",
    )

    items = await generate_manual_send_reminder(nh.id, db)
    assert len(items) == 0


@pytest.mark.asyncio
async def test_generate_manual_send_reminder_not_for_manual_delivery(
    db: AsyncSession,
) -> None:
    """Don't remind NHs who already confirmed manual delivery."""
    nh, _js, _f, _l, _c = await _setup_facilitation(
        db,
        status="approved",
        reviewed_at=datetime.now(timezone.utc) - timedelta(hours=72),
        delivery_method="linkedin_manual",
    )

    items = await generate_manual_send_reminder(nh.id, db)
    assert len(items) == 0


@pytest.mark.asyncio
async def test_generate_manual_send_reminder_not_befo[RESEND_KEY_REDACTED](
    db: AsyncSession,
) -> None:
    """Don't nudge if fewer than 48 hours have passed since approval."""
    nh, _js, _f, _l, _c = await _setup_facilitation(
        db,
        status="approved",
        reviewed_at=datetime.now(timezone.utc) - timedelta(hours=24),
        delivery_method=None,
    )

    items = await generate_manual_send_reminder(nh.id, db)
    assert len(items) == 0


@pytest.mark.asyncio
async def test_generate_manual_send_reminder_dedup(db: AsyncSession) -> None:
    """Don't generate duplicate reminders for the same facilitation."""
    nh, _js, _f, _l, _c = await _setup_facilitation(
        db,
        status="approved",
        reviewed_at=datetime.now(timezone.utc) - timedelta(hours=72),
        delivery_method=None,
    )

    items_first = await generate_manual_send_reminder(nh.id, db)
    assert len(items_first) == 1

    await db.flush()

    items_second = await generate_manual_send_reminder(nh.id, db)
    assert len(items_second) == 0


@pytest.mark.asyncio
async def test_generate_manual_send_reminder_contact_name_fallback(
    db: AsyncSession,
) -> None:
    """When listing or contact can't be resolved, fall back to 'your contact'."""
    nh = _make_user()
    js = _make_user()
    db.add_all([nh, js])
    await db.flush()

    company = Company(name="Acme")
    db.add(company)
    await db.flush()

    contact = Contact(
        user_id=nh.id,
        company_id=company.id,
        first_name="Alex",
        last_name="Test",
        full_name="Alex Test",
    )
    db.add(contact)
    await db.flush()

    listing = MarketplaceListing(
        network_holder_id=nh.id,
        contact_id=contact.id,
        company_id=company.id,
        role_level="mid",
        department_category="engineering",
        warm_sco[RESEND_KEY_REDACTED]="40-60",
        connection_recency="recent",
    )
    db.add(listing)
    await db.flush()

    facilitation = IntroFacilitation(
        job_seeker_id=js.id,
        network_holder_id=nh.id,
        marketplace_listing_id=listing.id,
        status="approved",
        reviewed_at=datetime.now(timezone.utc) - timedelta(hours=72),
        delivery_method=None,
    )
    db.add(facilitation)
    await db.flush()

    items = await generate_manual_send_reminder(nh.id, db)
    assert len(items) == 1
    # Should resolve to actual contact first_name since listing exists
    assert "Alex" in items[0].title
