"""Tests for CSV upload real-time progress publishing.

Verifies that _publish_progress commits milestones in separate transactions
and that process_csv_upload_core invokes the progress_callback at each phase.
"""

import base64
import contextlib
import uuid
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.models.contact import CsvUpload
from tests.conftest import TestSessionLocal, create_test_user_in_db


async def test_publish_progress_commits_fields_independently():
    """_publish_progress writes fields in a separate transaction visible to
    other sessions (simulating what the polling endpoint would see)."""
    from app.tasks.csv_processing import _publish_progress

    async with TestSessionLocal() as db:
        user, _ = await create_test_user_in_db(db, email="prog-test@example.com")
        upload = CsvUpload(user_id=user.id, filename="test.csv", status="queued")
        db.add(upload)
        await db.commit()
        await db.refresh(upload)
        upload_id = upload.id

    # Publish progress in a separate transaction
    await _publish_progress(
        TestSessionLocal,
        upload_id,
        status="processing",
        progress_phase="parsing",
        row_count=100,
    )

    # Verify the fields are visible from a fresh session
    async with TestSessionLocal() as db:
        result = await db.execute(select(CsvUpload).where(CsvUpload.id == upload_id))
        upload = result.scalar_one()
        assert upload.status == "processing"
        assert upload.progress_phase == "parsing"
        assert upload.row_count == 100


async def test_publish_progress_updates_processed_count():
    """_publish_progress can update processed_count incrementally."""
    from app.tasks.csv_processing import _publish_progress

    async with TestSessionLocal() as db:
        user, _ = await create_test_user_in_db(db, email="count-test@example.com")
        upload = CsvUpload(user_id=user.id, filename="test.csv", status="processing")
        db.add(upload)
        await db.commit()
        await db.refresh(upload)
        upload_id = upload.id

    await _publish_progress(TestSessionLocal, upload_id, processed_count=50)
    await _publish_progress(TestSessionLocal, upload_id, processed_count=100)

    async with TestSessionLocal() as db:
        result = await db.execute(select(CsvUpload).where(CsvUpload.id == upload_id))
        upload = result.scalar_one()
        assert upload.processed_count == 100


async def test_progress_callback_invoked_at_all_phases():
    """process_csv_upload_core calls progress_callback at parsing, cleaning,
    importing, and scoring milestones."""
    async with TestSessionLocal() as db:
        user, _ = await create_test_user_in_db(db, email="phases@example.com")
        upload = CsvUpload(user_id=user.id, filename="phases.csv", status="queued")
        db.add(upload)
        await db.commit()
        await db.refresh(upload)
        upload_id = str(upload.id)
        user_id = str(user.id)

    csv_content = b"First Name,Last Name,Company,Position,Connected On\nAlice,Smith,Acme,Engineer,01 Jan 2024\n"
    b64 = base64.b64encode(csv_content).decode()

    callback = AsyncMock()

    async with TestSessionLocal() as db:
        from app.tasks.csv_processing import process_csv_upload_core

        await process_csv_upload_core(
            upload_id, user_id, b64, db, progress_callback=callback
        )
        await db.commit()

    # Collect all progress_phase values from callback calls
    phases = []
    for call in callback.call_args_list:
        kwargs = call.kwargs if call.kwargs else {}
        if "progress_phase" in kwargs:
            phases.append(kwargs["progress_phase"])

    assert "parsing" in phases, f"Expected 'parsing' in phases, got {phases}"
    assert "cleaning" in phases, f"Expected 'cleaning' in phases, got {phases}"
    assert "importing" in phases, f"Expected 'importing' in phases, got {phases}"
    assert "scoring" in phases, f"Expected 'scoring' in phases, got {phases}"


