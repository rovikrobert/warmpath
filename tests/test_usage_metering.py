"""Tests for usage metering middleware + usage API endpoints."""

import io
import uuid as uuid_mod
from datetime import date, timedelta

from httpx import AsyncClient

from app.models.enrichment import UsageLog
from app.models.user import User
from tests.conftest import TestSessionLocal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_CSV = (
    "First Name,Last Name,Email Address,Company,Position,Connected On\n"
    "Alice,Smith,alice@example.com,Acme Corp,CEO,{recent}\n"
).format(
    recent=(date.today() - timedelta(days=30)).strftime("%d %b %Y"),
)


async def _signup(client: AsyncClient, email: str = "meter@test.com") -> dict:
    """Sign up a user, return {headers, user_id}."""
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Secret123", "full_name": "Meter User"},
    )
    token = resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get("/api/v1/auth/me", headers=headers)
    return {"headers": headers, "user_id": me.json()["data"]["id"]}


def _csv_file(content: str = SAMPLE_CSV):
    return {
        "file": ("connections.csv", io.BytesIO(content.encode("utf-8")), "text/csv")
    }


# ---------------------------------------------------------------------------
# Metered logging
# ---------------------------------------------------------------------------


async def test_metered_action_creates_log(client: AsyncClient):
    """POST /contacts/upload should create a usage_log with resource_type='metered'."""
    auth = await _signup(client, "metered_log@test.com")

    await client.post(
        "/api/v1/contacts/upload", headers=auth["headers"], files=_csv_file()
    )

    # Check that a metered log entry was written
    async with TestSessionLocal() as db:
        from sqlalchemy import select

        result = await db.execute(
            select(UsageLog).where(
                UsageLog.user_id == uuid_mod.UUID(auth["user_id"]),
                UsageLog.resource_type == "metered",
                UsageLog.action == "csv_upload",
            )
        )
        logs = list(result.scalars())
        assert len(logs) >= 1
        entry = logs[0]
        assert entry.metadata_ is not None
        assert entry.metadata_["method"] == "POST"
        assert "processing_time_ms" in entry.metadata_


async def test_nonmetered_endpoint_no_metered_log(client: AsyncClient):
    """GET /contacts should NOT create a metered log entry."""
    auth = await _signup(client, "nonmetered@test.com")

    await client.get("/api/v1/contacts", headers=auth["headers"])

    async with TestSessionLocal() as db:
        from sqlalchemy import select

        result = await db.execute(
            select(UsageLog).where(
                UsageLog.user_id == uuid_mod.UUID(auth["user_id"]),
                UsageLog.resource_type == "metered",
            )
        )
        metered_logs = list(result.scalars())
        assert len(metered_logs) == 0


# ---------------------------------------------------------------------------
# GET /usage/me — summary
# ---------------------------------------------------------------------------


async def test_usage_me_returns_correct_counts(client: AsyncClient):
    """After a CSV upload, GET /usage/me should reflect the metered count."""
    auth = await _signup(client, "usage_counts@test.com")

    # Do a CSV upload (metered action)
    await client.post(
        "/api/v1/contacts/upload", headers=auth["headers"], files=_csv_file()
    )

    resp = await client.get("/api/v1/usage/me", headers=auth["headers"])
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["plan_tier"] == "free"
    assert body["counts"]["csv_upload"] >= 1
    assert body["limits"]["csv_upload"] == 1
    assert body["limits"]["marketplace_search"] == 0
    assert body["total_metered_calls"] >= 1


async def test_usage_me_empty_for_new_user(client: AsyncClient):
    """New user with no activity should have zero metered counts."""
    auth = await _signup(client, "usage_empty@test.com")

    resp = await client.get("/api/v1/usage/me", headers=auth["headers"])
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["total_metered_calls"] == 0
    assert body["counts"]["csv_upload"] == 0
    assert body["counts"]["smart_search"] == 0


async def test_usage_me_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/usage/me")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /usage/me/history — pagination
# ---------------------------------------------------------------------------


async def test_usage_history_paginated(client: AsyncClient):
    """History endpoint should return paginated entries."""
    auth = await _signup(client, "usage_hist@test.com")

    # Create some usage via metered actions
    await client.post(
        "/api/v1/contacts/upload", headers=auth["headers"], files=_csv_file()
    )

    resp = await client.get(
        "/api/v1/usage/me/history",
        headers=auth["headers"],
        params={"page": 1, "per_page": 5},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "meta" in body
    assert body["meta"]["page"] == 1
    assert body["meta"]["per_page"] == 5
    assert body["meta"]["total"] >= 1
    # Each entry has expected fields
    entry = body["data"][0]
    assert "id" in entry
    assert "action" in entry
    assert "resource_type" in entry
    assert "created_at" in entry


async def test_usage_history_empty_befo[RESEND_KEY_REDACTED](client: AsyncClient):
    """New user with no metered actions should have only auth-related logs."""
    auth = await _signup(client, "usage_hist_empty@test.com")

    resp = await client.get("/api/v1/usage/me/history", headers=auth["headers"])
    assert resp.status_code == 200
    body = resp.json()
    # Signup helper calls /auth/me which gets logged by tracking middleware,
    # so total may be > 0, but no metered entries should exist
    metered_entries = [e for e in body["data"] if e["resource_type"] == "metered"]
    assert len(metered_entries) == 0


# ---------------------------------------------------------------------------
# Warning headers — free tier
# ---------------------------------------------------------------------------


async def test_free_tier_csv_upload_warning_at_limit(client: AsyncClient):
    """After 1 CSV upload on free tier, warning header should appear."""
    auth = await _signup(client, "csv_warn@test.com")

    # First upload — should trigger the "approaching" or "reached" warning
    resp = await client.post(
        "/api/v1/contacts/upload", headers=auth["headers"], files=_csv_file()
    )
    assert resp.status_code == 201

    # The warning header should be present (1/1 = limit reached)
    warning = resp.headers.get("x-warmpath-usage-warning", "")
    assert "csv_upload" in warning or "limit" in warning.lower()


async def test_free_tier_marketplace_warning(client: AsyncClient):
    """Free tier marketplace search should get marketplace warning header."""
    auth = await _signup(client, "mkt_warn@test.com")

    # Marketplace search will fail on 402 (no credits), but middleware runs after
    resp = await client.post(
        "/api/v1/marketplace/search",
        headers=auth["headers"],
        json={"company_names": ["Stripe"]},
    )
    # The endpoint itself will return 402 (insufficient credits), but middleware
    # should still add the warning header
    warning = resp.headers.get("x-warmpath-usage-warning", "")
    assert "paid plan" in warning.lower() or "marketplace" in warning.lower()


async def test_paid_tier_no_warning(client: AsyncClient):
    """Paid tier user should NOT get usage warning headers."""
    auth = await _signup(client, "paid_user@test.com")

    # Upgrade user to paid tier
    async with TestSessionLocal() as db:
        from sqlalchemy import select

        result = await db.execute(
            select(User).where(User.id == uuid_mod.UUID(auth["user_id"]))
        )
        user = result.scalar_one()
        user.plan_tier = "paid"
        await db.commit()

    resp = await client.post(
        "/api/v1/contacts/upload", headers=auth["headers"], files=_csv_file()
    )
    assert resp.status_code == 201
    warning = resp.headers.get("x-warmpath-usage-warning")
    assert warning is None
