"""Tests for PII encryption at rest.

Validates:
- Round-trip encrypt/decrypt on Contact PII fields
- NULL passthrough (None stays None)
- Blind index determinism
- In-memory contact search returns correct results
- Dashboard network analysis aggregation correctness
- raw_csv_row cleared after CSV processing
"""

import io
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.main import app
from app.models.contact import Contact
from app.models.match_result import WarmScore
from app.models.user import User
from app.utils.encryption import EncryptedString, compute_blind_index
from tests.conftest import TestSessionLocal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_user(db: AsyncSession, email: str = "enc@test.com") -> User:
    user = User(
        email=email,
        full_name="Encryption Test",
        password_hash="fakehash",
        email_verified=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _create_contact(
    db: AsyncSession,
    user_id: uuid.UUID,
    first_name: str = "Alice",
    last_name: str = "Smith",
    email: str = "alice@example.com",
    company: str = "Acme Inc",
    title: str = "Engineer",
    notes: str | None = None,
) -> Contact:
    contact = Contact(
        user_id=user_id,
        first_name=first_name,
        last_name=last_name,
        full_name=f"{first_name} {last_name}",
        email=email,
        current_company=company,
        current_title=title,
        notes=notes,
        email_blind_index=compute_blind_index(email) if email else None,
        name_company_blind_index=(
            compute_blind_index(f"{first_name}{last_name}{company}")
            if first_name and last_name and company
            else None
        ),
    )
    db.add(contact)
    await db.flush()
    return contact


async def _get_auth_headers(client: AsyncClient) -> tuple[dict, User]:
    """Register a user via API and return (headers, user)."""
    resp = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": f"enc-{uuid.uuid4().hex[:8]}@test.com",
            "password": "TestPass123!",
            "full_name": "Enc Tester",
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify user email so marketplace features work
    async with TestSessionLocal() as sess:
        result = await sess.execute(select(User).where(User.email_verified.is_(False)))
        user = result.scalar_one_or_none()
        if user:
            user.email_verified = True
            await sess.commit()
            await sess.refresh(user)
            return headers, user

    return headers, None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_round_trip_encrypt_decrypt():
    """Contact PII fields are encrypted on write and decrypted on read."""
    async with TestSessionLocal() as db:
        user = await _create_user(db)
        contact = await _create_contact(
            db, user.id,
            first_name="Bob",
            last_name="Jones",
            email="bob@corp.com",
            company="BigCorp",
            title="VP Engineering",
            notes="Met at conference",
        )
        await db.commit()
        contact_id = contact.id

        # Re-load from DB to trigger decrypt
        result = await db.execute(select(Contact).where(Contact.id == contact_id))
        loaded = result.scalar_one()

        assert loaded.first_name == "Bob"
        assert loaded.last_name == "Jones"
        assert loaded.full_name == "Bob Jones"
        assert loaded.email == "bob@corp.com"
        assert loaded.current_company == "BigCorp"
        assert loaded.current_title == "VP Engineering"
        assert loaded.notes == "Met at conference"


@pytest.mark.asyncio
async def test_null_passthrough():
    """None values stay None through encrypt/decrypt cycle."""
    async with TestSessionLocal() as db:
        user = await _create_user(db, email="null@test.com")
        contact = Contact(
            user_id=user.id,
            full_name="Null Test",
            first_name=None,
            last_name=None,
            email=None,
            current_company=None,
            notes=None,
            linkedin_url=None,
            location=None,
        )
        db.add(contact)
        await db.commit()

        result = await db.execute(select(Contact).where(Contact.id == contact.id))
        loaded = result.scalar_one()

        assert loaded.first_name is None
        assert loaded.email is None
        assert loaded.notes is None
        assert loaded.linkedin_url is None
        assert loaded.location is None


@pytest.mark.asyncio
async def test_blind_index_determinism():
    """Same input always produces the same blind index."""
    idx1 = compute_blind_index("alice@example.com")
    idx2 = compute_blind_index("alice@example.com")
    idx3 = compute_blind_index("ALICE@EXAMPLE.COM")  # case-insensitive
    idx4 = compute_blind_index("  alice@example.com  ")  # whitespace-stripped

    assert idx1 == idx2
    assert idx1 == idx3
    assert idx1 == idx4

    # Different input = different index
    idx_other = compute_blind_index("bob@example.com")
    assert idx1 != idx_other


@pytest.mark.asyncio
async def test_blind_index_stored_on_contact():
    """Blind indexes are populated correctly on Contact."""
    async with TestSessionLocal() as db:
        user = await _create_user(db, email="bi@test.com")
        contact = await _create_contact(db, user.id)
        await db.commit()

        result = await db.execute(select(Contact).where(Contact.id == contact.id))
        loaded = result.scalar_one()

        assert loaded.email_blind_index is not None
        assert len(loaded.email_blind_index) == 64  # SHA-256 hex digest
        assert loaded.name_company_blind_index is not None
        assert len(loaded.name_company_blind_index) == 64


@pytest.mark.asyncio
async def test_contact_search_in_memory(client: AsyncClient):
    """GET /contacts?search= filters correctly on encrypted fields."""
    headers, user = await _get_auth_headers(client)

    # Create contacts via API
    for name, company in [
        ("Alice", "Stripe"),
        ("Bob", "Google"),
        ("Charlie", "Stripe"),
    ]:
        resp = await client.post(
            "/api/v1/contacts/manual",
            json={
                "first_name": name,
                "last_name": "Test",
                "company": company,
                "position": "Engineer",
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text

    # Search for "Stripe" — should match Alice and Charlie
    resp = await client.get(
        "/api/v1/contacts?search=Stripe",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    names = {d["full_name"] for d in data}
    assert "Alice Test" in names
    assert "Charlie Test" in names
    assert "Bob Test" not in names
    assert resp.json()["meta"]["total"] == 2


@pytest.mark.asyncio
async def test_contact_search_by_name(client: AsyncClient):
    """Search by name works on encrypted fields."""
    headers, _ = await _get_auth_headers(client)

    await client.post(
        "/api/v1/contacts/manual",
        json={
            "first_name": "Unique",
            "last_name": "Person",
            "company": "SomeCorp",
            "position": "PM",
        },
        headers=headers,
    )

    resp = await client.get(
        "/api/v1/contacts?search=Unique",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["meta"]["total"] == 1
    assert resp.json()["data"][0]["full_name"] == "Unique Person"


@pytest.mark.asyncio
async def test_dashboard_network_analysis_aggregation(client: AsyncClient):
    """Dashboard network analysis aggregates companies correctly despite encryption."""
    headers, _ = await _get_auth_headers(client)

    # Create several contacts at the same company
    for i in range(3):
        await client.post(
            "/api/v1/contacts/manual",
            json={
                "first_name": f"Emp{i}",
                "last_name": "Worker",
                "company": "MegaCorp",
                "position": "Engineer",
            },
            headers=headers,
        )
    # One at a different company
    await client.post(
        "/api/v1/contacts/manual",
        json={
            "first_name": "Solo",
            "last_name": "Dev",
            "company": "TinyCo",
            "position": "CTO",
        },
        headers=headers,
    )

    resp = await client.get("/api/v1/dashboard/insights", headers=headers)
    assert resp.status_code == 200
    insights = resp.json()["data"]
    network = insights.get("network_analysis")
    assert network is not None
    assert network["total_contacts"] == 4

    # MegaCorp should be the top company with count 3
    top_companies = network["top_companies"]
    assert len(top_companies) >= 1
    megacorp = next((c for c in top_companies if c["company"] == "MegaCorp"), None)
    assert megacorp is not None
    assert megacorp["count"] == 3


@pytest.mark.asyncio
async def test_csv_upload_clears_raw_csv_row(client: AsyncClient):
    """After CSV processing, raw_csv_row is cleared on all contacts."""
    headers, _ = await _get_auth_headers(client)

    csv_content = (
        "First Name,Last Name,Email Address,Company,Position,Connected On\n"
        "Test,User,test.csv@example.com,CsvCorp,Dev,01 Jan 2024\n"
    )
    csv_file = io.BytesIO(csv_content.encode())

    resp = await client.post(
        "/api/v1/contacts/upload",
        files={"file": ("contacts.csv", csv_file, "text/csv")},
        headers=headers,
    )
    assert resp.status_code == 201

    # Check that raw_csv_row is None on the created contact
    # Note: email is encrypted, so we load all contacts and filter in-memory
    async with TestSessionLocal() as db:
        result = await db.execute(select(Contact))
        all_contacts = list(result.scalars())
        csv_contacts = [
            c for c in all_contacts if c.email == "test.csv@example.com"
        ]
        assert len(csv_contacts) >= 1
        for c in csv_contacts:
            assert c.raw_csv_row is None, "raw_csv_row should be cleared after processing"
