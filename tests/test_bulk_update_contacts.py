"""Tests for bulk contact relationship type update."""

import pytest
from httpx import AsyncClient

from tests.conftest import TestSessionLocal, create_test_user_in_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_user_with_contacts(db, email, num_contacts=5, company="Acme Corp"):
    """Create a test user and add contacts to their vault."""
    from app.models.contact import Contact

    user, headers = await create_test_user_in_db(db, email=email, full_name="Bulk User")
    for i in range(num_contacts):
        contact = Contact(
            user_id=user.id,
            first_name=f"Contact{i}",
            last_name="Test",
            full_name=f"Contact{i} Test",
            current_company=company,
            current_title=f"Engineer {i}",
            source="linkedin_csv",
        )
        db.add(contact)
    await db.commit()

    from sqlalchemy import select
    from app.models.contact import Contact as C

    result = await db.execute(select(C).where(C.user_id == user.id))
    contact_ids = [str(c.id) for c in result.scalars().all()]

    return user, headers, contact_ids


@pytest.mark.asyncio
async def test_bulk_update_by_ids_sets_relationship_type(client: AsyncClient):
    """Bulk update via contact_ids sets relationship_type on all specified contacts."""
    async with TestSessionLocal() as db:
        user, headers, ids = await _create_user_with_contacts(db, "bulk1@test.com", 3)

    res = await client.patch(
        "/api/v1/contacts/bulk-update",
        headers=headers,
        json={"relationship_type": "former_colleague", "contact_ids": ids},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["updated_count"] == 3

    # Verify contacts actually updated
    for cid in ids:
        r = await client.get(f"/api/v1/contacts/{cid}", headers=headers)
        assert r.json()["data"]["relationship_type"] == "former_colleague"


@pytest.mark.asyncio
async def test_bulk_update_by_filter_updates_matching_contacts(client: AsyncClient):
    """Bulk update via filter updates all contacts matching search criteria."""
    async with TestSessionLocal() as db:
        user, headers, ids = await _create_user_with_contacts(
            db, "bulk2@test.com", 5, company="Singapore EDB"
        )

    res = await client.patch(
        "/api/v1/contacts/bulk-update",
        headers=headers,
        json={
            "relationship_type": "alumni",
            "filter": {"search": "singapore edb"},
        },
    )
    assert res.status_code == 200
    assert res.json()["data"]["updated_count"] == 5


@pytest.mark.asyncio
async def test_bulk_update_rejects_both_ids_and_filter(client: AsyncClient):
    """Providing both contact_ids and filter returns 422."""
    async with TestSessionLocal() as db:
        user, headers, ids = await _create_user_with_contacts(db, "bulk3@test.com", 1)

    res = await client.patch(
        "/api/v1/contacts/bulk-update",
        headers=headers,
        json={
            "relationship_type": "friend",
            "contact_ids": ids,
            "filter": {"search": "test"},
        },
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_bulk_update_rejects_neither_ids_nor_filter(client: AsyncClient):
    """Providing neither contact_ids nor filter returns 422."""
    async with TestSessionLocal() as db:
        user, headers, _ = await _create_user_with_contacts(db, "bulk4@test.com", 1)

    res = await client.patch(
        "/api/v1/contacts/bulk-update",
        headers=headers,
        json={"relationship_type": "friend"},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_bulk_update_rejects_invalid_relationship_type(client: AsyncClient):
    """Invalid relationship_type returns 422."""
    async with TestSessionLocal() as db:
        user, headers, ids = await _create_user_with_contacts(db, "bulk5@test.com", 1)

    res = await client.patch(
        "/api/v1/contacts/bulk-update",
        headers=headers,
        json={"relationship_type": "best_buddy", "contact_ids": ids},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_bulk_update_does_not_affect_other_users_contacts(client: AsyncClient):
    """Bulk update only touches the current user's contacts, not other users'."""
    async with TestSessionLocal() as db:
        user1, headers1, ids1 = await _create_user_with_contacts(
            db, "bulk6a@test.com", 2, company="SharedCo"
        )
        user2, headers2, ids2 = await _create_user_with_contacts(
            db, "bulk6b@test.com", 2, company="SharedCo"
        )

    # User 1 bulk-updates their contacts
    res = await client.patch(
        "/api/v1/contacts/bulk-update",
        headers=headers1,
        json={"relationship_type": "manager", "filter": {"search": "sharedco"}},
    )
    assert res.status_code == 200
    assert res.json()["data"]["updated_count"] == 2

    # User 2's contacts are untouched
    for cid in ids2:
        r = await client.get(f"/api/v1/contacts/{cid}", headers=headers2)
        assert r.json()["data"]["relationship_type"] is None


@pytest.mark.asyncio
async def test_bulk_update_by_filter_with_relationship_type_filter(client: AsyncClient):
    """Filter by current relationship_type to reclassify contacts."""
    async with TestSessionLocal() as db:
        from app.models.contact import Contact

        user, headers = await create_test_user_in_db(db, email="bulk7@test.com")
        for i in range(3):
            db.add(
                Contact(
                    user_id=user.id,
                    first_name=f"R{i}",
                    last_name="Test",
                    full_name=f"R{i} Test",
                    current_company="TestCo",
                    relationship_type="recruiter",
                    source="linkedin_csv",
                )
            )
        db.add(
            Contact(
                user_id=user.id,
                first_name="Keep",
                last_name="This",
                full_name="Keep This",
                current_company="TestCo",
                relationship_type="friend",
                source="linkedin_csv",
            )
        )
        await db.commit()

    res = await client.patch(
        "/api/v1/contacts/bulk-update",
        headers=headers,
        json={
            "relationship_type": "industry_peer",
            "filter": {"relationship_type": "recruiter"},
        },
    )
    assert res.status_code == 200
    assert res.json()["data"]["updated_count"] == 3


@pytest.mark.asyncio
async def test_bulk_update_empty_filter_returns_400(client: AsyncClient):
    """Filter that matches zero contacts returns 400."""
    async with TestSessionLocal() as db:
        user, headers, _ = await _create_user_with_contacts(db, "bulk8@test.com", 2)

    res = await client.patch(
        "/api/v1/contacts/bulk-update",
        headers=headers,
        json={
            "relationship_type": "friend",
            "filter": {"search": "nonexistent_company_xyz"},
        },
    )
    assert res.status_code == 400
    assert "No contacts match" in res.json()["detail"]
