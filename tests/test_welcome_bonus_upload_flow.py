"""Tests for the P0 welcome bonus + CSV upload same-day flow.

Verifies:
1. Welcome bonus bypasses daily cap (skip_daily_cap=True)
2. CSV upload succeeds even when credit earn hits daily cap
3. Frontend-facing upload status surfaces errors correctly
"""

import base64
import uuid as uuid_mod
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models.contact import Contact, CsvUpload
from app.services.credits import MAX_EARN_PER_DAY, earn_credits, get_balance
from tests.conftest import TestSessionLocal, create_test_user_in_db


class TestWelcomeBonusSkipsDailyCap:
    async def test_welcome_bonus_with_skip_daily_cap_bypasses_limit(self):
        """earn_credits with skip_daily_cap=True succeeds even when cap is reached."""
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            # Fill up the daily cap
            await earn_credits(uid, MAX_EARN_PER_DAY, "csv_upload", db)
            await db.commit()

            # Without skip_daily_cap, this should fail
            with pytest.raises(ValueError, match="Daily earn cap exceeded"):
                await earn_credits(uid, 100, "csv_upload", db)

            # With skip_daily_cap=True, welcome bonus should succeed
            txn = await earn_credits(uid, 500, "welcome_bonus", db, skip_daily_cap=True)
            await db.commit()

            assert txn.amount == 500
            assert txn.reason == "welcome_bonus"

            balance = await get_balance(uid, db)
            assert balance == MAX_EARN_PER_DAY + 500

    async def test_daily_cap_still_enforced_without_skip_flag(self):
        """Regular earn_credits respects daily cap (regression guard)."""
        uid = uuid_mod.uuid4()
        async with TestSessionLocal() as db:
            await earn_credits(uid, MAX_EARN_PER_DAY, "csv_upload", db)
            await db.commit()

            with pytest.raises(ValueError, match="Daily earn cap exceeded"):
                await earn_credits(uid, 1, "csv_upload", db)


class TestCsvUploadSucceedsWhenDailyCapReached:
    async def test_contacts_imported_even_when_credit_earn_fails(self):
        """CSV upload creates contacts even if credit earn hits daily cap."""
        async with TestSessionLocal() as db:
            user, _ = await create_test_user_in_db(
                db, email="captest@test.com", full_name="Cap Tester"
            )
            user_id = user.id

            # Fill daily cap with a non-exempt reason so csv_upload credit
            # actually hits the cap (welcome_bonus is exempt from cap counting)
            await earn_credits(user_id, MAX_EARN_PER_DAY, "csv_upload", db)

            upload = CsvUpload(
                user_id=user_id,
                filename="test.csv",
                status="queued",
            )
            db.add(upload)
            await db.commit()
            await db.refresh(upload)
            upload_id = upload.id

        # Prepare minimal CSV
        csv_content = (
            b"First Name,Last Name,Company,Position,Connected On\n"
            b"Alice,Smith,Acme Corp,Engineer,01 Jan 2024\n"
            b"Bob,Jones,Beta Inc,Designer,15 Mar 2024\n"
        )
        b64 = base64.b64encode(csv_content).decode()

        # Run CSV processing (uses TestSessionLocal for DB)
        from unittest.mock import patch

        with patch(
            "app.database._get_session_factory",
            return_value=TestSessionLocal,
        ):
            from app.tasks.csv_processing import process_csv_upload_core

            async with TestSessionLocal() as db:
                await process_csv_upload_core(
                    str(upload_id),
                    str(user_id),
                    b64,
                    db,
                    progress_callback=AsyncMock(),
                )
                await db.commit()

        # Verify contacts were imported despite credit cap
        async with TestSessionLocal() as db:
            result = await db.execute(
                select(CsvUpload).where(CsvUpload.id == upload_id)
            )
            upload = result.scalar_one()
            assert upload.status == "completed", (
                f"Upload should complete even when credits fail, got: {upload.status}"
                f" error: {upload.error_message}"
            )
            assert upload.contacts_created >= 1

            # Verify contacts exist
            contacts_result = await db.execute(
                select(Contact).where(Contact.user_id == user_id)
            )
            contacts = contacts_result.scalars().all()
            assert len(contacts) >= 1

            # Balance should still be at cap (no extra credits earned)
            balance = await get_balance(user_id, db)
            assert balance == MAX_EARN_PER_DAY
