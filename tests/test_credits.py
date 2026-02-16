"""Tests for credit service — earn, spend, balance, refund, expiry."""

import uuid as uuid_mod
from datetime import datetime, timedelta, timezone

from app.models.credits import CreditTransaction
from app.services.credits import earn_credits, get_balance, refund_credits, spend_credits
from tests.conftest import TestSessionLocal


class TestGetBalance:
    async def test_zero_balance_new_user(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            balance = await get_balance(uid, db)
            assert balance == 0

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
            # Add expired credits
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
            # Expired
            db.add(CreditTransaction(
                user_id=uid,
                amount=50,
                type="earned",
                reason="old",
                expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            ))
            # Active
            await earn_credits(uid, 75, "csv_upload", db)
            balance = await get_balance(uid, db)
            assert balance == 75


class TestEarnCredits:
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
            txn = await earn_credits(uid, 50, "intro_facilitation", db, reference_id=ref)
            assert txn.reference_id == ref


class TestSpendCredits:
    async def test_deducts_balance(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            await earn_credits(uid, 100, "csv_upload", db)
            txn = await spend_credits(uid, 20, "intro_request", db)
            assert txn.amount == -20
            assert txn.type == "spent"
            balance = await get_balance(uid, db)
            assert balance == 80

    async def test_insufficient_balance_raises(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            await earn_credits(uid, 10, "csv_upload", db)
            try:
                await spend_credits(uid, 20, "intro_request", db)
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert "Insufficient credits" in str(e)

    async def test_exact_balance_succeeds(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            await earn_credits(uid, 20, "csv_upload", db)
            await spend_credits(uid, 20, "intro_request", db)
            balance = await get_balance(uid, db)
            assert balance == 0


class TestRefundCredits:
    async def test_refund_adds_credits(self):
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            await earn_credits(uid, 100, "csv_upload", db)
            await spend_credits(uid, 20, "intro_request", db)
            await refund_credits(uid, 15, "intro_declined_refund", db)
            balance = await get_balance(uid, db)
            assert balance == 95
