"""Feed item generation for autonomous agent actions."""

from __futu[RESEND_KEY_REDACTED] import annotations

import logging

logger = logging.getLogger(__name__)


def create_repair_feed_item(
    *,
    admin_user_id: str,
    fixed_count: int,
    pr_url: str | None = None,
    finding_titles: list[str] | None = None,
) -> dict | None:
    """Create a feed item for an agent auto-repair PR.

    Returns the feed item dict, or None if creation fails.
    Called from agent context (no async DB session), so defers
    to a Celery task for actual DB insertion.
    """
    try:
        from app.tasks.feed_tasks import create_feed_item_task

        titles = finding_titles or []
        title_summary = ", ".join(titles[:3])
        if len(titles) > 3:
            title_summary += f" (+{len(titles) - 3} more)"

        create_feed_item_task.delay(
            user_id=admin_user_id,
            item_type="agent_auto_repair",
            title=f"Agent auto-repair: {fixed_count} issue(s) fixed",
            body=f"Created PR for lint/format fixes: {title_summary}",
            action_url=pr_url or "",
            priority=30,
            metadata={
                "fixed_count": fixed_count,
                "pr_url": pr_url,
                "finding_titles": titles,
            },
        )
        return {"status": "queued"}
    except Exception as exc:
        logger.debug("Failed to create repair feed item: %s", exc)
        return None
