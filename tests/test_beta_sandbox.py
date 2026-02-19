"""Tests for beta sandbox mode — relaxed limits, welcome credits, API flag."""

import json
import uuid
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.middleware.usage_logger import (
    _BETA_FREE_TIER_LIMITS,
    _STANDARD_FREE_TIER_LIMITS,
    get_free_tier_limits,
)
from app.models.credits import CreditTransaction
from app.models.user import User
from tests.conftest import TestSessionLocal, create_test_user_in_db

SAMPLE_CSV = (
    "First Name,Last Name,Email Address,Company,Position,Connected On\n"
    "Alice,Smith,alice@example.com,Acme Corp,CEO,{recent}\n"
).format(recent=(date.today() - timedelta(days=30)).strftime("%d %b %Y"))


async def _signup(client: AsyncClient, email: str = "beta@test.com") -> dict:
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email=email, full_name="Beta User"
        )
    return {"headers": headers, "user_id": str(user.id)}


# ---------------------------------------------------------------------------
# get_free_tier_limits()
# ---------------------------------------------------------------------------


def test_beta_limits_a[RESEND_KEY_REDACTED](monkeypatch):
    """With beta on, get_free_tier_limits() returns the relaxed beta values."""
    from app.config import settings

    monkeypatch.setattr(settings, "BETA_SANDBOX_MODE", True)
    limits = get_free_tier_limits()
    assert limits is _BETA_FREE_TIER_LIMITS
    assert limits["smart_search"] == 25
    assert limits["marketplace_search"] == 15
    assert limits["intro_request"] == 10


def test_standard_limits_without_beta(monkeypatch):
    """With beta off, get_free_tier_limits() returns standard values."""
    from app.config import settings

    monkeypatch.setattr(settings, "BETA_SANDBOX_MODE", False)
    limits = get_free_tier_limits()
    assert limits is _STANDARD_FREE_TIER_LIMITS
    assert limits["smart_search"] == 3
    assert limits["marketplace_search"] == 0


# ---------------------------------------------------------------------------
# Clerk webhook — welcome credits
# ---------------------------------------------------------------------------


async def test_beta_welcome_credits_500(client: AsyncClient, monkeypatch):
    """user.created webhook with beta on grants 500 welcome credits."""
    from app.config import settings

    monkeypatch.setattr(settings, "BETA_SANDBOX_MODE", True)

    clerk_id = f"user_{uuid.uuid4().hex[:12]}"
    payload = {
        "type": "user.created",
        "data": {
            "id": clerk_id,
            "email_addresses": [
                {
                    "email_address": "beta500@test.com",
                    "verification": {"status": "verified"},
                }
            ],
            "first_name": "Beta",
            "last_name": "Tester",
        },
    }
    resp = await client.post(
        "/api/v1/webhooks/clerk",
        content=json.dumps(payload),
        headers={"content-type": "application/json", "x-webhook-test": "true"},
    )
    assert resp.status_code == 200

    async with TestSessionLocal() as db:
        result = await db.execute(select(User).where(User.clerk_user_id == clerk_id))
        user = result.scalar_one()
        credits_result = await db.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == user.id,
                CreditTransaction.reason == "welcome_bonus",
            )
        )
        bonus = credits_result.scalar_one()
        assert bonus.amount == 500


async def test_standard_welcome_credits_50(client: AsyncClient, monkeypatch):
    """user.created webhook with beta off grants 50 welcome credits."""
    from app.config import settings

    monkeypatch.setattr(settings, "BETA_SANDBOX_MODE", False)

    clerk_id = f"user_{uuid.uuid4().hex[:12]}"
    payload = {
        "type": "user.created",
        "data": {
            "id": clerk_id,
            "email_addresses": [
                {
                    "email_address": "standard50@test.com",
                    "verification": {"status": "verified"},
                }
            ],
            "first_name": "Standard",
            "last_name": "User",
        },
    }
    resp = await client.post(
        "/api/v1/webhooks/clerk",
        content=json.dumps(payload),
        headers={"content-type": "application/json", "x-webhook-test": "true"},
    )
    assert resp.status_code == 200

    async with TestSessionLocal() as db:
        result = await db.execute(select(User).where(User.clerk_user_id == clerk_id))
        user = result.scalar_one()
        credits_result = await db.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == user.id,
                CreditTransaction.reason == "welcome_bonus",
            )
        )
        bonus = credits_result.scalar_one()
        assert bonus.amount == 50


# ---------------------------------------------------------------------------
# GET /usage/me — beta flag and limits
# ---------------------------------------------------------------------------


async def test_usage_summary_includes_beta_flag(client: AsyncClient, monkeypatch):
    """Response includes beta_sandbox: true when beta mode is on."""
    from app.config import settings

    monkeypatch.setattr(settings, "BETA_SANDBOX_MODE", True)
    auth = await _signup(client, "beta_flag@test.com")

    resp = await client.get("/api/v1/usage/me", headers=auth["headers"])
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["beta_sandbox"] is True


async def test_usage_summary_beta_limits_reflected(client: AsyncClient, monkeypatch):
    """Beta mode sets marketplace_search limit to 15, not 0."""
    from app.config import settings

    monkeypatch.setattr(settings, "BETA_SANDBOX_MODE", True)
    auth = await _signup(client, "beta_limits@test.com")

    resp = await client.get("/api/v1/usage/me", headers=auth["headers"])
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["limits"]["marketplace_search"] == 15
    assert body["limits"]["smart_search"] == 25
    assert body["limits"]["intro_request"] == 10


async def test_beta_no_marketplace_block_warning(client: AsyncClient, monkeypatch):
    """Free user in beta mode doesn't get 'requires paid plan' warning for marketplace."""
    from app.config import settings

    monkeypatch.setattr(settings, "BETA_SANDBOX_MODE", True)
    auth = await _signup(client, "beta_no_block@test.com")

    resp = await client.post(
        "/api/v1/marketplace/search",
        headers=auth["headers"],
        json={"company_names": ["Stripe"]},
    )
    warning = resp.headers.get("x-warmpath-usage-warning", "")
    # Should NOT contain "paid plan" — beta users get relaxed limits
    assert "paid plan" not in warning.lower()
