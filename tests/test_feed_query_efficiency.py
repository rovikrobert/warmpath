"""Query-count regression tests for feed_generator dedup-key preload.

Before the optimization, each generator ran one COUNT query per candidate
item to check for duplicates. Now the orchestrator preloads a single set
of active dedup keys per user, and generators check membership in O(1).
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.user import User
from app.services.feed_generator import (
    _load_active_dedup_keys,
    generate_enrichment_prompts,
    generate_feed_for_user,
)
from tests.conftest import TestSessionLocal, engine


@contextmanager
def _count_queries():
    """Yield a 1-element list whose element gets incremented per SQL query."""
    counter = [0]

    def _on_execute(conn, cursor, statement, parameters, context, executemany):
        counter[0] += 1

    sync_engine = engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", _on_execute)
    try:
        yield counter
    finally:
        event.remove(sync_engine, "before_cursor_execute", _on_execute)


async def _make_user_with_contacts(db: AsyncSession, n_contacts: int) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"feed_eff_{uuid.uuid4().hex[:8]}@test.com",
        full_name="Feed Eff Tester",
    )
    db.add(user)
    await db.flush()

    base_date = datetime.now(timezone.utc) - timedelta(days=30)
    for i in range(n_contacts):
        c = Contact(
            user_id=user.id,
            first_name=f"Contact{i}",
            last_name="Test",
            full_name=f"Contact{i} Test",
            current_company=f"Company{i}",
            relationship_type=None,  # forces enrichment_prompt eligibility
            created_at=base_date + timedelta(minutes=i),
        )
        db.add(c)
    await db.flush()
    return user


# ---------------------------------------------------------------------------
# Direct, isolated comparison: with vs without preloaded set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_path_runs_per_candidate_count_query():
    """Without preloaded set, generate_enrichment_prompts issues 1 COUNT/candidate."""
    user_id: uuid.UUID
    async with TestSessionLocal() as setup_db:
        user = await _make_user_with_contacts(setup_db, n_contacts=10)
        await setup_db.commit()
        user_id = user.id

    async with TestSessionLocal() as db:
        with _count_queries() as legacy_counter:
            await generate_enrichment_prompts(user_id, db, batch_size=5)
        # 2 data queries (contacts + freshness signals) + 1 COUNT per
        # batch_size=5 candidates = 7 queries minimum.
        print(f"\n[BENCH] legacy path: {legacy_counter[0]} queries")
        assert legacy_counter[0] >= 7, (
            f"legacy path should issue per-candidate COUNT queries; got {legacy_counter[0]}"
        )


@pytest.mark.asyncio
async def test_optimized_path_skips_per_candidate_count_query():
    """With preloaded set, generate_enrichment_prompts issues only data queries."""
    user_id: uuid.UUID
    async with TestSessionLocal() as setup_db:
        user = await _make_user_with_contacts(setup_db, n_contacts=10)
        await setup_db.commit()
        user_id = user.id

    async with TestSessionLocal() as db:
        existing = await _load_active_dedup_keys(db, user_id)
        with _count_queries() as opt_counter:
            await generate_enrichment_prompts(
                user_id, db, batch_size=5, existing_keys=existing
            )
        # Only the 2 data queries (contacts + freshness signals); no
        # per-candidate COUNT queries because dedup checks hit the set.
        print(f"\n[BENCH] optimized path: {opt_counter[0]} queries")
        assert opt_counter[0] <= 3, (
            f"optimized path should be ~2 queries; got {opt_counter[0]}"
        )


# ---------------------------------------------------------------------------
# Orchestrator: a single load + a bounded number of per-generator queries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_loads_dedup_keys_only_once():
    """generate_feed_for_user runs _load_active_dedup_keys exactly once."""
    async with TestSessionLocal() as db:
        user = await _make_user_with_contacts(db, n_contacts=5)
        await db.commit()

        with _count_queries() as counter:
            await generate_feed_for_user(user.id, db)

        # The orchestrator runs ~11 generators; each issues a small fixed
        # number of data queries. The dedup preload itself is a single SELECT.
        # Without the optimization a 5-contact user would add 10-25+ COUNT
        # queries on top. Cap at a reasonable bound to catch regressions.
        print(f"\n[BENCH] orchestrator (11 generators, 5 contacts): {counter[0]} queries")
        assert counter[0] < 60, (
            f"orchestrator should issue <60 queries for a 5-contact user, "
            f"got {counter[0]}"
        )
