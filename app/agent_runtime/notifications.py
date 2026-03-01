"""Telegram notifications for the agent runtime.

Handles KPI anomaly alerts. Scheduled scan briefs are handled by the CoS
daily/weekly pipeline (agents.chief_of_staff.cos_agent) which produces a
richer unified brief with per-team health, Notion sync, and Telegram output.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_DEDUP_TTL = 86400  # 24 hours


async def _mark_notified(redis_url: str, notification_type: str, today: str) -> bool:
    """Set Redis dedup key. Returns True if already notified (duplicate)."""
    import redis.asyncio as aioredis

    key = f"agentrt:notified:{notification_type}:{today}"
    r = aioredis.from_url(redis_url, decode_responses=True)
    try:
        was_set = await r.set(key, "1", ex=_DEDUP_TTL, nx=True)
        return was_set is None  # None = key existed = already notified
    finally:
        await r.aclose()


def _format_kpi_alert(anomalies: list[dict[str, Any]]) -> str:
    """Format KPI anomaly alerts for Telegram."""
    lines = ["[!] KPI Anomaly Detected", ""]

    for a in anomalies[:5]:
        sev = a.get("severity", "medium")
        metric = a.get("metric", "unknown")
        value = a.get("value", "?")
        lines.append(f"  [{sev.upper()}] {metric}: {value}")

    return "\n".join(lines)


async def _send_telegram(message: str) -> None:
    """Send a message via Telegram Bot API (best-effort)."""
    import httpx

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.debug("Telegram not configured — skipping notification")
        return

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message},
            )
        logger.info("Telegram notification sent (%d chars)", len(message))
    except Exception:
        logger.debug("Telegram send failed", exc_info=True)


async def notify_kpi_anomaly(
    anomalies: list[dict[str, Any]],
    redis_url: str,
) -> None:
    """Send a Telegram alert for KPI anomalies.

    Deduplicates: max one KPI alert per day.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if await _mark_notified(redis_url, "kpi_anomaly", today):
        logger.info("KPI anomaly alert already sent today — skipping")
        return

    message = _format_kpi_alert(anomalies)
    await _send_telegram(message)


def _format_job_scan_alert(anomalies: list[dict[str, Any]]) -> str:
    """Format job scan anomaly alerts for Telegram."""
    count = len(anomalies)
    lines = [
        f"[!] Job Scan Anomaly — {count} issue{'s' if count != 1 else ''} detected",
        "",
    ]

    for a in anomalies[:10]:
        sev = a.get("severity", "medium").upper()
        title = a.get("title", "unknown")
        lines.append(f"  [{sev}] {title}")

    lines.append("")
    lines.append("Next scan: ~4h")
    return "\n".join(lines)


async def notify_job_scan_anomalies(
    anomalies: list[dict[str, Any]],
    redis_url: str,
) -> None:
    """Send a Telegram alert for job scan anomalies.

    Deduplicates: max one job scan alert per day.
    """
    if not anomalies:
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if await _mark_notified(redis_url, "job_scan_anomaly", today):
        logger.info("Job scan anomaly alert already sent today — skipping")
        return

    message = _format_job_scan_alert(anomalies)
    await _send_telegram(message)
