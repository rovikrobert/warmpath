"""Tests for the referral system — codes, redemption, conversions, leaderboard."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _signup(client: AsyncClient, email: str, name: str = "Test User") -> dict:
    """Sign up a user and return login response data."""
    await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Pass123!", "full_name": name},
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Pass123!"},
    )
    return login.json()["data"]


async def _headers(client: AsyncClient, email: str, name: str = "Test User") -> dict:
    """Sign up + login and return auth headers."""
    data = await _signup(client, email, name)
    return {"Authorization": f"Bearer {data['access_token']}"}


async def _verify_email(client: AsyncClient, email: str) -> None:
    """Verify a user's email directly via DB."""
    from tests.conftest import TestSessionLocal
    from sqlalchemy import update
    from app.models.user import User

    async with TestSessionLocal() as db:
        await db.execute(
            update(User)
            .where(User.email == email)
            .values(is_verified=True, email_verified=True)
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Test: Create referral code
# ---------------------------------------------------------------------------


async def test_create_nh_invite_code(client: AsyncClient):
    """Create a nh_invite referral code."""
    headers = await _headers(client, "referrer1@test.com", "Referrer One")
    await _verify_email(client, "referrer1@test.com")

    resp = await client.post(
        "/api/v1/referrals/create",
        json={"referral_type": "nh_invite"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["referral_type"] == "nh_invite"
    assert data["is_active"] is True
    assert data["uses_count"] == 0
    assert len(data["code"]) > 0
    assert data["credits_per_conversion"] == 25


async def test_create_js_invite_code(client: AsyncClient):
    """Create a js_invite referral code."""
    headers = await _headers(client, "referrer2@test.com", "Referrer Two")
    await _verify_email(client, "referrer2@test.com")

    resp = await client.post(
        "/api/v1/referrals/create",
        json={"referral_type": "js_invite"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["referral_type"] == "js_invite"
    assert data["credits_per_conversion"] == 50


async def test_create_targeted_invite(client: AsyncClient):
    """Create a targeted NH invite for a specific email."""
    headers = await _headers(client, "referrer3@test.com", "Referrer Three")
    await _verify_email(client, "referrer3@test.com")

    resp = await client.post(
        "/api/v1/referrals/create",
        json={
            "referral_type": "nh_invite",
            "target_email": "friend@company.com",
            "max_uses": 1,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["target_email"] == "friend@company.com"
    assert data["max_uses"] == 1


async def test_create_code_requires_auth(client: AsyncClient):
    """Unauthenticated request should fail."""
    resp = await client.post(
        "/api/v1/referrals/create",
        json={"referral_type": "nh_invite"},
    )
    assert resp.status_code in (401, 403)


async def test_create_code_requires_verified_email(client: AsyncClient):
    """Unverified users cannot create referral codes."""
    headers = await _headers(client, "unverified@test.com")
    resp = await client.post(
        "/api/v1/referrals/create",
        json={"referral_type": "nh_invite"},
        headers=headers,
    )
    assert resp.status_code == 403


async def test_create_code_invalid_type(client: AsyncClient):
    """Invalid referral_type should fail validation."""
    headers = await _headers(client, "referrer4@test.com")
    await _verify_email(client, "referrer4@test.com")

    resp = await client.post(
        "/api/v1/referrals/create",
        json={"referral_type": "bad_type"},
        headers=headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Test: List referral codes
# ---------------------------------------------------------------------------


async def test_list_my_codes(client: AsyncClient):
    """User can list their own referral codes."""
    headers = await _headers(client, "lister@test.com", "Lister")
    await _verify_email(client, "lister@test.com")

    # Create two codes
    await client.post(
        "/api/v1/referrals/create",
        json={"referral_type": "nh_invite"},
        headers=headers,
    )
    await client.post(
        "/api/v1/referrals/create",
        json={"referral_type": "js_invite"},
        headers=headers,
    )

    resp = await client.get("/api/v1/referrals/mine", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2
    types = {c["referral_type"] for c in data}
    assert types == {"nh_invite", "js_invite"}


# ---------------------------------------------------------------------------
# Test: Redeem referral code
# ---------------------------------------------------------------------------


async def test_redeem_code(client: AsyncClient):
    """New user can redeem a referral code."""
    # Create referrer
    referrer_headers = await _headers(client, "r_referrer@test.com", "Referrer")
    await _verify_email(client, "r_referrer@test.com")

    # Create code
    create_resp = await client.post(
        "/api/v1/referrals/create",
        json={"referral_type": "js_invite"},
        headers=referrer_headers,
    )
    code = create_resp.json()["data"]["code"]

    # Sign up new user and redeem
    new_headers = await _headers(client, "r_newuser@test.com", "New User")
    redeem_resp = await client.post(
        "/api/v1/referrals/redeem",
        json={"code": code},
        headers=new_headers,
    )
    assert redeem_resp.status_code == 200
    assert redeem_resp.json()["data"]["code"] == code

    # Verify uses_count incremented
    list_resp = await client.get("/api/v1/referrals/mine", headers=referrer_headers)
    codes = list_resp.json()["data"]
    redeemed = [c for c in codes if c["code"] == code][0]
    assert redeemed["uses_count"] == 1


async def test_redeem_self_referral_fails(client: AsyncClient):
    """Cannot redeem your own referral code."""
    headers = await _headers(client, "selfref@test.com", "Self Ref")
    await _verify_email(client, "selfref@test.com")

    create_resp = await client.post(
        "/api/v1/referrals/create",
        json={"referral_type": "js_invite"},
        headers=headers,
    )
    code = create_resp.json()["data"]["code"]

    redeem_resp = await client.post(
        "/api/v1/referrals/redeem",
        json={"code": code},
        headers=headers,
    )
    assert redeem_resp.status_code == 400
    assert "own referral" in redeem_resp.json()["detail"].lower()


async def test_redeem_invalid_code_fails(client: AsyncClient):
    """Invalid code returns 400."""
    headers = await _headers(client, "badcode@test.com")

    resp = await client.post(
        "/api/v1/referrals/redeem",
        json={"code": "NOTACODE"},
        headers=headers,
    )
    assert resp.status_code == 400


async def test_redeem_expired_code_fails(client: AsyncClient):
    """Expired codes cannot be redeemed."""
    from datetime import datetime, timedelta, timezone
    from tests.conftest import TestSessionLocal
    from sqlalchemy import update
    from app.models.referral import ReferralCode

    # Create referrer and code
    referrer_headers = await _headers(client, "expref@test.com", "Expired Referrer")
    await _verify_email(client, "expref@test.com")

    create_resp = await client.post(
        "/api/v1/referrals/create",
        json={"referral_type": "nh_invite"},
        headers=referrer_headers,
    )
    code = create_resp.json()["data"]["code"]

    # Expire the code
    async with TestSessionLocal() as db:
        await db.execute(
            update(ReferralCode)
            .where(ReferralCode.code == code)
            .values(expires_at=datetime.now(timezone.utc) - timedelta(days=1))
        )
        await db.commit()

    # Try to redeem
    new_headers = await _headers(client, "expredeemer@test.com")
    resp = await client.post(
        "/api/v1/referrals/redeem",
        json={"code": code},
        headers=new_headers,
    )
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"].lower()


async def test_redeem_exhausted_code_fails(client: AsyncClient):
    """Code at max_uses cannot be redeemed again."""
    referrer_headers = await _headers(client, "maxref@test.com", "Max Referrer")
    await _verify_email(client, "maxref@test.com")

    # Single-use code
    create_resp = await client.post(
        "/api/v1/referrals/create",
        json={"referral_type": "nh_invite", "max_uses": 1},
        headers=referrer_headers,
    )
    code = create_resp.json()["data"]["code"]

    # First user redeems
    user1_headers = await _headers(client, "maxuser1@test.com")
    resp1 = await client.post(
        "/api/v1/referrals/redeem", json={"code": code}, headers=user1_headers
    )
    assert resp1.status_code == 200

    # Second user tries
    user2_headers = await _headers(client, "maxuser2@test.com")
    resp2 = await client.post(
        "/api/v1/referrals/redeem", json={"code": code}, headers=user2_headers
    )
    assert resp2.status_code == 400
    assert "limit" in resp2.json()["detail"].lower()


async def test_redeem_duplicate_fails(client: AsyncClient):
    """Same user can't redeem the same code twice."""
    referrer_headers = await _headers(client, "dupref@test.com", "Dup Referrer")
    await _verify_email(client, "dupref@test.com")

    create_resp = await client.post(
        "/api/v1/referrals/create",
        json={"referral_type": "js_invite"},
        headers=referrer_headers,
    )
    code = create_resp.json()["data"]["code"]

    user_headers = await _headers(client, "dupuser@test.com")
    resp1 = await client.post(
        "/api/v1/referrals/redeem", json={"code": code}, headers=user_headers
    )
    assert resp1.status_code == 200

    resp2 = await client.post(
        "/api/v1/referrals/redeem", json={"code": code}, headers=user_headers
    )
    assert resp2.status_code == 400
    assert "already" in resp2.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test: Leaderboard
# ---------------------------------------------------------------------------


async def test_leaderboard_empty(client: AsyncClient):
    """Leaderboard returns empty list when no referrals exist."""
    headers = await _headers(client, "lb_empty@test.com")

    resp = await client.get("/api/v1/referrals/leaderboard", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"] == []


async def test_leaderboard_with_referrals(client: AsyncClient):
    """Leaderboard shows referrers ranked by conversions."""
    # Create referrer with a code
    referrer_headers = await _headers(client, "lb_referrer@test.com", "LB Referrer")
    await _verify_email(client, "lb_referrer@test.com")

    create_resp = await client.post(
        "/api/v1/referrals/create",
        json={"referral_type": "js_invite"},
        headers=referrer_headers,
    )
    code = create_resp.json()["data"]["code"]

    # New user redeems
    user_headers = await _headers(client, "lb_user@test.com", "LB User")
    await client.post(
        "/api/v1/referrals/redeem", json={"code": code}, headers=user_headers
    )

    # Check leaderboard
    resp = await client.get("/api/v1/referrals/leaderboard", headers=referrer_headers)
    assert resp.status_code == 200
    entries = resp.json()["data"]
    assert len(entries) >= 1
    assert entries[0]["full_name"] == "LB Referrer"
    assert entries[0]["total_conversions"] >= 1


# ---------------------------------------------------------------------------
# Test: Conversion tracking (service-level)
# ---------------------------------------------------------------------------


async def test_record_conversion_awards_credits(client: AsyncClient):
    """Recording a conversion event awards credits to the referrer."""
    from tests.conftest import TestSessionLocal
    from app.services.referral_service import record_conversion
    from app.services.credits import get_balance
    from app.models.user import User
    from sqlalchemy import select

    # Create referrer and referred user via API
    referrer_headers = await _headers(client, "conv_ref@test.com", "Conv Referrer")
    await _verify_email(client, "conv_ref@test.com")

    create_resp = await client.post(
        "/api/v1/referrals/create",
        json={"referral_type": "js_invite"},
        headers=referrer_headers,
    )
    code = create_resp.json()["data"]["code"]

    # New user redeems
    user_headers = await _headers(client, "conv_user@test.com", "Conv User")
    await client.post(
        "/api/v1/referrals/redeem", json={"code": code}, headers=user_headers
    )

    # Simulate a conversion event
    async with TestSessionLocal() as db:
        referred = (
            await db.execute(
                select(User).where(User.email == "conv_user@test.com")
            )
        ).scalar_one()
        referrer = (
            await db.execute(
                select(User).where(User.email == "conv_ref@test.com")
            )
        ).scalar_one()

        # Record csv_upload conversion
        conversion = await record_conversion(referred.id, "csv_upload", db)
        assert conversion is not None
        assert conversion.conversion_event == "csv_upload"
        assert conversion.credits_awarded == 50  # js_invite rate

        await db.commit()

        # Check referrer got credits
        balance = await get_balance(referrer.id, db)
        assert balance >= 50

        # Duplicate conversion should return None
        dup = await record_conversion(referred.id, "csv_upload", db)
        assert dup is None
