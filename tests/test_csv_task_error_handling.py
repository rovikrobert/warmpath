"""Tests for CSV processing task error handling.

Verifies that when the core processing function raises, the upload status
is persisted as 'failed' even though the main transaction is rolled back.
"""

import base64
import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.contact import CsvUpload
from tests.conftest import TestSessionLocal, create_test_user_in_db

pytestmark = pytest.mark.usefixtures("truncate_tables")


# ---------------------------------------------------------------------------
# Shared fixture: create a user + queued upload, return IDs for assertions.
# Using a proper fixture (instead of inline TestSessionLocal()) ensures the
# truncate_tables teardown runs *after* the test on the same event loop,
# preventing stale-session issues under pytest-xdist.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def queued_upload():
    """Create a fresh user + CsvUpload(status='queued') and return their IDs."""
    async with TestSessionLocal() as db:
        user, _ = await create_test_user_in_db(
            db, email=f"csv-task-{id(db)}@example.com"
        )
        upload = CsvUpload(
            user_id=user.id,
            filename="test.csv",
            status="queued",
        )
        db.add(upload)
        await db.commit()
        await db.refresh(upload)
        return {"upload_id": upload.id, "user_id": user.id}


# Shared mock for _get_engine — prevents _celery_run from creating a real
# asyncpg engine (which can fail or leak resources when PostgreSQL is not
# available in the test environment).
def _mock_engine():
    engine = MagicMock()
    engine.dispose = AsyncMock()
    return engine


async def test_failed_upload_status_persists_after_rollback(queued_upload):
    """Upload status must be 'failed' (not stuck in 'processing') when
    process_csv_upload_core raises an exception — even though the outer
    _celery_run wrapper rolls back the main transaction."""
    upload_id = queued_upload["upload_id"]
    user_id = queued_upload["user_id"]

    csv_content = b"First Name,Last Name,Company,Position,Connected On\nAlice,Smith,Acme,Engineer,01 Jan 2024\n"
    b64 = base64.b64encode(csv_content).decode()

    # Patch both _get_session_factory (for DB sessions) and _get_engine (to
    # avoid creating a real asyncpg engine that fails without PostgreSQL).
    with (
        patch(
            "app.database._get_session_factory",
            return_value=TestSessionLocal,
        ),
        patch(
            "app.database._get_engine",
            return_value=_mock_engine(),
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


@pytest.mark.smoke
async def test_successful_upload_status_is_completed(queued_upload):
    """Verify the happy path — successful processing sets status to 'completed'."""
    upload_id = queued_upload["upload_id"]
    user_id = queued_upload["user_id"]

    csv_content = b"First Name,Last Name,Company,Position,Connected On\nBob,Jones,Acme,Manager,01 Jan 2024\n"
    b64 = base64.b64encode(csv_content).decode()

    with (
        patch(
            "app.database._get_session_factory",
            return_value=TestSessionLocal,
        ),
        patch(
            "app.database._get_engine",
            return_value=_mock_engine(),
        ),
    ):
        from app.tasks.csv_processing import _celery_run

        await _celery_run(None, str(upload_id), str(user_id), b64)

    async with TestSessionLocal() as db:
        result = await db.execute(select(CsvUpload).where(CsvUpload.id == upload_id))
        upload = result.scalar_one()
        assert upload.status == "completed"
        assert upload.contacts_created >= 1
        assert upload.completed_at is not None
