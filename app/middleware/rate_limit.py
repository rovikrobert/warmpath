"""Rate limiting based on usage_logs table.

Checks action counts for the current day before allowing the request.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enrichment import UsageLog


async def check_rate_limit(
    user_id: uuid.UUID,
    action: str,
    max_per_day: int,
    db: AsyncSession,
) -> tuple[bool, int]:
    """Check if the user has exceeded the daily rate limit for an action.

    Returns (allowed, current_count).
    """
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    result = await db.execute(
        select(func.count())
        .select_from(UsageLog)
        .where(
            UsageLog.user_id == user_id,
            UsageLog.action == action,
            UsageLog.created_at >= today_start,
        )
    )
    count = result.scalar() or 0
    return count < max_per_day, count
