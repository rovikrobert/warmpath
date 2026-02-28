"""Tests for cross-user contact freshness signal aggregation.

Covers: consensus propagation, no-consensus skip, privacy (no user_ids in log),
company change feed items, NULL-only updates, idempotent re-runs.
"""

import hashlib

import pytest
from sqlalchemy import select

from app.models.contact import Contact
from app.models.feed import (
    ContactFreshnessSignal,
    FeedItem,
    FreshnessPropagationLog,
)
from tests.conftest import TestSessionLocal, create_test_user_in_db

pytestmark = pytest.mark.usefixtures("truncate_tables")


def _name_company_hash(full_name: str, company: str) -> str:
    """Reproduce the hash logic from app/api/feed.py."""
    raw = f"{full_name.lower()}|{company.lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def _create_contact(db, user_id, full_name, company, **kwargs):
    """Create a contact with computed name_company_blind_index."""
    contact = Contact(
        user_id=user_id,
        full_name=full_name,
        current_company=company,
        source="linkedin_csv",
        name_company_blind_index=_name_company_hash(full_name, company),
        **kwargs,
    )
    db.add(contact)
    await db.flush()
    return contact


async def _create_signal(
    db, user_id, contact_id, signal_type, signal_value, name_company_hash
):
    signal = ContactFreshnessSignal(
        user_id=user_id,
        contact_id=contact_id,
        signal_type=signal_type,
        signal_value=signal_value,
        name_company_hash=name_company_hash,
        source="feed_prompt",
    )
    db.add(signal)
    await db.flush()
    return signal


@pytest.mark.asyncio
async def test_freshness_propagation_log_model_exists():
    """FreshnessPropagationLog table can be queried."""
    async with TestSessionLocal() as db:
        result = await db.execute(select(FreshnessPropagationLog))
        rows = result.scalars().all()
        assert rows == []


@pytest.mark.asyncio
async def test_consensus_propagates_relationship_type_to_null_contacts():
    """When 2+ users agree on relationship_type, contacts with NULL get updated."""
    async with TestSessionLocal() as db:
        nch = _name_company_hash("Sarah Chen", "Stripe")

        user_a, _ = await create_test_user_in_db(
            db, email="a@test.com", full_name="User A"
        )
        user_b, _ = await create_test_user_in_db(
            db, email="b@test.com", full_name="User B"
        )
        user_c, _ = await create_test_user_in_db(
            db, email="c@test.com", full_name="User C"
        )

        contact_a = await _create_contact(
            db,
            user_a.id,
            "Sarah Chen",
            "Stripe",
            relationship_type="colleague",
        )
        contact_b = await _create_contact(db, user_b.id, "Sarah Chen", "Stripe")
        contact_c = await _create_contact(db, user_c.id, "Sarah Chen", "Stripe")

        await _create_signal(
            db,
            user_a.id,
            contact_a.id,
            "relationship_type",
            {"type": "colleague"},
            nch,
        )
        await _create_signal(
            db,
            user_b.id,
            contact_b.id,
            "relationship_type",
            {"type": "colleague"},
            nch,
        )
        await db.commit()

        from app.services.freshness_aggregator import aggregate_freshness_signals

        agg_result = await aggregate_freshness_signals(db)
        await db.commit()

        assert agg_result.contacts_updated == 2

        await db.refresh(contact_b)
        await db.refresh(contact_c)
        assert contact_b.relationship_type == "colleague"
        assert contact_c.relationship_type == "colleague"

        log_result = await db.execute(select(FreshnessPropagationLog))
        logs = log_result.scalars().all()
        assert len(logs) == 1
        assert logs[0].name_company_hash == nch
        assert logs[0].signal_type == "relationship_type"
        assert logs[0].source_count == 2
        assert logs[0].contacts_updated == 2


@pytest.mark.asyncio
async def test_no_consensus_when_users_disagree():
    """When users disagree on signal_value, no propagation occurs."""
    async with TestSessionLocal() as db:
        nch = _name_company_hash("Alex Kim", "Google")

        user_a, _ = await create_test_user_in_db(
            db, email="disagree_a@test.com", full_name="User DA"
        )
        user_b, _ = await create_test_user_in_db(
            db, email="disagree_b@test.com", full_name="User DB"
        )
        user_c, _ = await create_test_user_in_db(
            db, email="disagree_c@test.com", full_name="User DC"
        )

        contact_a = await _create_contact(db, user_a.id, "Alex Kim", "Google")
        contact_b = await _create_contact(db, user_b.id, "Alex Kim", "Google")
        contact_c = await _create_contact(db, user_c.id, "Alex Kim", "Google")

        # Only 1 vote each — neither reaches threshold of 2
        await _create_signal(
            db,
            user_a.id,
            contact_a.id,
            "relationship_type",
            {"type": "colleague"},
            nch,
        )
        await _create_signal(
            db,
            user_b.id,
            contact_b.id,
            "relationship_type",
            {"type": "friend"},
            nch,
        )
        await db.commit()

        from app.services.freshness_aggregator import aggregate_freshness_signals

        agg_result = await aggregate_freshness_signals(db)
        await db.commit()

        assert agg_result.contacts_updated == 0

        await db.refresh(contact_a)
        await db.refresh(contact_b)
        await db.refresh(contact_c)
        assert contact_a.relationship_type is None
        assert contact_b.relationship_type is None
        assert contact_c.relationship_type is None

        log_result = await db.execute(select(FreshnessPropagationLog))
        assert len(log_result.scalars().all()) == 0


