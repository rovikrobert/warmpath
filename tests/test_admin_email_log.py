"""Tests for the admin email log endpoint — GET /api/v1/auth/admin/emails/{user_id}."""

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.conftest import TestSessionLocal, create_test_user_in_db

from app.models.email_campaign import EmailCampaignLog


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def admin_headers(client: AsyncClient) -> dict:
    """Create an admin user and return auth headers."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db,
            email="emaillogadmin@test.com",
            full_name="Email Log Admin",
            is_admin=True,
        )
    return headers


@pytest_asyncio.fixture
async def user_headers(client: AsyncClient) -> dict:
    """Create a non-admin user and return auth headers."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="emailloguser@test.com", full_name="Email Log User"
        )
    return headers


@pytest_asyncio.fixture
async def target_user_with_logs(client: AsyncClient) -> uuid.UUID:
    """Create a user with email campaign logs and return their ID."""
    async with TestSessionLocal() as db:
        user, _ = await create_test_user_in_db(
            db, email="emaillogtarget@test.com", full_name="Target User"
        )
        now = datetime.now(timezone.utc)
        for email_type in ("welcome", "csv_reminder_d1", "smart_digest"):
            log = EmailCampaignLog(
                user_id=user.id,
                email_type=email_type,
                sent_date=now.strftime("%Y-%m-%d"),
                sent_at=now,
                external_id=f"re_{uuid.uuid4().hex[:8]}",
            )
            db.add(log)
        await db.commit()
    return user.id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAdminEmailLog:
    @pytest.mark.asyncio
    async def test_admin_email_log_returns_logs(
        self,
        client: AsyncClient,
        admin_headers: dict,
        target_user_with_logs: uuid.UUID,
    ):
        """Admin can view email campaign logs for a user."""
        resp = await client.get(
            f"/api/v1/auth/admin/emails/{target_user_with_logs}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["count"] == 3
        assert len(body["data"]) == 3
        # Verify response shape
        first = body["data"][0]
        assert "email_type" in first
        assert "sent_date" in first
        assert "external_id" in first
        assert "created_at" in first
        # Verify all expected types present
        types = {log["email_type"] for log in body["data"]}
        assert types == {"welcome", "csv_reminder_d1", "smart_digest"}

    @pytest.mark.asyncio
    async def test_admin_email_log_rejects_non_admin(
        self,
        client: AsyncClient,
        user_headers: dict,
        target_user_with_logs: uuid.UUID,
    ):
        """Non-admin user gets 403 when trying to view email logs."""
        resp = await client.get(
            f"/api/v1/auth/admin/emails/{target_user_with_logs}",
            headers=user_headers,
        )
        assert resp.status_code == 403
        assert "Admin" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_admin_email_log_no_auth_returns_401(
        self,
        client: AsyncClient,
        target_user_with_logs: uuid.UUID,
    ):
        """Unauthenticated request returns 401."""
        resp = await client.get(
            f"/api/v1/auth/admin/emails/{target_user_with_logs}",
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_admin_email_log_empty_for_unknown_user(
        self,
        client: AsyncClient,
        admin_headers: dict,
    ):
        """Admin sees empty list for a user with no email logs."""
        fake_user_id = uuid.uuid4()
        resp = await client.get(
            f"/api/v1/auth/admin/emails/{fake_user_id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["count"] == 0
        assert body["data"] == []

    @pytest.mark.asyncio
    async def test_admin_email_log_invalid_uuid_returns_422(
        self,
        client: AsyncClient,
        admin_headers: dict,
    ):
        """Invalid UUID in path returns 422."""
        resp = await client.get(
            "/api/v1/auth/admin/emails/not-a-uuid",
            headers=admin_headers,
        )
        assert resp.status_code == 422
