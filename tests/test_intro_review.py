"""Tests for public intro review endpoint (GET /api/v1/intro-review/{token}).

Covers: valid token lookup, expired token, invalid token, rate limiting,
DELETE token revocation (auth + authorization), PII exclusion checks.
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.contact import Contact
from app.models.marketplace import IntroFacilitation, MarketplaceListing
from app.models.user import User
from tests.conftest import (
    TestSessionLocal,
    create_test_clerk_token,
    create_test_user_in_db,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(email: str | None = None, full_name: str = "Test User") -> User:
    return User(
        id=uuid.uuid4(),
        email=email or f"{uuid.uuid4().hex[:8]}@test.com",
        full_name=full_name,
        clerk_user_id=f"user_{uuid.uuid4().hex[:12]}",
    )


async def _setup_facilitation(
    db: AsyncSession,
    *,
    review_token: str | None = None,
    token_expires_at: datetime | None = None,
    js_full_name: str = "Sarah Johnson",
    nh_full_name: str = "Rovik Kumar",
    company_name: str = "Grab",
    js_profile_snapshot: dict | None = None,
    status: str = "approved",
    delivered_at: datetime | None = None,
    reviewed_at: datetime | None = None,
) -> tuple[User, User, IntroFacilitation, MarketplaceListing, Company]:
    """Create NH, JS, Company, Contact, Listing, Facilitation with review token."""
    js = _make_user(full_name=js_full_name)
    nh = _make_user(full_name=nh_full_name)
    db.add_all([js, nh])
    await db.flush()

    company = Company(name=company_name)
    db.add(company)
    await db.flush()

    contact = Contact(
        user_id=nh.id,
        company_id=company.id,
        first_name="Alex",
        last_name="Chen",
        full_name="Alex Chen",
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

    snapshot = (
        js_profile_snapshot
        if js_profile_snapshot is not None
        else {"headline": "Senior Product Manager"}
    )

    facilitation = IntroFacilitation(
        job_seeker_id=js.id,
        network_holder_id=nh.id,
        marketplace_listing_id=listing.id,
        status=status,
        reviewed_at=reviewed_at or datetime.now(timezone.utc),
        delivered_at=delivered_at,
        delivery_method="email_relay",
        delivery_status="sent",
        job_seeker_profile_snapshot=snapshot,
        review_token=review_token,
        review_token_expires_at=token_expires_at,
    )
    db.add(facilitation)
    await db.flush()

    return js, nh, facilitation, listing, company


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with TestSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# GET /api/v1/intro-review/{token}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_intro_review_returns_correct_data(
    client: AsyncClient, db: AsyncSession
):
    """Valid token returns non-PII intro summary with correct fields."""
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=90)
    delivered = datetime.now(timezone.utc) - timedelta(hours=1)

    js, nh, facilitation, listing, company = await _setup_facilitation(
        db,
        review_token=token,
        token_expires_at=expires,
        js_full_name="Sarah Johnson",
        nh_full_name="Rovik Kumar",
        company_name="Grab",
        delivered_at=delivered,
    )
    await db.commit()

    resp = await client.get(f"/api/v1/intro-review/{token}")
    assert resp.status_code == 200

    data = resp.json()["data"]
    assert data["job_seeker_first_name"] == "Sarah"
    assert data["job_seeker_headline"] == "Senior Product Manager"
    assert data["introducer_first_name"] == "Rovik"
    assert data["target_company"] == "Grab"
    assert data["status"] == "approved"
    assert data["sent_at"] is not None


@pytest.mark.asyncio
async def test_get_intro_review_expired_token_returns_404(
    client: AsyncClient, db: AsyncSession
):
    """Expired token returns 404."""
    token = secrets.token_urlsafe(32)
    expired = datetime.now(timezone.utc) - timedelta(days=1)

    await _setup_facilitation(
        db,
        review_token=token,
        token_expires_at=expired,
    )
    await db.commit()

    resp = await client.get(f"/api/v1/intro-review/{token}")
    assert resp.status_code == 404
    assert "expired" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_intro_review_invalid_token_returns_404(client: AsyncClient):
    """Non-existent token returns 404."""
    resp = await client.get("/api/v1/intro-review/totally_invalid_token_abc123")
    assert resp.status_code == 404
    assert "expired" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_intro_review_no_pii_leaked(client: AsyncClient, db: AsyncSession):
    """Response must NOT contain emails, full names, user IDs, or facilitation IDs."""
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=90)

    js, nh, facilitation, _, _ = await _setup_facilitation(
        db,
        review_token=token,
        token_expires_at=expires,
        js_full_name="Sarah Johnson",
        nh_full_name="Rovik Kumar",
    )
    await db.commit()

    resp = await client.get(f"/api/v1/intro-review/{token}")
    assert resp.status_code == 200
    body_text = resp.text

    # No full names
    assert "Johnson" not in body_text
    assert "Kumar" not in body_text

    # No emails
    assert "@test.com" not in body_text
    assert "@example.com" not in body_text

    # No UUIDs (user IDs, facilitation IDs)
    assert str(js.id) not in body_text
    assert str(nh.id) not in body_text
    assert str(facilitation.id) not in body_text


@pytest.mark.asyncio
async def test_get_intro_review_uses_reviewed_at_when_no_delivered_at(
    client: AsyncClient, db: AsyncSession
):
    """When delivered_at is None, sent_at falls back to reviewed_at."""
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=90)
    reviewed = datetime.now(timezone.utc) - timedelta(hours=2)

    await _setup_facilitation(
        db,
        review_token=token,
        token_expires_at=expires,
        delivered_at=None,
        reviewed_at=reviewed,
    )
    await db.commit()

    resp = await client.get(f"/api/v1/intro-review/{token}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["sent_at"] is not None


@pytest.mark.asyncio
async def test_get_intro_review_empty_headline_in_snapshot(
    client: AsyncClient, db: AsyncSession
):
    """When snapshot has no headline, returns empty string."""
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=90)

    await _setup_facilitation(
        db,
        review_token=token,
        token_expires_at=expires,
        js_profile_snapshot={},
    )
    await db.commit()

    resp = await client.get(f"/api/v1/intro-review/{token}")
    assert resp.status_code == 200
    assert resp.json()["data"]["job_seeker_headline"] == ""


# ---------------------------------------------------------------------------
# DELETE /api/v1/intro-review/{token} — revocation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_revokes_token_as_network_holder(
    client: AsyncClient, db: AsyncSession
):
    """NH can revoke the review token."""
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=90)

    _, nh, facilitation, _, _ = await _setup_facilitation(
        db,
        review_token=token,
        token_expires_at=expires,
    )
    await db.commit()

    nh_auth_token = create_test_clerk_token(nh.clerk_user_id)
    headers = {"Authorization": f"Bearer {nh_auth_token}"}

    resp = await client.delete(f"/api/v1/intro-review/{token}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["revoked"] is True

    # Verify token no longer works
    resp2 = await client.get(f"/api/v1/intro-review/{token}")
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_delete_revokes_token_as_job_seeker(
    client: AsyncClient, db: AsyncSession
):
    """JS can also revoke the review token."""
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=90)

    js, _, facilitation, _, _ = await _setup_facilitation(
        db,
        review_token=token,
        token_expires_at=expires,
    )
    await db.commit()

    js_auth_token = create_test_clerk_token(js.clerk_user_id)
    headers = {"Authorization": f"Bearer {js_auth_token}"}

    resp = await client.delete(f"/api/v1/intro-review/{token}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["revoked"] is True


@pytest.mark.asyncio
async def test_delete_forbidden_for_unrelated_user(
    client: AsyncClient, db: AsyncSession
):
    """An unrelated user cannot revoke the token."""
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=90)

    await _setup_facilitation(
        db,
        review_token=token,
        token_expires_at=expires,
    )

    # Create a different user
    other_user, other_headers = await create_test_user_in_db(
        db, email="other@test.com", full_name="Other User"
    )

    resp = await client.delete(f"/api/v1/intro-review/{token}", headers=other_headers)
    assert resp.status_code == 403
    assert "not authorized" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_nonexistent_token_returns_404(
    client: AsyncClient, db: AsyncSession
):
    """Deleting a non-existent token returns 404."""
    _, headers = await create_test_user_in_db(db, email="user@test.com")

    resp = await client.delete(
        "/api/v1/intro-review/nonexistent_token_xyz", headers=headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_requires_auth(client: AsyncClient):
    """DELETE without auth returns 401/403."""
    resp = await client.delete("/api/v1/intro-review/some_token")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_after_20_requests(client: AsyncClient, db: AsyncSession):
    """After 20 requests from same IP in a minute, returns 429."""
    from app.models.audit import AuditLog

    # First request to discover the IP address used by the test client
    await client.get("/api/v1/intro-review/probe_token")
    # The probe creates an audit log entry — read it to get the IP
    from sqlalchemy import select

    probe_result = await db.execute(
        select(AuditLog).where(AuditLog.action == "intro_review_access").limit(1)
    )
    probe_entry = probe_result.scalar_one_or_none()
    test_ip = probe_entry.ip_address if probe_entry else "127.0.0.1"

    # Pre-populate enough audit log entries to exceed the rate limit
    now = datetime.now(timezone.utc)
    for _ in range(20):
        db.add(
            AuditLog(
                action="intro_review_access",
                ip_address=test_ip,
                created_at=now - timedelta(seconds=10),
            )
        )
    await db.commit()

    resp = await client.get("/api/v1/intro-review/any_token_here")
    assert resp.status_code == 429
    assert "too many" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Model columns exist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_review_token_columns_on_model(db: AsyncSession):
    """Verify review_token and review_token_expires_at columns exist on IntroFacilitation."""
    js = _make_user()
    nh = _make_user()
    db.add_all([js, nh])
    await db.flush()

    company = Company(name="TestCo")
    db.add(company)
    await db.flush()

    contact = Contact(
        user_id=nh.id,
        company_id=company.id,
        first_name="Test",
        last_name="Contact",
        full_name="Test Contact",
    )
    db.add(contact)
    await db.flush()

    listing = MarketplaceListing(
        network_holder_id=nh.id,
        contact_id=contact.id,
        company_id=company.id,
        role_level="mid",
        department_category="engineering",
        warm_score_range="40-60",
        connection_recency="recent",
    )
    db.add(listing)
    await db.flush()

    token_val = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=90)

    fac = IntroFacilitation(
        job_seeker_id=js.id,
        network_holder_id=nh.id,
        marketplace_listing_id=listing.id,
        status="approved",
        review_token=token_val,
        review_token_expires_at=expires,
    )
    db.add(fac)
    await db.commit()
    await db.refresh(fac)

    assert fac.review_token == token_val
    assert fac.review_token_expires_at is not None
