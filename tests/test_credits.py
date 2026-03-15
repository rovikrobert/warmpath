"""Tests for credit service + API — earn, spend, balance, refund, expiry, triggers."""

import uuid as uuid_mod
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.config import settings
from app.models.credits import CreditTransaction
from app.services.credits import (
    earn_credits,
    expire_stale_credits,
    get_balance,
    get_credit_summary,
    refund_credits,
    spend_credits,
)
from tests.conftest import TestSessionLocal, create_test_user_in_db


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------


class TestGetBalance:
    async def test_zero_balance_new_user(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            balance = await get_balance(uid, db)
            assert balance == 0

    @pytest.mark.smoke
    async def test_balance_after_earning(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            await earn_credits(uid, 100, "csv_upload", db)
            balance = await get_balance(uid, db)
            assert balance == 100

    async def test_balance_after_spending(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            await earn_credits(uid, 100, "csv_upload", db)
            await spend_credits(uid, 30, "marketplace_search", db)
            balance = await get_balance(uid, db)
            assert balance == 70

    async def test_expired_credits_excluded(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            txn = CreditTransaction(
                user_id=uid,
                amount=100,
                type="earned",
                reason="csv_upload",
                expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
            db.add(txn)
            await db.flush()
            balance = await get_balance(uid, db)
            assert balance == 0

    async def test_mixed_expired_and_active(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            db.add(
                CreditTransaction(
                    user_id=uid,
                    amount=50,
                    type="earned",
                    reason="old",
                    expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                )
            )
            await earn_credits(uid, 75, "csv_upload", db)
            balance = await get_balance(uid, db)
            assert balance == 75

    async def test_multiple_earns_cumulative(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            await earn_credits(uid, 100, "csv_upload", db)
            await earn_credits(uid, 50, "welcome_bonus", db)
            await earn_credits(uid, 50, "intro_facilitated", db)
            balance = await get_balance(uid, db)
            assert balance == 200


class TestDailyEarnCap:
    async def test_earn_cap_blocks_when_exceeded(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            await earn_credits(uid, 450, "csv_upload", db)
            with pytest.raises(ValueError, match="Daily earn cap exceeded"):
                await earn_credits(uid, 100, "csv_upload", db)

    async def test_skip_daily_cap_bypasses_limit(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            await earn_credits(uid, 500, "csv_upload", db)
            txn = await earn_credits(uid, 100, "welcome_bonus", db, skip_daily_cap=True)
            assert txn.amount == 100
            balance = await get_balance(uid, db)
            assert balance == 600

    async def test_welcome_bonus_does_not_block_subsequent_csv_upload(self):
        """Regression: welcome bonus (500 in beta) must not prevent same-day CSV upload credits."""
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            # Simulate beta welcome bonus (skip_daily_cap=True as fixed)
            await earn_credits(uid, 500, "welcome_bonus", db, skip_daily_cap=True)
            # CSV upload credits should still work
            txn = await earn_credits(uid, 100, "csv_upload", db)
            assert txn.amount == 100
            balance = await get_balance(uid, db)
            assert balance == 600


class TestGetCreditSummary:
    async def test_full_summary(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            await earn_credits(uid, 100, "csv_upload", db)
            await earn_credits(uid, 50, "welcome_bonus", db)
            await spend_credits(uid, 20, "intro_request", db)

            summary = await get_credit_summary(uid, db)
            assert summary["balance"] == 130
            assert summary["earned_total"] == 150
            assert summary["spent_total"] == 20
            assert summary["expiring_soon"] == 0

    async def test_expiring_soon(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            # Credits expiring in 15 days (within 30-day window)
            db.add(
                CreditTransaction(
                    user_id=uid,
                    amount=50,
                    type="earned",
                    reason="old_upload",
                    expires_at=datetime.now(timezone.utc) + timedelta(days=15),
                )
            )
            # Credits expiring in 60 days (outside 30-day window)
            db.add(
                CreditTransaction(
                    user_id=uid,
                    amount=75,
                    type="earned",
                    reason="recent_upload",
                    expires_at=datetime.now(timezone.utc) + timedelta(days=60),
                )
            )
            await db.flush()

            summary = await get_credit_summary(uid, db)
            assert summary["balance"] == 125
            assert summary["expiring_soon"] == 50

    async def test_empty_user(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            summary = await get_credit_summary(uid, db)
            assert summary["balance"] == 0
            assert summary["earned_total"] == 0
            assert summary["spent_total"] == 0
            assert summary["expiring_soon"] == 0


class TestEarnCredits:
    @pytest.mark.smoke
    async def test_creates_transaction(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            txn = await earn_credits(uid, 100, "csv_upload", db)
            assert txn.amount == 100
            assert txn.type == "earned"
            assert txn.reason == "csv_upload"
            assert txn.expires_at is not None

    async def test_with_reference_id(self):
        uid = uuid_mod.uuid4()
        ref = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            txn = await earn_credits(
                uid, 50, "intro_facilitation", db, reference_id=ref
            )
            assert txn.reference_id == ref

    async def test_expiry_is_12_months(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            before = datetime.now(timezone.utc)
            txn = await earn_credits(uid, 100, "csv_upload", db)
            after = datetime.now(timezone.utc)
            # expires_at should be approximately 365 days from now
            assert txn.expires_at >= before + timedelta(days=364)
            assert txn.expires_at <= after + timedelta(days=366)


class TestSpendCredits:
    @pytest.mark.smoke
    async def test_deducts_balance(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            await earn_credits(uid, 100, "csv_upload", db)
            txn = await spend_credits(uid, 20, "intro_request", db)
            assert txn.amount == -20
            assert txn.type == "spent"
            balance = await get_balance(uid, db)
            assert balance == 80

    @pytest.mark.smoke
    async def test_insufficient_balance_raises(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            await earn_credits(uid, 10, "csv_upload", db)
            with pytest.raises(ValueError, match="Insufficient credits"):
                await spend_credits(uid, 20, "intro_request", db)

    async def test_exact_balance_succeeds(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            await earn_credits(uid, 20, "csv_upload", db)
            await spend_credits(uid, 20, "intro_request", db)
            balance = await get_balance(uid, db)
            assert balance == 0

    async def test_spend_zero_balance_raises(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            with pytest.raises(ValueError):
                await spend_credits(uid, 5, "search", db)


class TestRefundCredits:
    async def test_refund_adds_credits(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            await earn_credits(uid, 100, "csv_upload", db)
            await spend_credits(uid, 20, "intro_request", db)
            await refund_credits(uid, 15, "intro_declined_refund", db)
            balance = await get_balance(uid, db)
            assert balance == 95

    async def test_refund_has_expiry(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            txn = await refund_credits(uid, 15, "refund", db)
            assert txn.expires_at is not None


class TestExpireStaleCredits:
    async def test_expires_old_credits(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            # Add expired credits (past expiry)
            db.add(
                CreditTransaction(
                    user_id=uid,
                    amount=100,
                    type="earned",
                    reason="csv_upload",
                    expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                )
            )
            # Add active credits
            await earn_credits(uid, 50, "welcome_bonus", db)
            await db.flush()

            # Balance before expiry: expired credits are already excluded
            # from get_balance, but the expiry sweep creates an offsetting txn
            # so the ledger is clean
            count = await expire_stale_credits(db)
            assert count == 1

            # Balance should still be 50 (active credits only)
            balance = await get_balance(uid, db)
            assert balance == 50

    async def test_no_double_expiry(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            db.add(
                CreditTransaction(
                    user_id=uid,
                    amount=100,
                    type="earned",
                    reason="csv_upload",
                    expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                )
            )
            await earn_credits(uid, 50, "welcome_bonus", db)
            await db.flush()

            # First sweep
            count1 = await expire_stale_credits(db)
            assert count1 == 1

            # Second sweep — nothing new to expire
            count2 = await expire_stale_credits(db)
            assert count2 == 0

    async def test_doesnt_expire_into_negative(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            # Earned 100, spent 80, then 100 expired
            db.add(
                CreditTransaction(
                    user_id=uid,
                    amount=100,
                    type="earned",
                    reason="csv_upload",
                    expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                )
            )
            db.add(
                CreditTransaction(
                    user_id=uid,
                    amount=-80,
                    type="spent",
                    reason="search",
                )
            )
            await db.flush()

            count = await expire_stale_credits(db)
            # Balance was already 0 (expired excluded), so nothing to offset
            assert count == 0
            balance = await get_balance(uid, db)
            assert balance == -80  # spent without active credits

    async def test_nothing_to_expire(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            await earn_credits(uid, 100, "csv_upload", db)
            count = await expire_stale_credits(db)
            assert count == 0

    async def test_multiple_users(self):
        uid1 = uuid_mod.uuid4()
        uid2 = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            # Both have expired credits + some active
            for uid in [uid1, uid2]:
                db.add(
                    CreditTransaction(
                        user_id=uid,
                        amount=100,
                        type="earned",
                        reason="csv_upload",
                        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                    )
                )
                await earn_credits(uid, 50, "welcome_bonus", db)
            await db.flush()

            count = await expire_stale_credits(db)
            assert count == 2


# ---------------------------------------------------------------------------
# API-level tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db,
            email="credits@test.com",
            full_name="Credit Tester",
            email_verified=True,
        )
        # Award welcome bonus (normally done by Clerk webhook)
        await earn_credits(user.id, 50, "welcome_bonus", db)
        await db.commit()
    return headers


@pytest_asyncio.fixture
async def user_id(auth_headers: dict, client: AsyncClient) -> str:
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    return resp.json()["data"]["id"]


class TestBalanceEndpoint:
    @pytest.mark.smoke
    async def test_new_user_has_welcome_bonus(self, client: AsyncClient, auth_headers):
        """New users get 50 welcome credits."""
        resp = await client.get("/api/v1/credits/balance", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["balance"] == 50
        assert data["earned_total"] == 50

    @pytest.mark.smoke
    async def test_balance_after_operations(
        self, client: AsyncClient, auth_headers, user_id
    ):
        """Balance reflects earn + spend."""
        uid = uuid_mod.UUID(user_id)
        async with TestSessionLocal() as db:
            await earn_credits(uid, 100, "csv_upload", db)
            await spend_credits(uid, 20, "search", db)
            await db.commit()

        resp = await client.get("/api/v1/credits/balance", headers=auth_headers)
        data = resp.json()["data"]
        # 50 (welcome) + 100 (csv) - 20 (search) = 130
        assert data["balance"] == 130
        assert data["earned_total"] == 150
        assert data["spent_total"] == 20


class TestHistoryEndpoint:
    async def test_lists_transactions(self, client: AsyncClient, auth_headers):
        """History shows all transactions."""
        resp = await client.get("/api/v1/credits/history", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        # Should have welcome bonus
        assert len(data) >= 1
        reasons = [t["reason"] for t in data]
        assert "welcome_bonus" in reasons

    async def test_filter_by_type(self, client: AsyncClient, auth_headers, user_id):
        """Can filter history by transaction type."""
        uid = uuid_mod.UUID(user_id)
        async with TestSessionLocal() as db:
            await earn_credits(uid, 100, "csv_upload", db)
            await spend_credits(uid, 5, "search", db)
            await db.commit()

        resp = await client.get(
            "/api/v1/credits/history?type=spent", headers=auth_headers
        )
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["type"] == "spent"

    async def test_pagination(self, client: AsyncClient, auth_headers, user_id):
        """History paginates correctly."""
        uid = uuid_mod.UUID(user_id)
        async with TestSessionLocal() as db:
            for i in range(5):
                await earn_credits(uid, 10, f"test_{i}", db)
            await db.commit()

        resp = await client.get(
            "/api/v1/credits/history?per_page=3&page=1", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        meta = resp.json()["meta"]
        assert len(data) == 3
        assert meta["total"] == 6  # 5 test + 1 welcome
        assert meta["total_pages"] == 2

    async def test_history_ordered_newest_first(
        self, client: AsyncClient, auth_headers, user_id
    ):
        """Transactions are ordered newest first."""
        uid = uuid_mod.UUID(user_id)
        async with TestSessionLocal() as db:
            await earn_credits(uid, 100, "latest_earn", db)
            await db.commit()

        resp = await client.get("/api/v1/credits/history", headers=auth_headers)
        data = resp.json()["data"]
        assert data[0]["reason"] == "latest_earn"


class TestPurchaseEndpoint:
    async def test_purchase_stub(self, client: AsyncClient, auth_headers):
        """Purchase credits (MVP stub)."""
        resp = await client.post(
            "/api/v1/credits/purchase",
            json={"amount": 100},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["amount"] == 100
        assert data["new_balance"] == 150  # 50 welcome + 100 purchased

    async def test_purchase_invalid_amount(self, client: AsyncClient, auth_headers):
        """Amount must be positive and <= 1000."""
        resp = await client.post(
            "/api/v1/credits/purchase",
            json={"amount": 0},
            headers=auth_headers,
        )
        assert resp.status_code == 422

        resp = await client.post(
            "/api/v1/credits/purchase",
            json={"amount": 1001},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_purchase_max_amount(self, client: AsyncClient, auth_headers):
        """Max purchase of 1000."""
        resp = await client.post(
            "/api/v1/credits/purchase",
            json={"amount": 1000},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["amount"] == 1000

    async def test_purchase_blocked_for_non_admin_in_production(
        self, client: AsyncClient, auth_headers
    ):
        """In production, non-admin users cannot mint credits via purchase."""
        old_env = settings.APP_ENV
        try:
            settings.APP_ENV = "production"
            resp = await client.post(
                "/api/v1/credits/purchase",
                json={"amount": 100},
                headers=auth_headers,
            )
            assert resp.status_code == 403
        finally:
            settings.APP_ENV = old_env

    async def test_purchase_allowed_for_admin_in_production(
        self, client: AsyncClient, auth_headers, user_id
    ):
        """In production, admins can still use purchase endpoint."""
        uid = uuid_mod.UUID(user_id)
        old_env = settings.APP_ENV
        try:
            settings.APP_ENV = "production"
            async with TestSessionLocal() as db:
                from app.models.user import User
                from sqlalchemy import select

                user = (
                    await db.execute(select(User).where(User.id == uid))
                ).scalar_one()
                user.is_admin = True
                await db.commit()

            resp = await client.post(
                "/api/v1/credits/purchase",
                json={"amount": 100},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            assert resp.json()["data"]["amount"] == 100
        finally:
            settings.APP_ENV = old_env


class TestExpireEndpoint:
    async def test_expire_sweep(self, client: AsyncClient, auth_headers, user_id):
        """Expire endpoint triggers sweep."""
        uid = uuid_mod.UUID(user_id)
        async with TestSessionLocal() as db:
            db.add(
                CreditTransaction(
                    user_id=uid,
                    amount=200,
                    type="earned",
                    reason="old_credits",
                    expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                )
            )
            await db.commit()

        resp = await client.post("/api/v1/credits/expire", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["users_expired"] >= 1

    async def test_expire_nothing(self, client: AsyncClient, auth_headers):
        """No expired credits → 0 users expired."""
        resp = await client.post("/api/v1/credits/expire", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["users_expired"] == 0


# ---------------------------------------------------------------------------
# Credit earn trigger tests
# ---------------------------------------------------------------------------


class TestCreditTriggers:
    async def test_welcome_bonus_credited(self, client: AsyncClient):
        """Welcome bonus awards 50 credits."""
        async with TestSessionLocal() as db:
            user, headers = await create_test_user_in_db(
                db, email="welcome@test.com", full_name="Welcome User"
            )
            await earn_credits(user.id, 50, "welcome_bonus", db)
            await db.commit()

        resp = await client.get("/api/v1/credits/balance", headers=headers)
        assert resp.json()["data"]["balance"] == 50

    @pytest.mark.smoke
    async def test_csv_upload_awards_credits(self, client: AsyncClient, auth_headers):
        """Successful CSV upload awards 100 credits."""
        import io

        csv_content = (
            "First Name,Last Name,Email Address,Company,Position,"
            "Connected On\n"
            "Alice,Smith,alice@example.com,Acme Corp,Engineer,"
            "01 Jan 2024\n"
        )

        before_resp = await client.get("/api/v1/credits/balance", headers=auth_headers)
        before_balance = before_resp.json()["data"]["balance"]

        resp = await client.post(
            "/api/v1/contacts/upload",
            headers=auth_headers,
            files={
                "file": (
                    "connections.csv",
                    io.BytesIO(csv_content.encode("utf-8")),
                    "text/csv",
                )
            },
        )
        assert resp.status_code in (200, 201, 202)

        after_resp = await client.get("/api/v1/credits/balance", headers=auth_headers)
        after_balance = after_resp.json()["data"]["balance"]

        assert after_balance == before_balance + 100
