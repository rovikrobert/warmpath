"""End-to-end integration tests for the intro relay and LinkedIn fallback flows.

Tests:
  1. Full email relay flow: NH approves -> relay email -> Resend delivery webhook -> credits
  2. Full LinkedIn fallback flow: no email -> approve -> confirm-sent -> credits
  3. Relay bounce with partial credits: approve -> Resend bounce webhook -> 25 credits
"""

import json
import uuid as uuid_mod
from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.models.company import Company
from app.models.contact import Contact
from app.models.marketplace import (
    ConnectorReputation,
    MarketplaceListing,
    NetworkSharingPreferences,
)
from app.models.match_result import WarmScore
from app.services.credits import earn_credits, get_balance
from tests.conftest import TestSessionLocal, create_test_user_in_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_verified_user_with_credits(
    email: str, full_name: str, credits: int = 200
) -> tuple[dict, str]:
    """Create a verified user, award credits, return (auth_dict, user_id_str).

    auth_dict has keys: headers, user_id.
    """
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email=email, full_name=full_name, email_verified=True
        )
        if credits > 0:
            await earn_credits(user.id, credits, "test_grant", db)
            await db.commit()
        user_id = str(user.id)
    return {"headers": headers, "user_id": user_id}, user_id


async def _setup_marketplace_with_email(
    holder_user_id: str,
) -> dict:
    """Create company + contact (WITH email + LinkedIn) + listing for holder.

    Returns dict with company_id, contact_id, listing_id.
    """
    holder_uid = uuid_mod.UUID(holder_user_id)

    async with TestSessionLocal() as db:
        company = Company(name="Relay Corp", domain="relaycorp.com")
        db.add(company)
        await db.flush()

        contact = Contact(
            user_id=holder_uid,
            full_name="Contact Relay",
            first_name="Contact",
            last_name="Relay",
            email="contact.relay@relaycorp.com",
            linkedin_url="https://linkedin.com/in/contact-relay",
            current_title="Senior Engineer",
            current_company="Relay Corp",
            company_id=company.id,
            connected_on=date.today() - timedelta(days=60),
        )
        db.add(contact)
        await db.flush()

        db.add(
            WarmScore(
                user_id=holder_uid,
                contact_id=contact.id,
                total_score=85,
                recency_score=90,
                tenu[RESEND_KEY_REDACTED]=75,
                context_score=80,
                role_score=85,
                referral_likelihood="high",
            )
        )

        db.add(NetworkSharingPreferences(user_id=holder_uid, opt_in_marketplace=True))
        await db.flush()

        listing = MarketplaceListing(
            network_holder_id=holder_uid,
            contact_id=contact.id,
            company_id=company.id,
            role_level="senior",
            department_category="engineering",
            warm_sco[RESEND_KEY_REDACTED]="high",
            connection_recency="recent",
        )
        db.add(listing)
        await db.flush()

        db.add(
            ConnectorReputation(
                user_id=holder_uid,
                intros_facilitated=3,
                response_rate=100,
                avg_rating=5,
            )
        )
        await db.commit()

        return {
            "company_id": company.id,
            "contact_id": contact.id,
            "listing_id": listing.id,
        }


