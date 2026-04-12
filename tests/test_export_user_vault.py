"""Tests for scripts/export_user_vault.py — sunset data-portability script.

TDD: tests written first, then implementation.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact, CsvUpload
from tests.conftest import TestSessionLocal, create_test_user_in_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_contact(
    db: AsyncSession,
    user_id: uuid.UUID,
    first_name: str,
    last_name: str,
    company: str,
) -> Contact:
    contact = Contact(
        user_id=user_id,
        full_name=f"{first_name} {last_name}",
        first_name=first_name,
        last_name=last_name,
        current_company=company,
        source="linkedin_csv",
    )
    db.add(contact)
    await db.flush()
    return contact


async def _create_upload(db: AsyncSession, user_id: uuid.UUID) -> CsvUpload:
    upload = CsvUpload(
        user_id=user_id,
        filename="connections.csv",
        row_count=2,
        status="completed",
    )
    db.add(upload)
    await db.flush()
    return upload


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_produces_valid_json(truncate_tables):
    """Exporting a user with 2 contacts returns JSON with all contacts and user info."""
    from scripts.export_user_vault import export_user_vault

    async with TestSessionLocal() as db:
        user, _ = await create_test_user_in_db(
            db, email="vault@example.com", full_name="Vault User"
        )
        await _create_contact(db, user.id, "Alice", "Smith", "Acme Corp")
        await _create_contact(db, user.id, "Bob", "Jones", "BetaCo")
        await db.commit()

        result = await export_user_vault(user_id=str(user.id), db=db)

    # Top-level keys
    assert "exported_at" in result
    assert "user" in result
    assert "contacts" in result
    assert "uploads" in result
    assert "intro_requests" in result

    # User data
    assert result["user"]["email"] == "vault@example.com"
    assert result["user"]["full_name"] == "Vault User"
    assert "id" in result["user"]

    # Both contacts present
    assert len(result["contacts"]) == 2
    contact_names = {c["full_name"] for c in result["contacts"]}
    assert "Alice Smith" in contact_names
    assert "Bob Jones" in contact_names

    # Contact record has key fields
    first_contact = result["contacts"][0]
    assert "id" in first_contact
    assert "current_company" in first_contact
    assert "created_at" in first_contact


@pytest.mark.asyncio
async def test_export_missing_user_raises_value_error(truncate_tables):
    """Requesting export for a non-existent UUID raises ValueError."""
    from scripts.export_user_vault import export_user_vault

    fake_id = str(uuid.uuid4())

    async with TestSessionLocal() as db:
        with pytest.raises(ValueError, match="User not found"):
            await export_user_vault(user_id=fake_id, db=db)


@pytest.mark.asyncio
async def test_export_does_not_write_to_db(truncate_tables):
    """Running an export leaves the contact count unchanged — no DB writes."""
    from scripts.export_user_vault import export_user_vault

    async with TestSessionLocal() as db:
        user, _ = await create_test_user_in_db(
            db, email="readonly@example.com", full_name="Read Only"
        )
        await _create_contact(db, user.id, "Carol", "White", "Initech")
        await db.commit()

        # Count contacts before export
        count_before_result = await db.execute(
            select(Contact).where(Contact.user_id == user.id)
        )
        count_before = len(count_before_result.scalars().all())

        await export_user_vault(user_id=str(user.id), db=db)

        # Count contacts after export — must be identical
        count_after_result = await db.execute(
            select(Contact).where(Contact.user_id == user.id)
        )
        count_after = len(count_after_result.scalars().all())

    assert count_before == 1
    assert count_after == count_before


@pytest.mark.asyncio
async def test_export_includes_uploads_metadata(truncate_tables):
    """Export includes CSV upload records for the user."""
    from scripts.export_user_vault import export_user_vault

    async with TestSessionLocal() as db:
        user, _ = await create_test_user_in_db(
            db, email="uploader@example.com", full_name="Upload User"
        )
        upload = await _create_upload(db, user.id)
        await db.commit()

        result = await export_user_vault(user_id=str(user.id), db=db)

    assert len(result["uploads"]) == 1
    assert result["uploads"][0]["filename"] == "connections.csv"
    assert result["uploads"][0]["status"] == "completed"
    assert str(upload.id) == result["uploads"][0]["id"]


@pytest.mark.asyncio
async def test_export_excludes_soft_deleted_contacts(truncate_tables):
    """Soft-deleted contacts (deleted_at is set) are excluded from the export."""
    from datetime import datetime, timezone

    from scripts.export_user_vault import export_user_vault

    async with TestSessionLocal() as db:
        user, _ = await create_test_user_in_db(
            db, email="deleted@example.com", full_name="Delete Test"
        )
        await _create_contact(db, user.id, "Active", "Person", "GoodCo")
        deleted = Contact(
            user_id=user.id,
            full_name="Gone Person",
            source="linkedin_csv",
            deleted_at=datetime.now(timezone.utc),
        )
        db.add(deleted)
        await db.commit()

        result = await export_user_vault(user_id=str(user.id), db=db)

    assert len(result["contacts"]) == 1
    assert result["contacts"][0]["full_name"] == "Active Person"
