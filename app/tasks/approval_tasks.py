"""Celery task for executing Telegram-approved decisions.

Runs in the Celery worker process (not the web worker) to safely
execute subprocess operations (git, pytest, gh) with 120s timeout.
"""

from __futu[RESEND_KEY_REDACTED] import annotations

import logging
import os
from datetime import datetime, timezone

import httpx

from agents.shared.action_handlers import dispatch_action
from agents.shared.decision_registry import find_decision, mark_executed
from agents.shared.execution_engine import ExecutionEngine, ExecutionTier
from agents.shared.learning import filter_resolved_findings
from agents.shared.report import Finding
from app.celery_app import celery_app

logger = logging.getLogger(__name__)

# Circuit breaker: max auto-merges per calendar day
MAX_AUTO_MERGES_PER_DAY = 10


def _send_telegram_reply(chat_id: int, text: str) -> None:
    """Send a reply to Telegram (best-effort)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.info("TELEGRAM_BOT_TOKEN not set — reply not sent: %s", text[:100])
        return
    try:
        with httpx.Client(timeout=10.0) as client:
            client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
    except Exception:
        logger.debug("Failed to send Telegram reply to %s", chat_id)


def _check_circuit_breaker() -> bool:
    """Check if daily auto-merge limit is reached (Redis-backed, persistent).

    Returns True if circuit breaker is TRIPPED (limit reached).
    """
    try:
        import redis

        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            return False  # No Redis = no circuit breaker = allow
        r = redis.from_url(redis_url)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"tg_approval_count:{today}"
        count = r.incr(key)
        if count == 1:
            r.expire(key, 86400)  # TTL 24h
        return count > MAX_AUTO_MERGES_PER_DAY
    except Exception as exc:
        logger.warning("Circuit breaker check failed: %s", exc)
        return False  # Fail open


def _publish_event(
    finding_id: str, tier: str, action: str, detail: str, pr_url: str = ""
) -> None:
    """Publish execution event to cto:events Redis Stream."""
    try:
        import redis

        from agents.shared.event_stream import STREAM_KEY

        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            return
        r = redis.from_url(redis_url)
        r.xadd(
            STREAM_KEY,
            {
                "team": "telegram",
                "agent": "founder_approval",
                "finding_id": finding_id,
                "tier": tier,
                "action": action,
                "detail": detail,
                "pr_url": pr_url,
                "source": "telegram_approval",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as exc:
        logger.warning("Failed to publish event: %s", exc)


def _execute_approval(chat_id: int, decision_number: int, reject: bool) -> None:
    """Core logic — separated from Celery decorator for testability."""
    try:
        # 1. Look up decision
        decision = find_decision(decision_number)
        if decision is None:
            _send_telegram_reply(
                chat_id,
                f"Decision #{decision_number} not found — "
                f"the brief may have been updated.",
            )
            return

        # 2. Already executed?
        if decision.executed_at:
            _send_telegram_reply(
                chat_id,
                f"Already executed at {decision.executed_at}: "
                f"{decision.result_summary}",
            )
            return

        # 3. Rejection
        if reject:
            mark_executed(decision_number, "Rejected by founder")
            _send_telegram_reply(chat_id, f"Decision #{decision_number} rejected.")
            return

        # 4. Kill switch
        try:
            from app.config import settings as _settings

            enabled = _settings.AUTONOMOUS_EXECUTION_ENABLED
        except Exception:
            enabled = (
                os.getenv("AUTONOMOUS_EXECUTION_ENABLED", "false").lower() == "true"
            )
        if not enabled:
            _send_telegram_reply(
                chat_id,
                f"Execution disabled (AUTONOMOUS_EXECUTION_ENABLED=false). "
                f"Decision #{decision_number} logged for next session.",
            )
            return

        # 5. Reconstruct finding
        finding = Finding.from_dict(decision.finding)

        # 6. Re-check resolved registry
        still_relevant = filter_resolved_findings([finding])
        if not still_relevant:
            mark_executed(decision_number, "Already resolved since brief generation")
            _send_telegram_reply(
                chat_id,
                f"Decision #{decision_number} already resolved — no action needed.",
            )
            return

        # 7. Triage
        engine = ExecutionEngine(enabled=True)
        tier = engine.triage(finding)

        # 8. Circuit breaker — downgrade AUTO_DO if limit reached
        if tier == ExecutionTier.AUTO_DO and _check_circuit_breaker():
            logger.warning("Circuit breaker tripped — downgrading AUTO_DO to AUTO_PR")
            tier = ExecutionTier.AUTO_PR

        # 9. Execute
        result = dispatch_action(finding, tier)

        # 10. Publish to cto:events
        _publish_event(
            finding_id=finding.id,
            tier=tier.value,
            action="executed" if result.success else "failed",
            detail=result.summary,
            pr_url=result.pr_url or "",
        )

        # 11. Record result
        summary = result.summary
        if result.pr_url:
            summary += f" {result.pr_url}"
        mark_executed(decision_number, summary)

        # 12. Reply
        if result.success:
            _send_telegram_reply(chat_id, f"Done. {summary}")
        else:
            _send_telegram_reply(chat_id, f"Could not execute: {summary}")

    except Exception as exc:
        logger.exception("Error executing approval #%d", decision_number)
        _send_telegram_reply(
            chat_id,
            f"Error executing decision #{decision_number}: "
            f"{str(exc)[:200]}. No changes made.",
        )


@celery_app.task(
    name="app.tasks.approval_tasks.execute_telegram_approval",
    time_limit=180,
    soft_time_limit=150,
)
def execute_telegram_approval(
    chat_id: int, decision_number: int, reject: bool = False
) -> None:
    """Execute a Telegram-approved decision. Sends result back via Bot API."""
    _execute_approval(chat_id, decision_number, reject)