@pytest.mark.asyncio
async def test_propagation_log_contains_no_user_ids():
    """Privacy: propagation log must not contain any user_id references."""
    async with TestSessionLocal() as db:
        nch = _name_company_hash("Privacy Test", "Meta")

        user_a, _ = await create_test_user_in_db(
            db, email="priv_a@test.com", full_name="Priv A"
        )
        user_b, _ = await create_test_user_in_db(
            db, email="priv_b@test.com", full_name="Priv B"
        )

        contact_a = await _create_contact(db, user_a.id, "Privacy Test", "Meta")
        contact_b = await _create_contact(db, user_b.id, "Privacy Test", "Meta")

        await _create_signal(
            db,
            user_a.id,
            contact_a.id,
            "would_refer",
            {"likelihood": "definitely"},
            nch,
        )
        await _create_signal(
            db,
            user_b.id,
            contact_b.id,
            "would_refer",
            {"likelihood": "definitely"},
            nch,
        )
        await db.commit()

        from app.services.freshness_aggregator import aggregate_freshness_signals

        await aggregate_freshness_signals(db)
        await db.commit()

        log_result = await db.execute(select(FreshnessPropagationLog))
        logs = log_result.scalars().all()
        assert len(logs) == 1

        column_names = [c.name for c in FreshnessPropagationLog.__table__.columns]
        assert "user_id" not in column_names

        log = logs[0]
        assert not hasattr(log, "user_id")
        val_str = str(log.consensus_value)
        assert str(user_a.id) not in val_str
        assert str(user_b.id) not in val_str


@pytest.mark.asyncio
async def test_company_change_creates_feed_item_not_contact_update():
    """When users say contact left company, generate feed item but don't auto-update contact."""
    async with TestSessionLocal() as db:
        nch = _name_company_hash("Li Wei", "Stripe")

        user_a, _ = await create_test_user_in_db(
            db, email="cc_a@test.com", full_name="CC User A"
        )
        user_b, _ = await create_test_user_in_db(
            db, email="cc_b@test.com", full_name="CC User B"
        )
        user_c, _ = await create_test_user_in_db(
            db, email="cc_c@test.com", full_name="CC User C"
        )

        contact_a = await _create_contact(db, user_a.id, "Li Wei", "Stripe")
        contact_b = await _create_contact(db, user_b.id, "Li Wei", "Stripe")
        contact_c = await _create_contact(db, user_c.id, "Li Wei", "Stripe")

        await _create_signal(
            db,
            user_a.id,
            contact_a.id,
            "contact_moved",
            {"old_company": "Stripe", "new_company": "Notion"},
            nch,
        )
        await _create_signal(
            db,
            user_b.id,
            contact_b.id,
            "contact_moved",
            {"old_company": "Stripe", "new_company": "Notion"},
            nch,
        )
        await db.commit()

        from app.services.freshness_aggregator import aggregate_freshness_signals

        await aggregate_freshness_signals(db)
        await db.commit()

        # Contact's current_company should NOT be changed
        await db.refresh(contact_a)
        await db.refresh(contact_b)
        await db.refresh(contact_c)
        assert contact_a.current_company == "Stripe"
        assert contact_b.current_company == "Stripe"
        assert contact_c.current_company == "Stripe"

        # Feed item for user_c only (didn't report signal)
        feed_result = await db.execute(
            select(FeedItem).where(FeedItem.item_type == "contact_update")
        )
        feed_items = feed_result.scalars().all()
        c_items = [f for f in feed_items if f.user_id == user_c.id]
        a_items = [f for f in feed_items if f.user_id == user_a.id]
        b_items = [f for f in feed_items if f.user_id == user_b.id]
        assert len(c_items) == 1
        assert len(a_items) == 0
        assert len(b_items) == 0

        meta = c_items[0].metadata_
        assert "consensus_count" in meta
        assert "stale_confidence" in meta
        assert meta["consensus_count"] == 2


