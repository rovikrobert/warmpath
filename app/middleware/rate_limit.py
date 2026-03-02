"""Rate limiting based on usage_logs table.

Checks action counts for the current day before allowing the request.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enrichment import UsageLog
from app.utils.exceptions import RateLimitError


async def check_rate_limit(
    user_id: uuid.UUID,
    action: str,
    max_per_day: int,
    db: AsyncSession,
    *,
    is_admin: bool = False,
) -> tuple[bool, int]:
    """Check if the user has exceeded the daily rate limit for an action.

    Returns (allowed, current_count).  Admins always pass.
    """
    if is_admin:
        return True, 0
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    result = await db.execute(
        select(func.count())
        .select_from(UsageLog)
        .where(
            UsageLog.user_id == user_id,
            UsageLog.action == action,
            or_(
                UsageLog.resource_type.is_(None),
                UsageLog.resource_type != "metered",
            ),
            UsageLog.created_at >= today_start,
        )
    )
    count = result.scalar() or 0
    return count < max_per_day, count


async def enforce_daily_limit(
    user_id: uuid.UUID,
    action: str,
    max_per_day: int,
    db: AsyncSession,
    *,
    is_admin: bool = False,
    error_message: str | None = None,
) -> int:
    """Raise RateLimitError if user exceeded daily cap for action.

    Returns current count when allowed.
    """
    allowed, count = await check_rate_limit(
        user_id,
        action,
        max_per_day,
        db,
        is_admin=is_admin,
    )
    if not allowed:
        raise RateLimitError(
            error_message or f"Daily limit reached for {action} ({max_per_day}/day)"
        )
    return count
