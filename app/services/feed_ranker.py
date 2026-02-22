"""Feed priority auto-tuning service.

Uses interaction data (views, clicks, dismissals) to learn which feed item
types are most engaging, then adjusts ranking weights so that high-engagement
types surface first.

Weight recomputation runs every 6 hours via Celery and is cached in Redis.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feed import FeedItem, FeedItemInteraction

logger = logging.getLogger(__name__)

# All known item types (from CHECK constraint on feed_items.item_type)
ALL_ITEM_TYPES = [
    "job_alert",
    "contact_update",
    "enrichment_prompt",
    "marketplace_signal",
    "outcome_check",
    "platform_activity",
    "network_insight",
    "follow_up_nudge",
    "intro_approval_nudge",
    "manual_send_reminder",
]

# Minimum total interactions before we trust learned weights
MIN_INTERACTIONS = 50

# Clamp range for weight multipliers
WEIGHT_MIN = 0.3
WEIGHT_MAX = 3.0

# Redis cache settings
CACHE_KEY = "feed_weights:global"
CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 hours


async def compute_type_weights(db: AsyncSession) -> dict[str, float]:
    """Compute engagement-based weight multipliers per feed item type.

    Looks at the last 30 days of interaction data. For each item_type:
    - seen_rate  = items seen / items generated
    - act_rate   = items acted on / items seen  (key metric)
    - dismiss_rate = items dismissed / items seen  (negative signal)
    - engagement_score = (act_rate * 2.0) - (dismiss_rate * 1.0) + (seen_rate * 0.1)

    Returns dict mapping item_type -> weight multiplier, normalized so
    average = 1.0, clamped to [0.3, 3.0].

    Falls back to all-1.0 weights if fewer than MIN_INTERACTIONS total.
    """
    since = datetime.now(timezone.utc) - timedelta(days=30)

    # Count total interactions to check data sufficiency
    total_result = await db.execute(
        select(func.count(FeedItemInteraction.id)).where(
            FeedItemInteraction.created_at >= since,
        )
    )
    total_interactions = total_result.scalar_one()

    if total_interactions < MIN_INTERACTIONS:
        return {t: 1.0 for t in ALL_ITEM_TYPES}

    # Count generated items per type (last 30 days)
    generated_q = (
        select(
            FeedItem.item_type,
            func.count(FeedItem.id).label("generated"),
        )
        .where(FeedItem.created_at >= since)
        .group_by(FeedItem.item_type)
    )
    generated_result = await db.execute(generated_q)
    generated_map = {row.item_type: row.generated for row in generated_result}

    # Count interactions by type: view, click, dismiss — joined via feed_item
    interaction_q = (
        select(
            FeedItem.item_type,
            func.count(
                case(
                    (
                        FeedItemInteraction.interaction_type == "view",
                        FeedItemInteraction.id,
                    ),
                )
            ).label("seen_count"),
            func.count(
                case(
                    (
                        FeedItemInteraction.interaction_type == "click",
                        FeedItemInteraction.id,
                    ),
                )
            ).label("act_count"),
            func.count(
                case(
                    (
                        FeedItemInteraction.interaction_type == "dismiss",
                        FeedItemInteraction.id,
                    ),
                )
            ).label("dismiss_count"),
        )
        .join(FeedItem, FeedItemInteraction.feed_item_id == FeedItem.id)
        .where(FeedItemInteraction.created_at >= since)
        .group_by(FeedItem.item_type)
    )
    interaction_result = await db.execute(interaction_q)
    interaction_map = {
        row.item_type: {
            "seen": row.seen_count,
            "act": row.act_count,
            "dismiss": row.dismiss_count,
        }
        for row in interaction_result
    }

    # Compute raw engagement scores
    raw_scores: dict[str, float] = {}
    for item_type in ALL_ITEM_TYPES:
        generated = generated_map.get(item_type, 0)
        stats = interaction_map.get(item_type, {"seen": 0, "act": 0, "dismiss": 0})

        if generated == 0 or stats["seen"] == 0:
            raw_scores[item_type] = 0.0
            continue

        seen_rate = stats["seen"] / generated
        act_rate = stats["act"] / stats["seen"]
        dismiss_rate = stats["dismiss"] / stats["seen"]

        raw_scores[item_type] = (
            (act_rate * 2.0) - (dismiss_rate * 1.0) + (seen_rate * 0.1)
        )

    # Normalize so average = 1.0
    scores = list(raw_scores.values())
    non_zero = [s for s in scores if s != 0.0]
    if not non_zero:
        return {t: 1.0 for t in ALL_ITEM_TYPES}

    avg = sum(non_zero) / len(non_zero)
    if avg == 0:
        return {t: 1.0 for t in ALL_ITEM_TYPES}

    weights: dict[str, float] = {}
    for item_type, score in raw_scores.items():
        if score == 0.0:
            weights[item_type] = 1.0  # no data → neutral
        else:
            w = score / avg
            weights[item_type] = max(WEIGHT_MIN, min(WEIGHT_MAX, w))

    return weights


def rank_feed_items(
    items: list[FeedItem],
    type_weights: dict[str, float],
) -> list[FeedItem]:
    """Score and sort feed items by learned type weight * priority * recency.

    final_score = item.priority * type_weight * recency_boost
    recency_boost = 1.0 + max(0, (24 - hours_since_created) / 24) * 0.5

    Items created less than 24h ago get up to +50% boost (linear decay).
    """
    now = datetime.now(timezone.utc)

    def _score(item: FeedItem) -> float:
        weight = type_weights.get(item.item_type, 1.0)
        created = item.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        hours_since = (now - created).total_seconds() / 3600.0
        recency_boost = 1.0 + max(0.0, (24.0 - hours_since) / 24.0) * 0.5
        return item.priority * weight * recency_boost

    return sorted(items, key=_score, reverse=True)


# ---------------------------------------------------------------------------
# Redis cache helpers
# ---------------------------------------------------------------------------


def _get_redis_client():
    """Get async Redis client, or None if unavailable."""
    try:
        import redis.asyncio as aioredis

        from app.config import settings

        return aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception:
        logger.debug("Redis not available for feed weight caching")
        return None


async def get_cached_weights() -> dict[str, float] | None:
    """Read cached type weights from Redis. Returns None on miss/error."""
    client = _get_redis_client()
    if not client:
        return None
    try:
        raw = await client.get(CACHE_KEY)
        if raw:
            return json.loads(raw)
        return None
    except Exception:
        logger.debug("Redis cache read failed for feed weights")
        return None
    finally:
        await client.aclose()


async def set_cached_weights(weights: dict[str, float]) -> None:
    """Write type weights to Redis with TTL."""
    client = _get_redis_client()
    if not client:
        return
    try:
        await client.set(CACHE_KEY, json.dumps(weights), ex=CACHE_TTL_SECONDS)
    except Exception:
        logger.debug("Redis cache write failed for feed weights")
    finally:
        await client.aclose()


async def get_type_weights(db: AsyncSession) -> dict[str, float]:
    """Get type weights, preferring cached values. Falls back to DB compute."""
    cached = await get_cached_weights()
    if cached is not None:
        return cached

    weights = await compute_type_weights(db)
    await set_cached_weights(weights)
    return weights


# ---------------------------------------------------------------------------
# Stats query for debug endpoint
# ---------------------------------------------------------------------------


async def compute_feed_stats(db: AsyncSession) -> dict:
    """Compute per-type feed engagement statistics for the debug endpoint.

    Returns per-type stats (generated, seen, act, dismiss, engagement, weight),
    overall metrics, and a 14-day daily time series.
    """
    since_30d = datetime.now(timezone.utc) - timedelta(days=30)
    since_14d = datetime.now(timezone.utc) - timedelta(days=14)

    # Per-type generated counts
    gen_q = (
        select(
            FeedItem.item_type,
            func.count(FeedItem.id).label("generated_count"),
        )
        .where(FeedItem.created_at >= since_30d)
        .group_by(FeedItem.item_type)
    )
    gen_result = await db.execute(gen_q)
    gen_map = {row.item_type: row.generated_count for row in gen_result}

    # Per-type interaction counts
    int_q = (
        select(
            FeedItem.item_type,
            func.count(
                case(
                    (
                        FeedItemInteraction.interaction_type == "view",
                        FeedItemInteraction.id,
                    ),
                )
            ).label("seen_count"),
            func.count(
                case(
                    (
                        FeedItemInteraction.interaction_type == "click",
                        FeedItemInteraction.id,
                    ),
                )
            ).label("act_count"),
            func.count(
                case(
                    (
                        FeedItemInteraction.interaction_type == "dismiss",
                        FeedItemInteraction.id,
                    ),
                )
            ).label("dismiss_count"),
        )
        .join(FeedItem, FeedItemInteraction.feed_item_id == FeedItem.id)
        .where(FeedItemInteraction.created_at >= since_30d)
        .group_by(FeedItem.item_type)
    )
    int_result = await db.execute(int_q)
    int_map = {
        row.item_type: {
            "seen": row.seen_count,
            "act": row.act_count,
            "dismiss": row.dismiss_count,
        }
        for row in int_result
    }

    # Compute current weights
    weights = await compute_type_weights(db)

    # Build per-type stats
    type_stats = []
    total_items = 0
    engagement_scores = []
    for item_type in ALL_ITEM_TYPES:
        generated = gen_map.get(item_type, 0)
        stats = int_map.get(item_type, {"seen": 0, "act": 0, "dismiss": 0})
        total_items += generated

        if generated > 0 and stats["seen"] > 0:
            seen_rate = stats["seen"] / generated
            act_rate = stats["act"] / stats["seen"]
            dismiss_rate = stats["dismiss"] / stats["seen"]
            eng = (act_rate * 2.0) - (dismiss_rate * 1.0) + (seen_rate * 0.1)
        else:
            eng = 0.0

        engagement_scores.append(eng)
        type_stats.append(
            {
                "item_type": item_type,
                "generated_count": generated,
                "seen_count": stats["seen"],
                "act_count": stats["act"],
                "dismiss_count": stats["dismiss"],
                "engagement_score": round(eng, 4),
                "current_weight": round(weights.get(item_type, 1.0), 4),
            }
        )

    # Sort by engagement descending
    type_stats.sort(key=lambda x: x["engagement_score"], reverse=True)

    # Overall
    non_zero_eng = [e for e in engagement_scores if e != 0.0]
    avg_engagement = (
        round(sum(non_zero_eng) / len(non_zero_eng), 4) if non_zero_eng else 0.0
    )
    most_engaging = (
        type_stats[0]["item_type"]
        if type_stats and type_stats[0]["engagement_score"] > 0
        else None
    )
    least_engaging = (
        type_stats[-1]["item_type"]
        if type_stats and type_stats[-1]["engagement_score"] > 0
        else None
    )

    # 14-day daily time series
    # Use SQLite-compatible date extraction via func.date for created_at
    daily_q = (
        select(
            func.date(FeedItemInteraction.created_at).label("day"),
            func.count(
                case(
                    (
                        FeedItemInteraction.interaction_type == "click",
                        FeedItemInteraction.id,
                    ),
                )
            ).label("acts"),
            func.count(
                case(
                    (
                        FeedItemInteraction.interaction_type == "dismiss",
                        FeedItemInteraction.id,
                    ),
                )
            ).label("dismissals"),
            func.count(
                case(
                    (
                        FeedItemInteraction.interaction_type == "view",
                        FeedItemInteraction.id,
                    ),
                )
            ).label("views"),
            func.count(FeedItemInteraction.id).label("total"),
        )
        .where(FeedItemInteraction.created_at >= since_14d)
        .group_by(func.date(FeedItemInteraction.created_at))
        .order_by(func.date(FeedItemInteraction.created_at))
    )
    daily_result = await db.execute(daily_q)
    daily_series = []
    for row in daily_result:
        views = row.views if row.views else 0
        acts = row.acts if row.acts else 0
        dismissals = row.dismissals if row.dismissals else 0
        eng = (
            (acts / views * 2.0) - (dismissals / views * 1.0) + 0.1
            if views > 0
            else 0.0
        )
        daily_series.append(
            {
                "date": str(row.day),
                "views": views,
                "acts": acts,
                "dismissals": dismissals,
                "total_interactions": row.total,
                "engagement_score": round(eng, 4),
            }
        )

    return {
        "per_type": type_stats,
        "overall": {
            "total_items_30d": total_items,
            "avg_engagement": avg_engagement,
            "most_engaging_type": most_engaging,
            "least_engaging_type": least_engaging,
        },
        "daily_series_14d": daily_series,
    }
