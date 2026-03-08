"""Celery tasks for engagement email campaigns.

Each task creates its own async DB session and calls the corresponding
service function. Designed to run via Celery Beat on a cron schedule.
"""

import asyncio
import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async function from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _run_email_task(task_name: str, func_name: str) -> int:
    """Shared runner: create async session, call service function, return count."""
    from app.database import _get_engine, _get_session_factory
    from app.services import email_engagement

    await _get_engine().dispose()

    async with _get_session_factory()() as db:
        try:
            fn = getattr(email_engagement, func_name)
            count = await fn(db)
            logger.info("[%s] sent %d emails", task_name, count)
            return count
        except Exception as exc:
            logger.exception("[%s] failed", task_name)
            await db.rollback()
            try:
                from app.utils.task_escalation import escalate_task_failure

                await escalate_task_failure(
                    task_name=task_name, error=exc, severity="high"
                )
            except Exception:
                logger.warning("[%s] escalation also failed", task_name)
            return 0


@celery_app.task(name="app.tasks.email_tasks.send_csv_reminder_d1")
def send_csv_reminder_d1() -> int:
    return _run_async(_run_email_task("csv_reminder_d1", "send_csv_reminder_d1"))


@celery_app.task(name="app.tasks.email_tasks.send_csv_reminder_d3")
def send_csv_reminder_d3() -> int:
    return _run_async(_run_email_task("csv_reminder_d3", "send_csv_reminder_d3"))


@celery_app.task(name="app.tasks.email_tasks.send_nh_sharing_d2")
def send_nh_sharing_d2() -> int:
    return _run_async(_run_email_task("nh_sharing_d2", "send_nh_sharing_reminder_d2"))


@celery_app.task(name="app.tasks.email_tasks.send_first_search_d2")
def send_first_search_d2() -> int:
    return _run_async(_run_email_task("first_search_d2", "send_first_search_nudge_d2"))


@celery_app.task(name="app.tasks.email_tasks.send_intro_pending_24h")
def send_intro_pending_24h() -> int:
    return _run_async(
        _run_email_task("intro_pending_24h", "send_intro_pending_reminder")
    )


@celery_app.task(name="app.tasks.email_tasks.send_weekly_digest")
def send_weekly_digest() -> int:
    return _run_async(_run_email_task("weekly_digest", "send_weekly_digest"))


@celery_app.task(name="app.tasks.email_tasks.send_reengagement_d30")
def send_reengagement_d30() -> int:
    return _run_async(_run_email_task("reengagement_d30", "send_reengagement_d30"))


@celery_app.task(name="app.tasks.email_tasks.send_reengagement_d90")
def send_reengagement_d90() -> int:
    return _run_async(_run_email_task("reengagement_d90", "send_reengagement_d90"))


@celery_app.task(name="app.tasks.email_tasks.send_credit_expiry_nudge")
def send_credit_expiry_nudge() -> int:
    return _run_async(
        _run_email_task("credit_expiry_nudge", "send_credit_expiry_nudge")
    )
