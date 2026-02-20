"""Celery tasks for background feed generation.

These tasks run on Railway cron schedules to populate the feed_items table
with personalized insights for each active user. The feed is the core
engagement driver — it's what makes WarmPath "come to you."
"""

import asyncio
import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Bridge async code into sync Celery task context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _get_session_factory():
    """Create an async session factory for Celery tasks (own connection)."""
    from app.database import _get_session_factory

    return _get_session_factory()


# ---------------------------------------------------------------------------
# Main feed generation task — runs every 4 hours
# ---------------------------------------------------------------------------


@celery_app.task(name="app.tasks.feed_tasks.generate_feed_all_users")
def generate_feed_all_users():
    """Generate feed items for all recently active users.

    Runs all 6 generators (job_alerts, enrichment_prompts, outcome_checks,
    marketplace_signals, follow_up_nudges, network_insights) for each user
    who had activity in the last 14 days.

    Schedule: Every 4 hours (0:00, 4:00, 8:00, 12:00, 16:00, 20:00 UTC)
    """

    async def _run():
        from app.services.feed_generator import generate_feed_for_all_active_users

        async with _get_session_factory()() as db:
            try:
                total = await generate_feed_for_all_active_users(db)
                logger.info("Feed generation task complete: %d items", total)
                return total
            except Exception:
                logger.exception("Feed generation task failed")
                await db.rollback()
                return 0

    return _run_async(_run())


# ---------------------------------------------------------------------------
# Cleanup task — remove expired feed items weekly
# ---------------------------------------------------------------------------


@celery_app.task(name="app.tasks.feed_tasks.cleanup_expired_feed_items")
def cleanup_expired_feed_items():
    """Delete feed items that have expired or been dismissed > 30 days ago.

    Keeps the feed_items table lean. Interaction data in
    feed_item_interactions is preserved for analytics.

    Schedule: Weekly (Sunday 3:00 AM UTC)
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete, or_

    async def _run():
        from app.models.feed import FeedItem

        async with _get_session_factory()() as db:
            try:
                now = datetime.now(timezone.utc)
                thirty_days_ago = now - timedelta(days=30)

                result = await db.execute(
                    delete(FeedItem).where(
                        or_(
                            # Expired items
                            FeedItem.expires_at <= now,
                            # Long-dismissed items
                            FeedItem.dismissed_at <= thirty_days_ago,
                        )
                    )
                )
                await db.commit()
                count = result.rowcount
                logger.info("Cleaned up %d expired/dismissed feed items", count)
                return count
            except Exception:
                logger.exception("Feed cleanup task failed")
                await db.rollback()
                return 0

    return _run_async(_run())


# ---------------------------------------------------------------------------
# Smart digest email task — replaces basic weekly digest with feed-powered one
# ---------------------------------------------------------------------------


@celery_app.task(name="app.tasks.feed_tasks.send_smart_digest")
def send_smart_digest():
    """Send email digest with top 3 unseen feed items per active user.

    This replaces the basic weekly digest (which just counted searches/intros)
    with a feed-powered digest that surfaces the most valuable unseen insights.

    Schedule: Monday + Thursday 8:00 AM UTC (twice weekly for engagement)
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func, select

    async def _run():
        from app.models.enrichment import UsageLog

        async with _get_session_factory()() as db:
            try:
                since = datetime.now(timezone.utc) - timedelta(days=7)
                active_users = await db.execute(
                    select(func.distinct(UsageLog.user_id)).where(
                        UsageLog.created_at >= since,
                    )
                )
                user_ids = [row[0] for row in active_users.all()]

                from app.services.email_engagement import send_smart_digest_email

                sent = 0
                for uid in user_ids:
                    try:
                        was_sent = await send_smart_digest_email(uid, db)
                        if was_sent:
                            sent += 1
                    except Exception:
                        logger.warning("Smart digest failed for user %s", uid)

                await db.commit()
                logger.info(
                    "Smart digest: prepared for %d/%d active users",
                    sent,
                    len(user_ids),
                )
                return sent
            except Exception:
                logger.exception("Smart digest task failed")
                await db.rollback()
                return 0

    return _run_async(_run())
