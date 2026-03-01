"""Celery task failure escalation — bridges task errors to FindingStore + Telegram.

When a Celery task fails, this utility:
1. Records the failure in FindingStore (dedup via hash)
2. Sends a Telegram alert if it's a NEW finding (not already known)
3. Degrades gracefully if Redis is unavailable
"""

import logging
import os
import traceback
from typing import Any

logger = logging.getLogger(__name__)


def _get_finding_store() -> Any:
    """Lazy import to avoid circular deps and allow mocking."""
    from app.agent_runtime.finding_store import FindingStore
    from app.config import settings

    return FindingStore(redis_url=settings.REDIS_URL)


async def _send_telegram_alert(message: str) -> None:
    """Best-effort Telegram notification."""
    import httpx

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message},
            )
    except Exception:
        logger.warning("Telegram task escalation failed", exc_info=True)


async def escalate_task_failure(
    task_name: str,
    error: Exception,
    severity: str = "high",
) -> None:
    """Escalate a Celery task failure to FindingStore + Telegram.

    Only sends Telegram alert for NEW findings (first occurrence).
    Known findings (already in FindingStore) are silently deduped.
    """
    error_type = type(error).__name__
    error_msg = str(error)[:200]

    # Get last app-level traceback frame
    tb = traceback.format_exception(type(error), error, error.__traceback__)
    last_frame = ""
    for line in reversed(tb):
        if "File " in line and "/app/" in line:
            last_frame = line.strip()[:150]
            break

    finding = {
        "source_team": "engineering",
        "category": "celery_task_failure",
        "title": f"Task {task_name} failed: {error_type}",
        "severity": severity,
        "metadata": {
            "task_name": task_name,
            "error_type": error_type,
            "error_message": error_msg,
            "traceback_frame": last_frame,
        },
    }

    is_new = True
    try:
        store = _get_finding_store()
        new_findings, _ = await store.classify_findings([finding])
        is_new = len(new_findings) > 0
    except Exception:
        logger.warning("FindingStore unavailable for task escalation", exc_info=True)

    if is_new:
        message = "\n".join(
            [
                f"[!!] Celery Task Failed: {task_name}",
                "",
                f"{error_type}: {error_msg}",
                last_frame if last_frame else "",
                "",
                "Check Celery logs for full trace.",
            ]
        )
        await _send_telegram_alert(message)
