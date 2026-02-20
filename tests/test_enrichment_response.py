"""Tests for POST /api/v1/feed/enrichment-response endpoint.

Covers: each signal type, credit award, upsert dedup, invalid feed_item_id.
"""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.contact import Contact
from app.models.credits import CreditTransaction
from app.models.feed import ContactFreshnessSignal, FeedItem
from tests.conftest import TestSessionLocal, create_test_user_in_db


@pytest_asyncio.fixture
async def enrichment_setup(client: AsyncClient):
    """Create a user, contact, and enrichment_prompt feed item."""
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="enrichment@test.com", full_name="Enrichment Tester"
        )
        contact = Contact(
            user_id=user.id,
            full_name="Sarah Chen",
            current_company="Stripe",
            current_title="Senior Engineer",
            source="linkedin_csv",
        )
        db.add(contact)
        await db.flush()

        feed_item = FeedItem(
            user_id=user.id,
            item_type="enrichment_prompt",
            title="How do you know Sarah Chen?",
            priority=60,
            metadata_={
                "contact_id": str(contact.id),
                "prompt_type": "relationship_type",
            },
        )
        db.add(feed_item)
        await db.commit()
        await db.refresh(contact)
        await db.refresh(feed_item)

    return {
        "user": user,
        "headers": headers,
        "contact_id": contact.id,
        "feed_item_id": feed_item.id,
    }


@pytest.mark.asyncio
async def test_enrichment_relationship_type_updates_contact_and_awards_credits(
    client: AsyncClient, enrichment_setup: dict
):
    resp = await client.post(
        "/api/v1/feed/enrichment-response",
        json={
            "feed_item_id": str(enrichment_setup["feed_item_id"]),
            "signal_type": "relationship_type",
            "signal_value": "colleague",
        },
        headers=enrichment_setup["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "recorded"
    assert data["signal_type"] == "relationship_type"
    assert data["applied"] is True
    assert data["credits_awarded"] == 5
    assert data["contact"]["relationship_type"] == "colleague"
    assert data["contact"]["full_name"] == "Sarah Chen"

    # Verify credit transaction was created
    async with TestSessionLocal() as db:
        ct_result = await db.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == enrichment_setup["user"].id,
                CreditTransaction.reason == "enrichment_response",
            )
        )
        txn = ct_result.scalar_one()
        assert txn.amount == 5
        assert txn.type == "earned"


