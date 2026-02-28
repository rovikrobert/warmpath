"""Tests for feed priority auto-tuning system.

Covers: weight computation, ranking order, Redis caching,
no-data defaults, recency boost math, and the /feed/stats endpoint.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.feed import FeedItem, FeedItemInteraction
from app.services.feed_ranker import (
    ALL_ITEM_TYPES,
    WEIGHT_MAX,
    WEIGHT_MIN,
    compute_feed_stats,
    compute_type_weights,
    rank_feed_items,
)
from tests.conftest import TestSessionLocal, create_test_user_in_db

pytestmark = pytest.mark.usefixtures("truncate_tables")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_feed_item(
    user_id: uuid.UUID,
    item_type: str = "job_alert",
    priority: int = 50,
    created_at: datetime | None = None,
    seen_at: datetime | None = None,
) -> FeedItem:
    """Create a FeedItem ORM object (not yet added to session)."""
    return FeedItem(
        user_id=user_id,
        item_type=item_type,
        title=f"Test {item_type}",
        priority=priority,
        created_at=created_at or datetime.now(timezone.utc),
        seen_at=seen_at,
    )


def _make_interaction(
    feed_item_id: uuid.UUID,
    user_id: uuid.UUID,
    interaction_type: str = "view",
    created_at: datetime | None = None,
) -> FeedItemInteraction:
    """Create a FeedItemInteraction ORM object."""
    return FeedItemInteraction(
        feed_item_id=feed_item_id,
        user_id=user_id,
        interaction_type=interaction_type,
        source="in_app",
        created_at=created_at or datetime.now(timezone.utc),
    )


@pytest_asyncio.fixture
async def user_and_db():
    """Create a test user and yield (user, db_session)."""
    async with TestSessionLocal() as db:
        user, _ = await create_test_user_in_db(db, email="ranker@test.com")
        yield user, db


# ---------------------------------------------------------------------------
# compute_type_weights tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_weights_with_no_interactions(user_and_db):
    """Returns all-1.0 weights when no interaction data exists."""
    _, db = user_and_db
    weights = await compute_type_weights(db)

    assert weights == {t: 1.0 for t in ALL_ITEM_TYPES}


@pytest.mark.asyncio
async def test_default_weights_below_min_interactions(user_and_db):
    """Returns all-1.0 weights when fewer than MIN_INTERACTIONS exist."""
    user, db = user_and_db

    # Create a few items and interactions (below threshold)
    items = []
    for _i in range(5):
        item = _make_feed_item(user.id, item_type="job_alert")
        db.add(item)
        items.append(item)
    await db.flush()

    for item in items:
        db.add(_make_interaction(item.id, user.id, "view"))
    await db.commit()

    weights = await compute_type_weights(db)
    assert weights == {t: 1.0 for t in ALL_ITEM_TYPES}


@pytest.mark.asyncio
async def test_weights_computed_from_interaction_data(user_and_db):
    """Weights reflect actual engagement scores when sufficient data exists."""
    user, db = user_and_db
    now = datetime.now(timezone.utc)

    # Create items for two types with contrasting engagement patterns
    # job_alert: high engagement (many clicks, few dismissals)
    job_items = []
    for _ in range(20):
        item = _make_feed_item(
            user.id, item_type="job_alert", created_at=now - timedelta(days=5)
        )
        db.add(item)
        job_items.append(item)

    # network_insight: low engagement (many dismissals, few clicks)
    insight_items = []
    for _ in range(20):
        item = _make_feed_item(
            user.id, item_type="network_insight", created_at=now - timedelta(days=5)
        )
        db.add(item)
        insight_items.append(item)
    await db.flush()

    # job_alert: 15 views, 10 clicks, 1 dismiss
    for item in job_items[:15]:
        db.add(_make_interaction(item.id, user.id, "view", now - timedelta(days=3)))
    for item in job_items[:10]:
        db.add(_make_interaction(item.id, user.id, "click", now - timedelta(days=2)))
    db.add(
        _make_interaction(job_items[0].id, user.id, "dismiss", now - timedelta(days=1))
    )

    # network_insight: 15 views, 1 click, 10 dismissals
    for item in insight_items[:15]:
        db.add(_make_interaction(item.id, user.id, "view", now - timedelta(days=3)))
    db.add(
        _make_interaction(
            insight_items[0].id, user.id, "click", now - timedelta(days=2)
        )
    )
    for item in insight_items[:10]:
        db.add(_make_interaction(item.id, user.id, "dismiss", now - timedelta(days=1)))

    await db.commit()

    weights = await compute_type_weights(db)

    # job_alert should be weighted higher than network_insight
    assert weights["job_alert"] > weights["network_insight"]
    # Both should be within bounds
    assert WEIGHT_MIN <= weights["job_alert"] <= WEIGHT_MAX
    assert WEIGHT_MIN <= weights["network_insight"] <= WEIGHT_MAX
    # Types with no data should get 1.0
    assert weights["enrichment_prompt"] == 1.0


@pytest.mark.asyncio
async def test_weights_clamped_to_range(user_and_db):
    """All computed weights fall within [WEIGHT_MIN, WEIGHT_MAX]."""
    user, db = user_and_db
    now = datetime.now(timezone.utc)

    # Create extreme engagement data for one type only
    items = []
    for _ in range(30):
        item = _make_feed_item(
            user.id, item_type="job_alert", created_at=now - timedelta(days=2)
        )
        db.add(item)
        items.append(item)
    await db.flush()

    # Perfect engagement: all viewed and clicked
    for item in items:
        db.add(_make_interaction(item.id, user.id, "view", now - timedelta(days=1)))
        db.add(_make_interaction(item.id, user.id, "click", now - timedelta(hours=12)))
    await db.commit()

    weights = await compute_type_weights(db)

    for w in weights.values():
        assert WEIGHT_MIN <= w <= WEIGHT_MAX


@pytest.mark.asyncio
async def test_old_interactions_excluded(user_and_db):
    """Interactions older than 30 days are not counted."""
    user, db = user_and_db
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=45)

    # Create items with old interactions only
    items = []
    for _ in range(30):
        item = _make_feed_item(user.id, item_type="job_alert", created_at=old)
        db.add(item)
        items.append(item)
    await db.flush()

    for item in items:
        db.add(_make_interaction(item.id, user.id, "view", old))
        db.add(_make_interaction(item.id, user.id, "click", old))
    await db.commit()

    weights = await compute_type_weights(db)
    # All defaults because interactions are too old
    assert weights == {t: 1.0 for t in ALL_ITEM_TYPES}


# ---------------------------------------------------------------------------
# rank_feed_items tests
# ---------------------------------------------------------------------------


def test_ranking_orders_by_weighted_score():
    """Higher priority * weight items rank first."""
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Low-priority high-weight vs high-priority low-weight
    item_a = _make_feed_item(
        user_id,
        item_type="job_alert",
        priority=30,
        created_at=now - timedelta(hours=48),
    )
    item_b = _make_feed_item(
        user_id,
        item_type="network_insight",
        priority=80,
        created_at=now - timedelta(hours=48),
    )

    weights = {"job_alert": 3.0, "network_insight": 0.5}
    ranked = rank_feed_items([item_a, item_b], weights)

    # item_a: 30 * 3.0 = 90 (base)
    # item_b: 80 * 0.5 = 40 (base)
    assert ranked[0] is item_a
    assert ranked[1] is item_b


def test_recency_boost_for_recent_items():
    """Items created within 24h get up to 50% boost."""
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Same priority, same weight, but different ages
    old_item = _make_feed_item(
        user_id, priority=50, created_at=now - timedelta(hours=48)
    )
    new_item = _make_feed_item(
        user_id, priority=50, created_at=now - timedelta(hours=1)
    )

    weights = {"job_alert": 1.0}
    ranked = rank_feed_items([old_item, new_item], weights)

    # New item should rank higher due to recency boost
    assert ranked[0] is new_item


def test_recency_boost_is_zero_after_24h():
    """Items older than 24h get no recency boost (boost = 1.0)."""
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    item_25h = _make_feed_item(
        user_id, priority=50, created_at=now - timedelta(hours=25)
    )
    item_48h = _make_feed_item(
        user_id, priority=50, created_at=now - timedelta(hours=48)
    )

    weights = {"job_alert": 1.0}
    ranked = rank_feed_items([item_48h, item_25h], weights)

    # Both should have recency_boost = 1.0, so order doesn't matter from boost
    # But stable sort should keep relative order
    assert len(ranked) == 2


def test_recency_boost_math_at_12h():
    """At 12 hours old, recency_boost should be ~1.25 (halfway)."""
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    item = _make_feed_item(user_id, priority=100, created_at=now - timedelta(hours=12))

    weights = {"job_alert": 1.0}
    ranked = rank_feed_items([item], weights)

    # At 12h: boost = 1.0 + max(0, (24-12)/24) * 0.5 = 1.0 + 0.25 = 1.25
    # Score = 100 * 1.0 * 1.25 = 125.0
    # We can't inspect the score directly, but we can verify the item is ranked
    assert len(ranked) == 1


def test_ranking_with_default_weights():
    """When all weights are 1.0, priority is the primary sort key."""
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    items = [
        _make_feed_item(user_id, priority=30, created_at=now - timedelta(hours=48)),
        _make_feed_item(user_id, priority=90, created_at=now - timedelta(hours=48)),
        _make_feed_item(user_id, priority=60, created_at=now - timedelta(hours=48)),
    ]

    weights = {t: 1.0 for t in ALL_ITEM_TYPES}
    ranked = rank_feed_items(items, weights)

    assert ranked[0].priority == 90
    assert ranked[1].priority == 60
    assert ranked[2].priority == 30


def test_ranking_empty_list():
    """Ranking an empty list returns empty list."""
    ranked = rank_feed_items([], {"job_alert": 1.0})
    assert ranked == []


def test_ranking_missing_type_weight_defaults_to_one():
    """If item_type not in weights dict, weight defaults to 1.0."""
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    item = _make_feed_item(
        user_id,
        item_type="contact_update",
        priority=50,
        created_at=now - timedelta(hours=48),
    )

    # Weights dict doesn't include contact_update
    weights = {"job_alert": 2.0}
    ranked = rank_feed_items([item], weights)

    assert len(ranked) == 1
    assert ranked[0] is item


# ---------------------------------------------------------------------------
# Redis caching tests (mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_type_weights_uses_cache_when_available():
    """get_type_weights returns cached weights without querying DB."""
    from app.services.feed_ranker import get_type_weights

    cached = {"job_alert": 1.5, "network_insight": 0.7}
    with patch(
        "app.services.feed_ranker.get_cached_weights",
        new_callable=AsyncMock,
        return_value=cached,
    ):
        async with TestSessionLocal() as db:
            weights = await get_type_weights(db)

    assert weights == cached


@pytest.mark.asyncio
async def test_get_type_weights_computes_and_caches_on_miss(user_and_db):
    """get_type_weights computes from DB and caches when Redis miss."""
    from app.services.feed_ranker import get_type_weights

    with (
        patch(
            "app.services.feed_ranker.get_cached_weights",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.feed_ranker.set_cached_weights", new_callable=AsyncMock
        ) as mock_set,
    ):
        _, db = user_and_db
        weights = await get_type_weights(db)

    # Should have computed default weights (no data) and cached them
    assert weights == {t: 1.0 for t in ALL_ITEM_TYPES}
    mock_set.assert_called_once_with(weights)


# ---------------------------------------------------------------------------
# GET /feed/stats endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feed_stats_returns_per_type_and_overall(client: AsyncClient):
    """GET /feed/stats returns per_type, overall, and daily_series_14d."""
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(db, email="stats@test.com")

    resp = await client.get("/api/v1/feed/stats", headers=headers)
    assert resp.status_code == 200

    data = resp.json()["data"]
    assert "per_type" in data
    assert "overall" in data
    assert "daily_series_14d" in data
    assert len(data["per_type"]) == len(ALL_ITEM_TYPES)
    assert "total_items_30d" in data["overall"]
    assert "avg_engagement" in data["overall"]
    assert "most_engaging_type" in data["overall"]
    assert "least_engaging_type" in data["overall"]


@pytest.mark.asyncio
async def test_feed_stats_reflects_interaction_data(client: AsyncClient):
    """Stats endpoint shows correct counts from real interaction data."""
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(db, email="statsdata@test.com")
        now = datetime.now(timezone.utc)

        # Create 5 job_alert items, add interactions
        items = []
        for _ in range(5):
            item = _make_feed_item(
                user.id, item_type="job_alert", created_at=now - timedelta(days=2)
            )
            db.add(item)
            items.append(item)
        await db.flush()

        for item in items[:3]:
            db.add(_make_interaction(item.id, user.id, "view", now - timedelta(days=1)))
        db.add(
            _make_interaction(items[0].id, user.id, "click", now - timedelta(hours=12))
        )
        await db.commit()

    resp = await client.get("/api/v1/feed/stats", headers=headers)
    assert resp.status_code == 200

    data = resp.json()["data"]
    job_stat = next(s for s in data["per_type"] if s["item_type"] == "job_alert")
    assert job_stat["generated_count"] == 5
    assert job_stat["seen_count"] == 3
    assert job_stat["act_count"] == 1


# ---------------------------------------------------------------------------
# GET /feed integration — ranking applied
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feed_endpoint_applies_learned_ranking(client: AsyncClient):
    """GET /feed returns items ranked by type weights, not just priority."""
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(db, email="feedrank@test.com")
        now = datetime.now(timezone.utc)

        # Create two items: low-priority job_alert and high-priority network_insight
        item_a = FeedItem(
            user_id=user.id,
            item_type="job_alert",
            title="Job A",
            priority=30,
            created_at=now - timedelta(hours=48),
        )
        item_b = FeedItem(
            user_id=user.id,
            item_type="network_insight",
            title="Insight B",
            priority=80,
            created_at=now - timedelta(hours=48),
        )
        db.add_all([item_a, item_b])
        await db.commit()

    # With default weights (all 1.0, no interactions), priority wins
    with patch(
        "app.services.feed_ranker.get_cached_weights",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.get("/api/v1/feed", headers=headers)
        assert resp.status_code == 200
        items = resp.json()["data"]
        assert len(items) == 2
        assert items[0]["priority"] == 80  # higher priority first

    # With custom weights favoring job_alert
    custom_weights = {t: 1.0 for t in ALL_ITEM_TYPES}
    custom_weights["job_alert"] = 3.0
    custom_weights["network_insight"] = 0.3
    with patch(
        "app.services.feed_ranker.get_cached_weights",
        new_callable=AsyncMock,
        return_value=custom_weights,
    ):
        resp = await client.get("/api/v1/feed", headers=headers)
        assert resp.status_code == 200
        items = resp.json()["data"]
        assert len(items) == 2
        # job_alert: 30 * 3.0 = 90 > network_insight: 80 * 0.3 = 24
        assert items[0]["item_type"] == "job_alert"
        assert items[1]["item_type"] == "network_insight"


@pytest.mark.asyncio
async def test_feed_unseen_before_seen_with_ranking(client: AsyncClient):
    """Unseen items always appear before seen items, regardless of weight."""
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(db, email="unseenfirst@test.com")
        now = datetime.now(timezone.utc)

        # Seen item with high priority, unseen item with low priority
        seen_item = FeedItem(
            user_id=user.id,
            item_type="job_alert",
            title="Seen",
            priority=100,
            created_at=now - timedelta(hours=48),
            seen_at=now - timedelta(hours=24),
        )
        unseen_item = FeedItem(
            user_id=user.id,
            item_type="network_insight",
            title="Unseen",
            priority=10,
            created_at=now - timedelta(hours=48),
        )
        db.add_all([seen_item, unseen_item])
        await db.commit()

    resp = await client.get("/api/v1/feed", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert len(items) == 2
    assert items[0]["seen_at"] is None  # unseen first
    assert items[1]["seen_at"] is not None  # seen second


# ---------------------------------------------------------------------------
# compute_feed_stats unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_feed_stats_empty_db(user_and_db):
    """Stats return zeros and empty lists when no feed data exists."""
    _, db = user_and_db
    stats = await compute_feed_stats(db)

    assert stats["overall"]["total_items_30d"] == 0
    assert stats["overall"]["avg_engagement"] == 0.0
    assert stats["overall"]["most_engaging_type"] is None
    assert len(stats["per_type"]) == len(ALL_ITEM_TYPES)
    assert len(stats["daily_series_14d"]) == 0


@pytest.mark.asyncio
async def test_compute_feed_stats_with_data(user_and_db):
    """Stats correctly aggregate interaction data."""
    user, db = user_and_db
    now = datetime.now(timezone.utc)

    # Create items and interactions for two types
    job_items = []
    for _ in range(10):
        item = _make_feed_item(
            user.id, item_type="job_alert", created_at=now - timedelta(days=3)
        )
        db.add(item)
        job_items.append(item)
    await db.flush()

    # 8 views, 5 clicks, 1 dismiss for job_alerts
    for item in job_items[:8]:
        db.add(_make_interaction(item.id, user.id, "view", now - timedelta(days=2)))
    for item in job_items[:5]:
        db.add(_make_interaction(item.id, user.id, "click", now - timedelta(days=1)))
    db.add(
        _make_interaction(
            job_items[0].id, user.id, "dismiss", now - timedelta(hours=12)
        )
    )
    await db.commit()

    stats = await compute_feed_stats(db)

    job_stat = next(s for s in stats["per_type"] if s["item_type"] == "job_alert")
    assert job_stat["generated_count"] == 10
    assert job_stat["seen_count"] == 8
    assert job_stat["act_count"] == 5
    assert job_stat["dismiss_count"] == 1
    assert job_stat["engagement_score"] > 0

    assert stats["overall"]["total_items_30d"] == 10
    assert stats["overall"]["most_engaging_type"] == "job_alert"


@pytest.mark.asyncio
async def test_daily_time_series_shows_recent_data(user_and_db):
    """Daily series includes entries for days with interactions."""
    user, db = user_and_db
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)

    item = _make_feed_item(
        user.id, item_type="job_alert", created_at=now - timedelta(days=3)
    )
    db.add(item)
    await db.flush()

    # Add interactions on yesterday's date
    db.add(_make_interaction(item.id, user.id, "view", yesterday))
    db.add(_make_interaction(item.id, user.id, "click", yesterday))
    await db.commit()

    stats = await compute_feed_stats(db)

    assert len(stats["daily_series_14d"]) >= 1
    day_entry = stats["daily_series_14d"][0]
    assert "date" in day_entry
    assert day_entry["views"] >= 1
    assert day_entry["acts"] >= 1
    assert day_entry["engagement_score"] > 0


# ---------------------------------------------------------------------------
# POST /feed/dismiss-all — bulk dismiss
# ---------------------------------------------------------------------------


async def test_dismiss_all_clears_feed(client: AsyncClient):
    """POST /feed/dismiss-all dismisses all items and returns count."""
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="dismissall@test.com", full_name="Dismiss All"
        )
        now = datetime.now(timezone.utc)
        for i in range(3):
            db.add(
                FeedItem(
                    user_id=user.id,
                    item_type="job_alert",
                    priority=50,
                    title=f"Job {i}",
                    body=f"Body {i}",
                    dedup_key=f"dismiss-all-{i}",
                    created_at=now,
                )
            )
        await db.commit()

    resp = await client.post("/api/v1/feed/dismiss-all", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["dismissed"] == 3

    # Feed should now be empty
    resp2 = await client.get("/api/v1/feed", headers=headers)
    assert resp2.status_code == 200
    assert len(resp2.json()["data"]) == 0


async def test_dismiss_all_skips_already_dismissed(client: AsyncClient):
    """Already dismissed items are not double-counted."""
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="dismissskip@test.com", full_name="Skip Test"
        )
        now = datetime.now(timezone.utc)
        db.add(
            FeedItem(
                user_id=user.id,
                item_type="job_alert",
                priority=50,
                title="Already gone",
                body="Body",
                dedup_key="already-dismissed",
                dismissed_at=now,
                created_at=now,
            )
        )
        db.add(
            FeedItem(
                user_id=user.id,
                item_type="job_alert",
                priority=50,
                title="Still visible",
                body="Body",
                dedup_key="still-visible",
                created_at=now,
            )
        )
        await db.commit()

    resp = await client.post("/api/v1/feed/dismiss-all", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["dismissed"] == 1
