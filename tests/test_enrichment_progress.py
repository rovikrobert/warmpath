"""Tests for GET /api/v1/contacts/enrichment-progress endpoint."""

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.contact import Contact
from app.models.milestone import UserMilestone
from tests.conftest import TestSessionLocal, create_test_user_in_db


@pytest_asyncio.fixture
async def progress_user(client: AsyncClient):
    """Create a user with 10 contacts, some enriched."""
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="progress@test.com", full_name="Progress Tester"
        )
        # Create 10 contacts: 3 with relationship_type, 1 with both fields
        for i in range(10):
            c = Contact(
                user_id=user.id,
                full_name=f"Contact {i}",
                current_company=f"Company {i}",
                source="linkedin_csv",
            )
            if i < 3:
                c.relationship_type = "colleague"
            if i == 0:
                c.would_refer = "definitely"
            db.add(c)
        await db.commit()
    return {"user": user, "headers": headers}


@pytest.mark.asyncio
async def test_enrichment_progress_returns_correct_stats(
    client: AsyncClient, progress_user: dict
):
    resp = await client.get(
        "/api/v1/contacts/enrichment-progress",
        headers=progress_user["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_contacts"] == 10
    assert data["enriched_contacts"] == 3
    assert data["fully_enriched"] == 1
    assert data["percentage"] == 30.0
    assert data["next_milestone"] == 50
    assert data["credits_at_next_milestone"] == 50
    assert data["milestones_claimed"] == []


@pytest.mark.asyncio
async def test_enrichment_progress_no_contacts_returns_zero(
    client: AsyncClient,
):
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="empty@test.com", full_name="Empty User"
        )
    resp = await client.get(
        "/api/v1/contacts/enrichment-progress",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_contacts"] == 0
    assert data["percentage"] == 0.0
    assert data["next_milestone"] == 10
    assert data["credits_at_next_milestone"] == 10


@pytest.mark.asyncio
async def test_enrichment_progress_shows_claimed_milestones(
    client: AsyncClient, progress_user: dict
):
    # Manually create a claimed milestone
    async with TestSessionLocal() as db:
        m = UserMilestone(
            user_id=progress_user["user"].id,
            milestone_type="enrichment",
            milestone_value=10,
            credits_awarded=10,
        )
        db.add(m)
        await db.commit()

    resp = await client.get(
        "/api/v1/contacts/enrichment-progress",
        headers=progress_user["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["milestones_claimed"]) == 1
    assert data["milestones_claimed"][0]["milestone_value"] == 10
    assert data["milestones_claimed"][0]["credits_awarded"] == 10
    # 30% enriched, 10% already claimed, next unclaimed above 30% is 50%
    assert data["next_milestone"] == 50


@pytest.mark.asyncio
async def test_enrichment_progress_all_milestones_claimed_returns_null_next(
    client: AsyncClient,
):
    """When all milestones are claimed and 100% enriched, next_milestone is null."""
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="complete@test.com", full_name="Complete User"
        )
        # Create 2 fully enriched contacts
        for i in range(2):
            c = Contact(
                user_id=user.id,
                full_name=f"Done {i}",
                current_company=f"Co {i}",
                source="manual",
                relationship_type="friend",
                would_refer="definitely",
            )
            db.add(c)
        # Claim all milestones
        for pct, credits in [(10, 10), (25, 25), (50, 50), (75, 75), (100, 100)]:
            db.add(
                UserMilestone(
                    user_id=user.id,
                    milestone_type="enrichment",
                    milestone_value=pct,
                    credits_awarded=credits,
                )
            )
        await db.commit()

    resp = await client.get(
        "/api/v1/contacts/enrichment-progress",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["percentage"] == 100.0
    assert data["next_milestone"] is None
    assert data["credits_at_next_milestone"] is None
    assert len(data["milestones_claimed"]) == 5