async def _setup_marketplace_no_email(
    holder_user_id: str,
) -> dict:
    """Create company + contact (NO email, has LinkedIn) + listing for holder.

    Returns dict with company_id, contact_id, listing_id.
    """
    holder_uid = uuid_mod.UUID(holder_user_id)

    async with TestSessionLocal() as db:
        company = Company(name="LinkedIn Only Inc", domain="linkedinonly.com")
        db.add(company)
        await db.flush()

        contact = Contact(
            user_id=holder_uid,
            full_name="Diana LinkedIn",
            first_name="Diana",
            last_name="LinkedIn",
            email=None,
            linkedin_url="https://linkedin.com/in/diana-linkedin",
            current_title="Staff Engineer",
            current_company="LinkedIn Only Inc",
            company_id=company.id,
            connected_on=date.today() - timedelta(days=90),
        )
        db.add(contact)
        await db.flush()

        db.add(
            WarmScore(
                user_id=holder_uid,
                contact_id=contact.id,
                total_score=75,
                recency_score=80,
                tenu[RESEND_KEY_REDACTED]=70,
                context_score=75,
                role_score=70,
                referral_likelihood="high",
            )
        )

        db.add(NetworkSharingPreferences(user_id=holder_uid, opt_in_marketplace=True))
        await db.flush()

        listing = MarketplaceListing(
            network_holder_id=holder_uid,
            contact_id=contact.id,
            company_id=company.id,
            role_level="lead",
            department_category="engineering",
            warm_sco[RESEND_KEY_REDACTED]="high",
            connection_recency="recent",
        )
        db.add(listing)
        await db.flush()

        db.add(
            ConnectorReputation(
                user_id=holder_uid,
                intros_facilitated=5,
                response_rate=90,
                avg_rating=5,
            )
        )
        await db.commit()

        return {
            "company_id": company.id,
            "contact_id": contact.id,
            "listing_id": listing.id,
        }


# ---------------------------------------------------------------------------
# Test 1: Full email relay flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_intro_relay_flow(client: AsyncClient) -> None:
    """Full email relay flow: create users, request intro, approve (relay),
    simulate Resend delivery webhook, verify credits awarded to NH."""

    # -- Step 1: Create NH and JS users with credits --------------------------
    nh_auth, nh_id = await _create_verified_user_with_credits(
        "nh_relay@test.com", "Network Holder Relay", credits=0
    )
    js_auth, js_id = await _create_verified_user_with_credits(
        "js_relay@test.com", "Job Seeker Relay", credits=200
    )

    # -- Step 2: Set up marketplace with contact that HAS email ---------------
    mkt = await _setup_marketplace_with_email(nh_id)
    listing_id = str(mkt["listing_id"])

    # -- Step 3: JS requests intro (costs 20 credits) -------------------------
    intro_resp = await client.post(
        "/api/v1/marketplace/request-intro",
        json={
            "marketplace_listing_id": listing_id,
            "message_to_holder": "Interested in a referral for SWE role",
            "profile_visibility": "summary",
        },
        headers=js_auth["headers"],
    )
    assert intro_resp.status_code == 201
    facilitation = intro_resp.json()["data"]
    facilitation_id = facilitation["id"]
    assert facilitation["status"] == "requested"

    # Verify JS credits deducted (200 - 20 = 180)
    js_uid = uuid_mod.UUID(js_id)
    async with TestSessionLocal() as db:
        js_balance = await get_balance(js_uid, db)
    assert js_balance == 180

    # -- Step 4: NH approves the request (email relay path) -------------------
    approve_resp = await client.patch(
        f"/api/v1/marketplace/requests/{facilitation_id}",
        json={"action": "approve", "notes": "Happy to help!"},
        headers=nh_auth["headers"],
    )
    assert approve_resp.status_code == 200
    approved_data = approve_resp.json()["data"]
    assert approved_data["status"] == "approved"
    assert approved_data["delivery_method"] == "email_relay"
    # In test mode RESEND_API_KEY is empty, so relay returns None -> "failed"
    assert approved_data["delivery_status"] in ("sent", "failed")
    assert approved_data["credits_awarded_at"] is None

    # -- Step 5: Verify NH does NOT have credits yet (deferred) ---------------
    nh_uid = uuid_mod.UUID(nh_id)
    async with TestSessionLocal() as db:
        nh_balance_before = await get_balance(nh_uid, db)
    assert nh_balance_before == 0

    # -- Step 6: Set up relay_message_id manually for webhook test ------------
    # In test env, send_intro_relay_email returns None (no RESEND_API_KEY).
    # We manually set a relay_message_id so we can simulate the webhook.
    relay_message_id = f"resend_relay_{uuid_mod.uuid4().hex[:12]}"
    async with TestSessionLocal() as db:
        from sqlalchemy import select

        from app.models.marketplace import IntroFacilitation

        result = await db.execute(
            select(IntroFacilitation).where(
                IntroFacilitation.id == uuid_mod.UUID(facilitation_id)
            )
        )
        fac = result.scalar_one()
        fac.relay_message_id = relay_message_id
        fac.delivery_status = "sent"
        await db.commit()

    # -- Step 7: Simulate Resend delivery webhook -----------------------------
    webhook_payload = {
        "type": "email.delivered",
        "data": {"email_id": relay_message_id},
    }
    webhook_resp = await client.post(
        "/api/v1/webhooks/resend",
        content=json.dumps(webhook_payload),
        headers={"Content-Type": "application/json"},
    )
    assert webhook_resp.status_code == 200
    assert webhook_resp.json()["data"]["matched"] is True

    # -- Step 8: Verify delivery status and credits awarded -------------------
    async with TestSessionLocal() as db:
        result = await db.execute(
            select(IntroFacilitation).where(
                IntroFacilitation.id == uuid_mod.UUID(facilitation_id)
            )
        )
        fac = result.scalar_one()
        assert fac.delivery_status == "delivered"
        assert fac.delivered_at is not None
        assert fac.credits_awarded_at is not None

    # -- Step 9: Verify NH earned 50 credits ----------------------------------
    async with TestSessionLocal() as db:
        nh_balance_after = await get_balance(nh_uid, db)
    assert nh_balance_after == 50


