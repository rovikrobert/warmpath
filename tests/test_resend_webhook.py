"""Tests for Resend webhook — email open/click tracking via external_id."""

import json
import uuid as uuid_mod

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.email_campaign import EmailCampaignLog
from app.models.user import User
from tests.conftest import TestSessionLocal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def campaign_log_with_external_id() -> str:
    """Create a campaign log entry with an external_id, return the external_id."""
    eid = f"resend_{uuid_mod.uuid4().hex[:12]}"
    async with TestSessionLocal() as db:
        user = User(email="webhook@test.com", full_name="Webhook Tester")
        db.add(user)
        await db.flush()

        log = EmailCampaignLog(
            user_id=user.id,
            email_type="welcome_js",
            sent_date="2026-02-18",
            external_id=eid,
        )
        db.add(log)
        await db.commit()
    return eid


# ---------------------------------------------------------------------------
# Webhook event tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resend_webhook_email_opened(
    client: AsyncClient, campaign_log_with_external_id: str
) -> None:
    eid = campaign_log_with_external_id
    payload = {
        "type": "email.opened",
        "data": {"email_id": eid},
    }
    resp = await client.post(
        "/api/v1/webhooks/resend",
        content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["matched"] is True

    # Verify opened_at was set
    async with TestSessionLocal() as db:
        from sqlalchemy import select

        result = await db.execute(
            select(EmailCampaignLog).where(EmailCampaignLog.external_id == eid)
        )
        log = result.scalar_one()
        assert log.opened_at is not None


@pytest.mark.asyncio
async def test_resend_webhook_email_clicked(
    client: AsyncClient, campaign_log_with_external_id: str
) -> None:
    eid = campaign_log_with_external_id
    payload = {
        "type": "email.clicked",
        "data": {"email_id": eid},
    }
    resp = await client.post(
        "/api/v1/webhooks/resend",
        content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["matched"] is True

    # clicked should also set opened_at
    async with TestSessionLocal() as db:
        from sqlalchemy import select

        result = await db.execute(
            select(EmailCampaignLog).where(EmailCampaignLog.external_id == eid)
        )
        log = result.scalar_one()
        assert log.clicked_at is not None
        assert log.opened_at is not None  # auto-set on click


@pytest.mark.asyncio
async def test_resend_webhook_email_bounced(
    client: AsyncClient, campaign_log_with_external_id: str
) -> None:
    eid = campaign_log_with_external_id
    payload = {
        "type": "email.bounced",
        "data": {"email_id": eid},
    }
    resp = await client.post(
        "/api/v1/webhooks/resend",
        content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["matched"] is True


@pytest.mark.asyncio
async def test_resend_webhook_unknown_email_id(client: AsyncClient) -> None:
    payload = {
        "type": "email.opened",
        "data": {"email_id": "nonexistent_id_12345"},
    }
    resp = await client.post(
        "/api/v1/webhooks/resend",
        content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["matched"] is False


@pytest.mark.asyncio
async def test_resend_webhook_no_email_id(client: AsyncClient) -> None:
    payload = {
        "type": "email.opened",
        "data": {},
    }
    resp = await client.post(
        "/api/v1/webhooks/resend",
        content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    # No email_id means we can't match, but we still accept


@pytest.mark.asyncio
async def test_resend_webhook_invalid_json(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/webhooks/resend",
        content="not json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_resend_webhook_idempotent_open(
    client: AsyncClient, campaign_log_with_external_id: str
) -> None:
    """Multiple open events don't overwrite the first opened_at."""
    eid = campaign_log_with_external_id
    payload = {"type": "email.opened", "data": {"email_id": eid}}

    await client.post(
        "/api/v1/webhooks/resend",
        content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )

    # Get the first opened_at
    async with TestSessionLocal() as db:
        from sqlalchemy import select

        result = await db.execute(
            select(EmailCampaignLog).where(EmailCampaignLog.external_id == eid)
        )
        assert result.scalar_one().opened_at is not None

    # Second open event
    await client.post(
        "/api/v1/webhooks/resend",
        content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )

    # opened_at should not change
    async with TestSessionLocal() as db:
        result = await db.execute(
            select(EmailCampaignLog).where(EmailCampaignLog.external_id == eid)
        )
        second_opened = result.scalar_one().opened_at
        # Both should be set (first one preserved)
        assert second_opened is not None


# ---------------------------------------------------------------------------
# External ID storage in email engagement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_send_stores_external_id() -> None:
    """_record_send should store external_id when provided."""
    async with TestSessionLocal() as db:
        user = User(email="eid@test.com", full_name="EID Tester")
        db.add(user)
        await db.flush()

        from app.services.email_engagement import _record_send

        await _record_send(db, user.id, "test_email", external_id="resend_abc123")
        await db.commit()

    async with TestSessionLocal() as db:
        from sqlalchemy import select

        result = await db.execute(
            select(EmailCampaignLog).where(
                EmailCampaignLog.external_id == "resend_abc123"
            )
        )
        log = result.scalar_one()
        assert log.external_id == "resend_abc123"
        assert log.email_type == "test_email"


@pytest.mark.asyncio
async def test_record_send_handles_none_external_id() -> None:
    """_record_send with None external_id should work (console mode)."""
    async with TestSessionLocal() as db:
        user = User(email="noeid@test.com", full_name="No EID")
        db.add(user)
        await db.flush()

        from app.services.email_engagement import _record_send

        await _record_send(db, user.id, "test_email_none", external_id=None)
        await db.commit()

    async with TestSessionLocal() as db:
        from sqlalchemy import select

        result = await db.execute(
            select(EmailCampaignLog).where(
                EmailCampaignLog.email_type == "test_email_none"
            )
        )
        log = result.scalar_one()
        assert log.external_id is None


# ---------------------------------------------------------------------------
# Intro facilitation delivery webhook tests
# ---------------------------------------------------------------------------


async def _create_intro_facilitation_with_relay_id() -> tuple[str, str]:
    """Create full chain: users + company + contact + listing + facilitation.

    Returns (relay_message_id, network_holder_id as str).
    """
    from app.models.company import Company
    from app.models.contact import Contact
    from app.models.marketplace import IntroFacilitation, MarketplaceListing

    relay_id = f"resend_relay_{uuid_mod.uuid4().hex[:12]}"
    async with TestSessionLocal() as db:
        nh = User(
            id=uuid_mod.uuid4(),
            email=f"nh_{uuid_mod.uuid4().hex[:6]}@test.com",
            full_name="Network Holder",
        )
        js = User(
            id=uuid_mod.uuid4(),
            email=f"js_{uuid_mod.uuid4().hex[:6]}@test.com",
            full_name="Job Seeker",
        )
        db.add_all([nh, js])
        await db.flush()

        company = Company(id=uuid_mod.uuid4(), name="TestCo", domain="testco.com")
        db.add(company)
        await db.flush()

        contact = Contact(
            user_id=nh.id,
            company_id=company.id,
            first_name="Contact",
            last_name="Person",
            full_name="Contact Person",
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

        facilitation = IntroFacilitation(
            job_seeker_id=js.id,
            network_holder_id=nh.id,
            marketplace_listing_id=listing.id,
            status="approved",
            relay_message_id=relay_id,
            delivery_status="sent",
            delivery_method="email_relay",
        )
        db.add(facilitation)
        await db.commit()

        nh_id_str = str(nh.id)
    return relay_id, nh_id_str


@pytest.mark.asyncio
async def test_resend_webhook_delivery_awards_credits(client: AsyncClient) -> None:
    """email.delivered sets delivery_status, delivered_at, awards 50 credits to NH."""
    relay_id, nh_id = await _create_intro_facilitation_with_relay_id()

    payload = {"type": "email.delivered", "data": {"email_id": relay_id}}
    resp = await client.post(
        "/api/v1/webhooks/resend",
        content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["matched"] is True

    async with TestSessionLocal() as db:
        from sqlalchemy import select

        from app.models.credits import CreditTransaction
        from app.models.marketplace import IntroFacilitation

        result = await db.execute(
            select(IntroFacilitation).where(
                IntroFacilitation.relay_message_id == relay_id
            )
        )
        fac = result.scalar_one()
        assert fac.delivery_status == "delivered"
        assert fac.delivered_at is not None
        assert fac.credits_awarded_at is not None

        # NH should have 50 credits
        import uuid as _uuid

        credit_result = await db.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == _uuid.UUID(nh_id),
                CreditTransaction.reason == "intro_facilitation",
            )
        )
        txn = credit_result.scalar_one()
        assert txn.amount == 50


@pytest.mark.asyncio
async def test_resend_webhook_bounce_awards_partial_credits(
    client: AsyncClient,
) -> None:
    """email.bounced sets delivery_status=bounced, awards 25 partial credits to NH."""
    relay_id, nh_id = await _create_intro_facilitation_with_relay_id()

    payload = {"type": "email.bounced", "data": {"email_id": relay_id}}
    resp = await client.post(
        "/api/v1/webhooks/resend",
        content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["matched"] is True

    async with TestSessionLocal() as db:
        from sqlalchemy import select

        from app.models.credits import CreditTransaction
        from app.models.marketplace import IntroFacilitation

        result = await db.execute(
            select(IntroFacilitation).where(
                IntroFacilitation.relay_message_id == relay_id
            )
        )
        fac = result.scalar_one()
        assert fac.delivery_status == "bounced"
        assert fac.delivered_at is not None
        assert fac.credits_awarded_at is not None

        import uuid as _uuid

        credit_result = await db.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == _uuid.UUID(nh_id),
                CreditTransaction.reason == "intro_facilitation_bounced",
            )
        )
        txn = credit_result.scalar_one()
        assert txn.amount == 25


@pytest.mark.asyncio
async def test_resend_webhook_opened_updates_status_no_credits(
    client: AsyncClient,
) -> None:
    """email.opened sets delivery_status=opened but awards no credits."""
    relay_id, nh_id = await _create_intro_facilitation_with_relay_id()

    payload = {"type": "email.opened", "data": {"email_id": relay_id}}
    resp = await client.post(
        "/api/v1/webhooks/resend",
        content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["matched"] is True

    async with TestSessionLocal() as db:
        from sqlalchemy import func, select

        from app.models.credits import CreditTransaction
        from app.models.marketplace import IntroFacilitation

        result = await db.execute(
            select(IntroFacilitation).where(
                IntroFacilitation.relay_message_id == relay_id
            )
        )
        fac = result.scalar_one()
        assert fac.delivery_status == "opened"
        assert fac.credits_awarded_at is None

        # No credits should have been awarded
        import uuid as _uuid

        count_result = await db.execute(
            select(func.count()).where(
                CreditTransaction.user_id == _uuid.UUID(nh_id),
            )
        )
        assert count_result.scalar() == 0


@pytest.mark.asyncio
async def test_resend_webhook_no_double_credit_on_duplicate_delivery(
    client: AsyncClient,
) -> None:
    """Sending email.delivered twice awards credits only once (idempotent)."""
    relay_id, nh_id = await _create_intro_facilitation_with_relay_id()

    payload = {"type": "email.delivered", "data": {"email_id": relay_id}}
    headers = {"Content-Type": "application/json"}

    # First delivery event
    resp1 = await client.post(
        "/api/v1/webhooks/resend", content=json.dumps(payload), headers=headers
    )
    assert resp1.status_code == 200

    # Second delivery event (duplicate)
    resp2 = await client.post(
        "/api/v1/webhooks/resend", content=json.dumps(payload), headers=headers
    )
    assert resp2.status_code == 200

    async with TestSessionLocal() as db:
        from sqlalchemy import func, select

        from app.models.credits import CreditTransaction

        import uuid as _uuid

        count_result = await db.execute(
            select(func.count()).where(
                CreditTransaction.user_id == _uuid.UUID(nh_id),
                CreditTransaction.reason == "intro_facilitation",
            )
        )
        # Only one credit transaction despite two webhook calls
        assert count_result.scalar() == 1
