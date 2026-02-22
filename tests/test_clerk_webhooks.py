"""Tests for Clerk webhook endpoint (user lifecycle sync)."""

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.credits import CreditTransaction
from app.models.user import User
from tests.conftest import TestSessionLocal


@pytest.fixture(autouse=True)
def _disable_beta_sandbox(monkeypatch):
    """Ensure standard (non-beta) limits for all tests in this module."""
    from app.config import settings

    monkeypatch.setattr(settings, "BETA_SANDBOX_MODE", False)


async def test_webhook_user_created_creates_db_user_with_welcome_credits(
    client: AsyncClient,
):
    """user.created event creates a user row and awards 50 welcome credits."""
    clerk_id = f"user_{uuid.uuid4().hex[:12]}"
    payload = {
        "type": "user.created",
        "data": {
            "id": clerk_id,
            "email_addresses": [
                {
                    "email_address": "newclerk@test.com",
                    "verification": {"status": "verified"},
                }
            ],
            "first_name": "Jane",
            "last_name": "Smith",
            "primary_email_address_id": "idn_123",
        },
    }
    resp = await client.post(
        "/api/v1/webhooks/clerk",
        content=json.dumps(payload),
        headers={
            "content-type": "application/json",
            "x-webhook-test": "true",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["received"] is True

    # Verify user was created
    async with TestSessionLocal() as db:
        result = await db.execute(select(User).where(User.clerk_user_id == clerk_id))
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.email == "newclerk@test.com"
        assert user.full_name == "Jane Smith"
        assert user.email_verified is True

        # Verify welcome credits (50)
        credits_result = await db.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == user.id,
                CreditTransaction.reason == "welcome_bonus",
            )
        )
        bonus = credits_result.scalar_one_or_none()
        assert bonus is not None
        assert bonus.amount == 50


async def test_webhook_user_updated_syncs_email_and_name(client: AsyncClient):
    """user.updated event syncs email and name changes."""
    clerk_id = f"user_{uuid.uuid4().hex[:12]}"

    # Pre-create user
    async with TestSessionLocal() as db:
        user = User(
            email="old@test.com",
            full_name="Old Name",
            clerk_user_id=clerk_id,
        )
        db.add(user)
        await db.commit()

    payload = {
        "type": "user.updated",
        "data": {
            "id": clerk_id,
            "email_addresses": [
                {
                    "email_address": "new@test.com",
                    "verification": {"status": "verified"},
                }
            ],
            "first_name": "New",
            "last_name": "Name",
            "primary_email_address_id": "idn_456",
        },
    }
    resp = await client.post(
        "/api/v1/webhooks/clerk",
        content=json.dumps(payload),
        headers={
            "content-type": "application/json",
            "x-webhook-test": "true",
        },
    )
    assert resp.status_code == 200

    async with TestSessionLocal() as db:
        result = await db.execute(select(User).where(User.clerk_user_id == clerk_id))
        user = result.scalar_one()
        assert user.email == "new@test.com"
        assert user.full_name == "New Name"
        assert user.email_verified is True


async def test_webhook_user_deleted_removes_user(client: AsyncClient):
    """user.deleted event hard-deletes the user."""
    clerk_id = f"user_{uuid.uuid4().hex[:12]}"

    async with TestSessionLocal() as db:
        user = User(
            email="delete@test.com",
            full_name="Delete Me",
            clerk_user_id=clerk_id,
        )
        db.add(user)
        await db.commit()

    payload = {
        "type": "user.deleted",
        "data": {"id": clerk_id},
    }
    resp = await client.post(
        "/api/v1/webhooks/clerk",
        content=json.dumps(payload),
        headers={
            "content-type": "application/json",
            "x-webhook-test": "true",
        },
    )
    assert resp.status_code == 200

    async with TestSessionLocal() as db:
        result = await db.execute(select(User).where(User.clerk_user_id == clerk_id))
        assert result.scalar_one_or_none() is None


async def test_webhook_ignores_unknown_event_type(client: AsyncClient):
    """Unknown event type returns 200 (acknowledge but ignore)."""
    payload = {"type": "org.created", "data": {"id": "org_123"}}
    resp = await client.post(
        "/api/v1/webhooks/clerk",
        content=json.dumps(payload),
        headers={
            "content-type": "application/json",
            "x-webhook-test": "true",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["received"] is True


async def test_webhook_duplicate_user_created_is_idempotent(client: AsyncClient):
    """Duplicate user.created for same clerk_id doesn't crash."""
    clerk_id = f"user_{uuid.uuid4().hex[:12]}"

    # Pre-create user
    async with TestSessionLocal() as db:
        user = User(
            email="existing@test.com",
            full_name="Existing",
            clerk_user_id=clerk_id,
        )
        db.add(user)
        await db.commit()

    payload = {
        "type": "user.created",
        "data": {
            "id": clerk_id,
            "email_addresses": [
                {
                    "email_address": "existing@test.com",
                    "verification": {"status": "verified"},
                }
            ],
            "first_name": "Existing",
            "last_name": "User",
            "primary_email_address_id": "idn_789",
        },
    }
    resp = await client.post(
        "/api/v1/webhooks/clerk",
        content=json.dumps(payload),
        headers={
            "content-type": "application/json",
            "x-webhook-test": "true",
        },
    )
    assert resp.status_code == 200


async def test_webhook_user_created_relinks_existing_email_to_new_clerk_id(
    client: AsyncClient,
):
    """user.created with a new clerk_id but existing email re-links instead of crashing."""
    old_clerk_id = f"user_{uuid.uuid4().hex[:12]}"
    new_clerk_id = f"user_{uuid.uuid4().hex[:12]}"
    email = "relink@test.com"

    # Pre-create user with old clerk_id
    async with TestSessionLocal() as db:
        user = User(
            email=email,
            full_name="Original Name",
            clerk_user_id=old_clerk_id,
        )
        db.add(user)
        await db.commit()
        original_user_id = user.id

    # Webhook arrives with new clerk_id but same email (e.g. re-signup via different OAuth)
    payload = {
        "type": "user.created",
        "data": {
            "id": new_clerk_id,
            "email_addresses": [
                {
                    "email_address": email,
                    "verification": {"status": "verified"},
                }
            ],
            "first_name": "Updated",
            "last_name": "Name",
        },
    }
    resp = await client.post(
        "/api/v1/webhooks/clerk",
        content=json.dumps(payload),
        headers={
            "content-type": "application/json",
            "x-webhook-test": "true",
        },
    )
    assert resp.status_code == 200

    # Verify: same user row, clerk_id updated, no duplicate
    async with TestSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        users = result.scalars().all()
        assert len(users) == 1
        user = users[0]
        assert user.id == original_user_id
        assert user.clerk_user_id == new_clerk_id
        assert user.full_name == "Updated Name"
        assert user.email_verified is True