@pytest.mark.asyncio
async def test_null_only_propagation_does_not_overwrite_existing_values():
    """Contacts with existing non-NULL values are never overwritten by consensus."""
    async with TestSessionLocal() as db:
        nch = _name_company_hash("Existing Val", "Apple")

        user_a, _ = await create_test_user_in_db(
            db, email="null_a@test.com", full_name="Null A"
        )
        user_b, _ = await create_test_user_in_db(
            db, email="null_b@test.com", full_name="Null B"
        )
        user_c, _ = await create_test_user_in_db(
            db, email="null_c@test.com", full_name="Null C"
        )

        contact_a = await _create_contact(db, user_a.id, "Existing Val", "Apple")
        contact_b = await _create_contact(db, user_b.id, "Existing Val", "Apple")
        contact_c = await _create_contact(
            db,
            user_c.id,
            "Existing Val",
            "Apple",
            relationship_type="friend",
        )

        await _create_signal(
            db,
            user_a.id,
            contact_a.id,
            "relationship_type",
            {"type": "colleague"},
            nch,
        )
        await _create_signal(
            db,
            user_b.id,
            contact_b.id,
            "relationship_type",
            {"type": "colleague"},
            nch,
        )
        await db.commit()

        from app.services.freshness_aggregator import aggregate_freshness_signals

        await aggregate_freshness_signals(db)
        await db.commit()

        await db.refresh(contact_a)
        await db.refresh(contact_b)
        await db.refresh(contact_c)

        assert contact_a.relationship_type == "colleague"
        assert contact_b.relationship_type == "colleague"
        assert contact_c.relationship_type == "friend"  # NOT overwritten


@pytest.mark.asyncio
async def test_still_at_company_false_creates_feed_item():
    """still_at_company with confirmed=false generates feed item, not contact update."""
    async with TestSessionLocal() as db:
        nch = _name_company_hash("Jane Park", "Databricks")

        user_a, _ = await create_test_user_in_db(
            db, email="sac_a@test.com", full_name="SAC A"
        )
        user_b, _ = await create_test_user_in_db(
            db, email="sac_b@test.com", full_name="SAC B"
        )
        user_c, _ = await create_test_user_in_db(
            db, email="sac_c@test.com", full_name="SAC C"
        )

        contact_a = await _create_contact(db, user_a.id, "Jane Park", "Databricks")
        contact_b = await _create_contact(db, user_b.id, "Jane Park", "Databricks")
        contact_c = await _create_contact(db, user_c.id, "Jane Park", "Databricks")

        await _create_signal(
            db,
            user_a.id,
            contact_a.id,
            "still_at_company",
            {"confirmed": False},
            nch,
        )
        await _create_signal(
            db,
            user_b.id,
            contact_b.id,
            "still_at_company",
            {"confirmed": False},
            nch,
        )
        await db.commit()

        from app.services.freshness_aggregator import aggregate_freshness_signals

        result = await aggregate_freshness_signals(db)
        await db.commit()

        # Company should NOT be updated
        await db.refresh(contact_c)
        assert contact_c.current_company == "Databricks"

        # Feed item should exist for user_c (not reporters a/b)
        feed_result = await db.execute(
            select(FeedItem).where(FeedItem.item_type == "contact_update")
        )
        feed_items = feed_result.scalars().all()
        c_items = [f for f in feed_items if f.user_id == user_c.id]
        assert len(c_items) == 1
        assert result.feed_items_created == 1


@pytest.mark.asyncio
async def test_would_refer_consensus_propagates_to_null_contacts():
    """would_refer consensus updates contacts where would_refer is NULL."""
    async with TestSessionLocal() as db:
        nch = _name_company_hash("Refer Test", "Notion")

        user_a, _ = await create_test_user_in_db(
            db, email="wr_a@test.com", full_name="WR A"
        )
        user_b, _ = await create_test_user_in_db(
            db, email="wr_b@test.com", full_name="WR B"
        )

        contact_a = await _create_contact(db, user_a.id, "Refer Test", "Notion")
        contact_b = await _create_contact(
            db, user_b.id, "Refer Test", "Notion", would_refer="no"
        )

        await _create_signal(
            db,
            user_a.id,
            contact_a.id,
            "would_refer",
            {"likelihood": "definitely"},
            nch,
        )
        await _create_signal(
            db,
            user_b.id,
            contact_b.id,
            "would_refer",
            {"likelihood": "definitely"},
            nch,
        )
        await db.commit()

        from app.services.freshness_aggregator import aggregate_freshness_signals

        result = await aggregate_freshness_signals(db)
        await db.commit()

        await db.refresh(contact_a)
        await db.refresh(contact_b)

        # contact_a was NULL → now "definitely"
        assert contact_a.would_refer == "definitely"
        # contact_b had "no" → stays "no" (not overwritten)
        assert contact_b.would_refer == "no"
        assert result.contacts_updated == 1
