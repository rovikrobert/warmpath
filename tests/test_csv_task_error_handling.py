"""Tests for CSV processing task error handling.

Verifies that when the core processing function raises, the upload status
is persisted as 'failed' even though the main transaction is rolled back.
"""

import base64
import contextlib
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.contact import CsvUpload
from tests.conftest import TestSessionLocal, create_test_user_in_db

pytestmark = pytest.mark.usefixtures("truncate_tables")


async def test_failed_upload_status_persists_after_rollback():
    """Upload status must be 'failed' (not stuck in 'processing') when
    process_csv_upload_core raises an exception — even though the outer
    _celery_run wrapper rolls back the main transaction."""
    async with TestSessionLocal() as db:
        user, _ = await create_test_user_in_db(db, email="fail-test@example.com")

        upload = CsvUpload(
            user_id=user.id,
            filename="fail.csv",
            status="queued",
        )
        db.add(upload)
        await db.commit()
        await db.refresh(upload)
        upload_id = upload.id
        user_id = user.id

    csv_content = b"First Name,Last Name,Company,Position,Connected On\nAlice,Smith,Acme,Engineer,01 Jan 2024\n"
    b64 = base64.b64encode(csv_content).decode()

    # Patch at app.database where _get_session_factory is defined (it's
    # imported lazily inside _celery_run, so module-level patch won't work).
    with (
        patch(
            "app.database._get_session_factory",
            return_value=TestSessionLocal,
        ),
        patch(
            "app.tasks.csv_processing.clean_contacts",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Claude API rate limit exceeded"),
        ),
    ):
        from app.tasks.csv_processing import _celery_run

        with contextlib.suppress(RuntimeError):
            await _celery_run(None, str(upload_id), str(user_id), b64)

    # Now verify: the upload status must be 'failed', not 'processing'
    async with TestSessionLocal() as db:
        result = await db.execute(select(CsvUpload).where(CsvUpload.id == upload_id))
        upload = result.scalar_one()
        assert upload.status == "failed", (
            f"Expected 'failed' but got '{upload.status}' — "
            "error status was lost by transaction rollback"
        )
        assert "rate limit" in upload.error_message.lower()
        assert upload.completed_at is not None


async def test_successful_upload_status_is_completed():
    """Verify the happy path — successful processing sets status to 'completed'."""
    async with TestSessionLocal() as db:
        user, _ = await create_test_user_in_db(db, email="success-test@example.com")

        upload = CsvUpload(
            user_id=user.id,
            filename="good.csv",
            status="queued",
        )
        db.add(upload)
        await db.commit()
        await db.refresh(upload)
        upload_id = upload.id
        user_id = user.id

    csv_content = b"First Name,Last Name,Company,Position,Connected On\nBob,Jones,Acme,Manager,01 Jan 2024\n"
    b64 = base64.b64encode(csv_content).decode()

    with patch(
        "app.database._get_session_factory",
        return_value=TestSessionLocal,
    ):
        from app.tasks.csv_processing import _celery_run

        await _celery_run(None, str(upload_id), str(user_id), b64)

    async with TestSessionLocal() as db:
        result = await db.execute(select(CsvUpload).where(CsvUpload.id == upload_id))
        upload = result.scalar_one()
        assert upload.status == "completed"
        assert upload.contacts_created >= 1
        assert upload.completed_at is not None
