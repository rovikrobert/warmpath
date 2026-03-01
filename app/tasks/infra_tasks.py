"""Infrastructure maintenance tasks.

Lightweight Celery tasks for platform health — rate limiter watchdog,
Redis Stream cleanup, stuck upload detection, etc.
"""

import logging

from app.celery_app import celery_app
from app.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.infra_tasks.rate_limiter_watchdog")
def rate_limiter_watchdog() -> None:
    """Top up rate limiter tokens lost to worker crashes.

    Runs every 5 minutes via Beat. Ensures all configured AI provider
    rate limiters have their tokens available.
    """
    from app.utils.rate_limiter import top_up_tokens_sync

    # Always top up Anthropic (used for matcher, scorer, coach — not just cleaner)
    top_up_tokens_sync("anthropic", settings.ANTHROPIC_MAX_CONCURRENT)

    # Top up all configured cleaning providers
    if settings.GOOGLE_API_KEY or settings.GOOGLE_SERVICE_ACCOUNT_JSON:
        top_up_tokens_sync("gemini", settings.GOOGLE_MAX_CONCURRENT)
    if settings.OPENAI_API_KEY:
        top_up_tokens_sync("openai", settings.OPENAI_MAX_CONCURRENT)
    if settings.GROQ_API_KEY:
        top_up_tokens_sync("groq", settings.GROQ_MAX_CONCURRENT)
    logger.debug("Rate limiter watchdog completed")


@celery_app.task(name="app.tasks.infra_tasks.redis_stream_janitor")
def redis_stream_janitor() -> None:
    """Clean up orphaned Redis Streams older than TTL.

    Runs every 30 minutes via Beat. Catches streams left behind by
    crashed pipeline tasks.
    """
    import asyncio

    asyncio.run(_janitor_async())


async def _janitor_async() -> None:
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            # Scan for csv: streams
            cursor = 0
            while True:
                cursor, keys = await client.scan(cursor, match="csv:*", count=100)
                for key in keys:
                    try:
                        info = await client.xinfo_stream(key)
                        length = info.get("length", 0)
                        # If stream is empty and has been idle, delete it
                        if length == 0:
                            await client.delete(key)
                            logger.info("Janitor: deleted empty stream %s", key)
                    except Exception:
                        # Stream might have been deleted between scan and info
                        pass
                if cursor == 0:
                    break
        finally:
            await client.aclose()
    except Exception:
        logger.debug("Stream janitor failed", exc_info=True)


# ---------------------------------------------------------------------------
# Stuck upload watchdog
# ---------------------------------------------------------------------------

# Thresholds (seconds) before an upload is considered stuck
_QUEUED_THRESHOLD = 600  # 10 min — worker should pick up within seconds
_PROCESSING_THRESHOLD = 900  # 15 min — matches Celery soft_time_limit
_BATCH_THRESHOLD = 7200  # 2 hr — Gemini batch API is slow


@celery_app.task(name="app.tasks.infra_tasks.stuck_upload_watchdog")
def stuck_upload_watchdog() -> None:
    """Detect and fail stuck CSV uploads, notify affected users.

    Runs every 15 minutes via Beat. Finds uploads stuck in queued/processing
    beyond their threshold, marks them failed, and sends the user a
    "your upload failed" email so they can re-upload.
    """
    import asyncio

    asyncio.run(_stuck_upload_watchdog_run())


async def _stuck_upload_watchdog_run() -> None:
    """Celery entry point — creates its own DB session."""
    from app.database import _get_engine, _get_session_factory

    await _get_engine().dispose()
    factory = _get_session_factory()

    async with factory() as db:
        failed_count, notified_count = await detect_and_fail_stuck_uploads(db)

    if failed_count > 0:
        await _send_watchdog_telegram_alert(failed_count, notified_count)


async def _send_watchdog_telegram_alert(failed_count: int, notified_count: int) -> None:
    """Send a Telegram alert when the watchdog marks stuck uploads as failed."""
    import os

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.debug("Telegram not configured — skipping watchdog alert")
        return

    msg = (
        f"\u26a0\ufe0f Upload watchdog: {failed_count} stuck upload(s) marked failed, "
        f"{notified_count} user(s) emailed."
    )
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": msg},
            )
        logger.info("Watchdog Telegram alert sent")
    except Exception:
        logger.warning("Failed to send watchdog Telegram alert", exc_info=True)


async def detect_and_fail_stuck_uploads(db) -> tuple[int, int]:
    """Core logic: find stuck uploads, mark failed, notify users.

    Returns (failed_count, notified_count). Callable from tests with
    a test DB session.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.models.contact import CsvUpload
    from app.models.user import User
    from app.services.email_engagement import send_upload_failure_notification

    now = datetime.now(timezone.utc)

    # Find all uploads still in queued or processing
    result = await db.execute(
        select(CsvUpload).where(
            CsvUpload.status.in_(["queued", "pending", "processing"]),
            CsvUpload.completed_at.is_(None),
        )
    )
    uploads = list(result.scalars())

    failed_count = 0
    notified_count = 0

    for upload in uploads:
        ref_time = upload.started_at or upload.created_at
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)
        age = (now - ref_time).total_seconds()

        if upload.batch_job_name:
            threshold = _BATCH_THRESHOLD
        elif upload.status == "processing":
            threshold = _PROCESSING_THRESHOLD
        else:
            threshold = _QUEUED_THRESHOLD

        if age <= threshold:
            continue

        # Mark as failed
        upload.status = "failed"
        upload.error_message = "Processing timed out — please re-upload"
        upload.completed_at = now
        failed_count += 1

        # Load user and send notification email
        user_result = await db.execute(select(User).where(User.id == upload.user_id))
        user = user_result.scalar_one_or_none()
        if user:
            sent = await send_upload_failure_notification(user, upload.id, db)
            if sent:
                notified_count += 1

        logger.warning(
            "Stuck upload watchdog: upload %s (user %s) stuck in '%s' for %.0fs — marked failed",
            upload.id,
            upload.user_id,
            upload.status,
            age,
        )

    if failed_count:
        await db.commit()
        logger.info(
            "Stuck upload watchdog: %d uploads failed, %d users notified",
            failed_count,
            notified_count,
        )
    else:
        logger.debug("Stuck upload watchdog: no stuck uploads found")

    return failed_count, notified_count
