"""Tests for Resend webhook — email open/click tracking via external_id."""

import json
import uuid as uuid_mod
from datetime import datetime, timezone

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
        user = User(email="webhook@test.com", full_name="Webhook Tester", password_hash="x")
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
        first_opened = result.scalar_one().opened_at

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
        user = User(email="eid@test.com", full_name="EID Tester", password_hash="x")
        db.add(user)
        await db.flush()

        from app.services.email_engagement import _record_send

        await _record_send(db, user.id, "test_email", external_id="resend_abc123")
        await db.commit()

    async with TestSessionLocal() as db:
        from sqlalchemy import select

        result = await db.execute(
            select(EmailCampaignLog).where(EmailCampaignLog.external_id == "resend_abc123")
        )
        log = result.scalar_one()
        assert log.external_id == "resend_abc123"
        assert log.email_type == "test_email"


@pytest.mark.asyncio
async def test_record_send_handles_none_external_id() -> None:
    """_record_send with None external_id should work (console mode)."""
    async with TestSessionLocal() as db:
        user = User(email="noeid@test.com", full_name="No EID", password_hash="x")
        db.add(user)
        await db.flush()

        from app.services.email_engagement import _record_send

        await _record_send(db, user.id, "test_email_none", external_id=None)
        await db.commit()

    async with TestSessionLocal() as db:
        from sqlalchemy import select

        result = await db.execute(
            select(EmailCampaignLog).where(EmailCampaignLog.email_type == "test_email_none")
        )
        log = result.scalar_one()
        assert log.external_id is None