async def test_progress_callback_receives_row_count():
    """progress_callback receives row_count after CSV parsing."""
    async with TestSessionLocal() as db:
        user, _ = await create_test_user_in_db(db, email="rowcount@example.com")
        upload = CsvUpload(user_id=user.id, filename="rows.csv", status="queued")
        db.add(upload)
        await db.commit()
        await db.refresh(upload)
        upload_id = str(upload.id)
        user_id = str(user.id)

    csv_rows = (
        b"First Name,Last Name,Company,Position,Connected On\n"
        b"Alice,Smith,Acme,Engineer,01 Jan 2024\n"
        b"Bob,Jones,Globex,Manager,15 Mar 2023\n"
    )
    b64 = base64.b64encode(csv_rows).decode()

    callback = AsyncMock()

    async with TestSessionLocal() as db:
        from app.tasks.csv_processing import process_csv_upload_core

        await process_csv_upload_core(
            upload_id, user_id, b64, db, progress_callback=callback
        )
        await db.commit()

    # Find the call that set row_count
    row_counts = [
        call.kwargs["row_count"]
        for call in callback.call_args_list
        if "row_count" in (call.kwargs or {})
    ]
    assert len(row_counts) >= 1
    assert row_counts[0] == 2


async def test_progress_phase_cleared_on_completion():
    """After successful processing, progress_phase should be None."""
    async with TestSessionLocal() as db:
        user, _ = await create_test_user_in_db(db, email="done@example.com")
        upload = CsvUpload(user_id=user.id, filename="done.csv", status="queued")
        db.add(upload)
        await db.commit()
        await db.refresh(upload)
        upload_id = str(upload.id)
        user_id = str(user.id)

    csv_content = b"First Name,Last Name,Company,Position,Connected On\nAlice,Smith,Acme,Engineer,01 Jan 2024\n"
    b64 = base64.b64encode(csv_content).decode()

    async with TestSessionLocal() as db:
        from app.tasks.csv_processing import process_csv_upload_core

        await process_csv_upload_core(upload_id, user_id, b64, db)
        await db.commit()

    async with TestSessionLocal() as db:
        result = await db.execute(
            select(CsvUpload).where(CsvUpload.id == uuid.UUID(upload_id))
        )
        upload = result.scalar_one()
        assert upload.status == "completed"
        assert upload.progress_phase is None


async def test_progress_phase_cleared_on_failure():
    """After failed processing, progress_phase should be None."""
    async with TestSessionLocal() as db:
        user, _ = await create_test_user_in_db(db, email="fail-prog@example.com")
        upload = CsvUpload(user_id=user.id, filename="fail.csv", status="queued")
        db.add(upload)
        await db.commit()
        await db.refresh(upload)
        upload_id = str(upload.id)
        user_id = str(user.id)

    csv_content = b"First Name,Last Name,Company,Position,Connected On\nAlice,Smith,Acme,Engineer,01 Jan 2024\n"
    b64 = base64.b64encode(csv_content).decode()

    with patch(
        "app.tasks.csv_processing.clean_contacts",
        new_callable=AsyncMock,
        side_effect=RuntimeError("API error"),
    ):
        async with TestSessionLocal() as db:
            from app.tasks.csv_processing import process_csv_upload_core

            with contextlib.suppress(RuntimeError):
                await process_csv_upload_core(upload_id, user_id, b64, db)
            await db.commit()

    async with TestSessionLocal() as db:
        result = await db.execute(
            select(CsvUpload).where(CsvUpload.id == uuid.UUID(upload_id))
        )
        upload = result.scalar_one()
        assert upload.status == "failed"
        assert upload.progress_phase is None


async def test_progress_phase_in_upload_status_response(client):
    """GET /api/v1/contacts/uploads/{id} returns progress_phase field."""
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(db, email="api-prog@example.com")
        upload = CsvUpload(
            user_id=user.id,
            filename="api.csv",
            status="processing",
            progress_phase="importing",
            row_count=200,
            processed_count=50,
        )
        db.add(upload)
        await db.commit()
        await db.refresh(upload)
        upload_id = upload.id

    resp = await client.get(f"/api/v1/contacts/uploads/{upload_id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["progress_phase"] == "importing"
    assert data["row_count"] == 200
    assert data["processed_count"] == 50