@pytest.mark.asyncio
async def test_enrichment_would_refer_updates_contact(
    client: AsyncClient, enrichment_setup: dict
):
    resp = await client.post(
        "/api/v1/feed/enrichment-response",
        json={
            "feed_item_id": str(enrichment_setup["feed_item_id"]),
            "signal_type": "would_refer",
            "signal_value": "definitely",
        },
        headers=enrichment_setup["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["contact"]["would_refer"] == "definitely"
    assert data["credits_awarded"] == 5


@pytest.mark.asyncio
async def test_enrichment_recency_updates_last_interaction_date(
    client: AsyncClient, enrichment_setup: dict
):
    resp = await client.post(
        "/api/v1/feed/enrichment-response",
        json={
            "feed_item_id": str(enrichment_setup["feed_item_id"]),
            "signal_type": "recency",
            "signal_value": "2026-01-15",
        },
        headers=enrichment_setup["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["contact"]["last_interaction_date"] == "2026-01-15"
    assert data["credits_awarded"] == 5


@pytest.mark.asyncio
async def test_enrichment_duplicate_signal_upserts_not_duplicates(
    client: AsyncClient, enrichment_setup: dict
):
    payload = {
        "feed_item_id": str(enrichment_setup["feed_item_id"]),
        "signal_type": "relationship_type",
        "signal_value": "colleague",
    }
    # First submission
    resp1 = await client.post(
        "/api/v1/feed/enrichment-response",
        json=payload,
        headers=enrichment_setup["headers"],
    )
    assert resp1.status_code == 200

    # Second submission with updated value — should upsert, not duplicate
    payload["signal_value"] = "manager"
    resp2 = await client.post(
        "/api/v1/feed/enrichment-response",
        json=payload,
        headers=enrichment_setup["headers"],
    )
    assert resp2.status_code == 200
    assert resp2.json()["data"]["contact"]["relationship_type"] == "manager"

    # Verify only one signal row exists for this user+contact+type
    async with TestSessionLocal() as db:
        count_result = await db.execute(
            select(func.count()).where(
                ContactFreshnessSignal.user_id == enrichment_setup["user"].id,
                ContactFreshnessSignal.contact_id == enrichment_setup["contact_id"],
                ContactFreshnessSignal.signal_type == "relationship_type",
            )
        )
        assert count_result.scalar() == 1


@pytest.mark.asyncio
async def test_enrichment_invalid_feed_item_id_returns_404(
    client: AsyncClient, enrichment_setup: dict
):
    resp = await client.post(
        "/api/v1/feed/enrichment-response",
        json={
            "feed_item_id": str(uuid.uuid4()),
            "signal_type": "relationship_type",
            "signal_value": "colleague",
        },
        headers=enrichment_setup["headers"],
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Feed item not found"


@pytest.mark.asyncio
async def test_enrichment_feed_item_without_contact_id_returns_400(
    client: AsyncClient, enrichment_setup: dict
):
    """Feed item with no contact_id in metadata should return 400."""
    async with TestSessionLocal() as db:
        bad_item = FeedItem(
            user_id=enrichment_setup["user"].id,
            item_type="enrichment_prompt",
            title="Bad item",
            priority=50,
            metadata_={"prompt_type": "relationship_type"},  # no contact_id
        )
        db.add(bad_item)
        await db.commit()
        await db.refresh(bad_item)
        bad_item_id = bad_item.id

    resp = await client.post(
        "/api/v1/feed/enrichment-response",
        json={
            "feed_item_id": str(bad_item_id),
            "signal_type": "relationship_type",
            "signal_value": "colleague",
        },
        headers=enrichment_setup["headers"],
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Feed item has no associated contact"


@pytest.mark.asyncio
async def test_enrichment_marks_feed_item_acted_on(
    client: AsyncClient, enrichment_setup: dict
):
    resp = await client.post(
        "/api/v1/feed/enrichment-response",
        json={
            "feed_item_id": str(enrichment_setup["feed_item_id"]),
            "signal_type": "would_refer",
            "signal_value": "probably",
        },
        headers=enrichment_setup["headers"],
    )
    assert resp.status_code == 200

    async with TestSessionLocal() as db:
        item_result = await db.execute(
            select(FeedItem).where(FeedItem.id == enrichment_setup["feed_item_id"])
        )
        item = item_result.scalar_one()
        assert item.acted_on_at is not None
        assert item.seen_at is not None


@pytest.mark.asyncio
async def test_enrichment_response_awards_milestone_when_threshold_crossed(
    client: AsyncClient,
):
    """When enrichment pushes percentage past a milestone, bonus credits are awarded."""
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="milestone@test.com", full_name="Milestone Tester"
        )
        # Create 10 contacts, 0 enriched (need 1 to cross 10%)
        contacts_list = []
        for i in range(10):
            c = Contact(
                user_id=user.id,
                full_name=f"Contact M{i}",
                current_company=f"Company M{i}",
                source="linkedin_csv",
            )
            db.add(c)
            contacts_list.append(c)
        await db.flush()

        # Create feed item for first contact
        feed_item = FeedItem(
            user_id=user.id,
            item_type="enrichment_prompt",
            title="How do you know Contact M0?",
            priority=60,
            metadata_={
                "contact_id": str(contacts_list[0].id),
                "prompt_type": "relationship_type",
            },
        )
        db.add(feed_item)
        await db.commit()
        await db.refresh(feed_item)
        feed_item_id = feed_item.id

    resp = await client.post(
        "/api/v1/feed/enrichment-response",
        json={
            "feed_item_id": str(feed_item_id),
            "signal_type": "relationship_type",
            "signal_value": "colleague",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["credits_awarded"] == 5  # base enrichment credits
    assert data["milestone_reached"] is not None
    assert data["milestone_reached"]["percent"] == 10
    assert data["milestone_reached"]["credits"] == 10

    # Verify milestone was persisted
    async with TestSessionLocal() as db:
        from app.models.milestone import UserMilestone

        result = await db.execute(
            select(UserMilestone).where(
                UserMilestone.user_id == user.id,
                UserMilestone.milestone_type == "enrichment",
            )
        )
        milestone = result.scalar_one()
        assert milestone.milestone_value == 10
        assert milestone.credits_awarded == 10


@pytest.mark.asyncio
async def test_enrichment_response_no_milestone_when_not_crossed(
    client: AsyncClient,
):
    """When enrichment doesn't cross a milestone, no milestone_reached in response."""
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="no_milestone@test.com", full_name="No Milestone"
        )
        # 100 contacts, 5 already enriched (5%), enriching 1 more = 6% (no milestone)
        target_contact = None
        for i in range(100):
            c = Contact(
                user_id=user.id,
                full_name=f"NM Contact {i}",
                current_company=f"NM Company {i}",
                source="linkedin_csv",
            )
            if i < 5:
                c.relationship_type = "colleague"
            db.add(c)
            if i == 5:
                target_contact = c
        await db.flush()

        feed_item = FeedItem(
            user_id=user.id,
            item_type="enrichment_prompt",
            title="How do you know NM Contact 5?",
            priority=60,
            metadata_={
                "contact_id": str(target_contact.id),
                "prompt_type": "relationship_type",
            },
        )
        db.add(feed_item)
        await db.commit()
        await db.refresh(feed_item)
        fi_id = feed_item.id

    resp = await client.post(
        "/api/v1/feed/enrichment-response",
        json={
            "feed_item_id": str(fi_id),
            "signal_type": "relationship_type",
            "signal_value": "friend",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["milestone_reached"] is None