# ---------------------------------------------------------------------------
# Test 2: Full LinkedIn fallback flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_linkedin_fallback_flow(client: AsyncClient) -> None:
    """LinkedIn fallback flow: contact has no email, NH approves,
    gets LinkedIn URL + drafted message, confirms manual send, earns credits."""

    # -- Step 1: Create NH and JS users with credits --------------------------
    nh_auth, nh_id = await _create_verified_user_with_credits(
        "nh_linkedin@test.com", "Network Holder LinkedIn", credits=0
    )
    js_auth, js_id = await _create_verified_user_with_credits(
        "js_linkedin@test.com", "Job Seeker LinkedIn", credits=200
    )

    # -- Step 2: Set up marketplace with contact that has NO email -------------
    mkt = await _setup_marketplace_no_email(nh_id)
    listing_id = str(mkt["listing_id"])

    # -- Step 3: JS requests intro (costs 20 credits) -------------------------
    intro_resp = await client.post(
        "/api/v1/marketplace/request-intro",
        json={
            "marketplace_listing_id": listing_id,
            "message_to_holder": "Looking for a referral at LinkedIn Only Inc",
            "profile_visibility": "summary",
        },
        headers=js_auth["headers"],
    )
    assert intro_resp.status_code == 201
    facilitation = intro_resp.json()["data"]
    facilitation_id = facilitation["id"]
    assert facilitation["status"] == "requested"

    # -- Step 4: NH approves (LinkedIn fallback path) -------------------------
    approve_resp = await client.patch(
        f"/api/v1/marketplace/requests/{facilitation_id}",
        json={"action": "approve"},
        headers=nh_auth["headers"],
    )
    assert approve_resp.status_code == 200
    approved_data = approve_resp.json()["data"]
    assert approved_data["status"] == "approved"
    # No email relay — delivery_method should be None
    assert approved_data["delivery_method"] is None
    # LinkedIn fallback provides URL and drafted message
    assert approved_data["linkedin_url"] == "https://linkedin.com/in/diana-linkedin"
    assert approved_data["drafted_message"] is not None
    assert "Diana" in approved_data["drafted_message"]
    # Credits NOT awarded yet
    assert approved_data["credits_awarded_at"] is None

    # -- Step 5: Verify NH has NOT earned credits yet -------------------------
    nh_uid = uuid_mod.UUID(nh_id)
    async with TestSessionLocal() as db:
        nh_balance = await get_balance(nh_uid, db)
    assert nh_balance == 0

    # -- Step 6: NH confirms manual send via confirm-sent endpoint ------------
    confirm_resp = await client.post(
        f"/api/v1/marketplace/requests/{facilitation_id}/confirm-sent",
        headers=nh_auth["headers"],
    )
    assert confirm_resp.status_code == 200
    confirm_data = confirm_resp.json()["data"]
    assert confirm_data["status"] == "confirmed"
    assert confirm_data["credits_awarded"] == 50

    # -- Step 7: Verify NH earned 50 credits ----------------------------------
    async with TestSessionLocal() as db:
        nh_balance_after = await get_balance(nh_uid, db)
    assert nh_balance_after == 50

    # -- Step 8: Verify delivery tracking fields set correctly -----------------
    async with TestSessionLocal() as db:
        from sqlalchemy import select

        from app.models.marketplace import IntroFacilitation

        result = await db.execute(
            select(IntroFacilitation).where(
                IntroFacilitation.id == uuid_mod.UUID(facilitation_id)
            )
        )
        fac = result.scalar_one()
        assert fac.delivery_method == "linkedin_manual"
        assert fac.delivery_status == "delivered"
        assert fac.delivered_at is not None
        assert fac.credits_awarded_at is not None


# ---------------------------------------------------------------------------
# Test 3: Relay bounce with partial credits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_relay_bounce_partial_credits(client: AsyncClient) -> None:
    """Email relay bounce: NH approves, Resend reports bounce,
    NH earns 25 partial credits (not 50) for the effort."""

    # -- Step 1: Create NH and JS users with credits --------------------------
    nh_auth, nh_id = await _create_verified_user_with_credits(
        "nh_bounce@test.com", "Network Holder Bounce", credits=0
    )
    js_auth, js_id = await _create_verified_user_with_credits(
        "js_bounce@test.com", "Job Seeker Bounce", credits=200
    )

    # -- Step 2: Set up marketplace with contact that HAS email ---------------
    mkt = await _setup_marketplace_with_email(nh_id)
    listing_id = str(mkt["listing_id"])

    # -- Step 3: JS requests intro --------------------------------------------
    intro_resp = await client.post(
        "/api/v1/marketplace/request-intro",
        json={
            "marketplace_listing_id": listing_id,
            "message_to_holder": "Referral request for bounce test",
            "profile_visibility": "summary",
        },
        headers=js_auth["headers"],
    )
    assert intro_resp.status_code == 201
    facilitation_id = intro_resp.json()["data"]["id"]

    # -- Step 4: NH approves (email relay path) -------------------------------
    approve_resp = await client.patch(
        f"/api/v1/marketplace/requests/{facilitation_id}",
        json={"action": "approve"},
        headers=nh_auth["headers"],
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["data"]["status"] == "approved"
    assert approve_resp.json()["data"]["delivery_method"] == "email_relay"

    # -- Step 5: Set relay_message_id for webhook simulation ------------------
    relay_message_id = f"resend_bounce_{uuid_mod.uuid4().hex[:12]}"
    async with TestSessionLocal() as db:
        from sqlalchemy import select

        from app.models.marketplace import IntroFacilitation

        result = await db.execute(
            select(IntroFacilitation).where(
                IntroFacilitation.id == uuid_mod.UUID(facilitation_id)
            )
        )
        fac = result.scalar_one()
        fac.relay_message_id = relay_message_id
        fac.delivery_status = "sent"
        await db.commit()

    # -- Step 6: Simulate Resend BOUNCE webhook -------------------------------
    webhook_payload = {
        "type": "email.bounced",
        "data": {"email_id": relay_message_id},
    }
    webhook_resp = await client.post(
        "/api/v1/webhooks/resend",
        content=json.dumps(webhook_payload),
        headers={"Content-Type": "application/json"},
    )
    assert webhook_resp.status_code == 200
    assert webhook_resp.json()["data"]["matched"] is True

    # -- Step 7: Verify delivery status is "bounced" --------------------------
    async with TestSessionLocal() as db:
        result = await db.execute(
            select(IntroFacilitation).where(
                IntroFacilitation.id == uuid_mod.UUID(facilitation_id)
            )
        )
        fac = result.scalar_one()
        assert fac.delivery_status == "bounced"
        assert fac.delivered_at is not None
        assert fac.credits_awarded_at is not None

    # -- Step 8: Verify NH earned 25 partial credits (not 50) -----------------
    nh_uid = uuid_mod.UUID(nh_id)
    async with TestSessionLocal() as db:
        nh_balance = await get_balance(nh_uid, db)
    assert nh_balance == 25
