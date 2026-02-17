"""Usage API — metered usage summary + history.

Endpoints:
  GET /api/v1/usage/me          — monthly summary (metered counts, limits, plan)
  GET /api/v1/usage/me/history  — paginated usage log entries
"""

import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.usage_logger import FREE_TIER_LIMITS
from app.models.enrichment import UsageLog
from app.models.user import User
from app.utils.security import get_current_user

router = APIRouter()


@router.get("/me")
async def usage_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Current user's metered usage for the calendar month."""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Count each metered action this month (single GROUP BY query)
    metered_actions = list(FREE_TIER_LIMITS.keys()) + [
        "job_scan",
        "application_create",
    ]
    result = await db.execute(
        select(UsageLog.action, func.count())
        .where(
            UsageLog.user_id == current_user.id,
            UsageLog.action.in_(metered_actions),
            UsageLog.resource_type == "metered",
            UsageLog.created_at >= month_start,
        )
        .group_by(UsageLog.action)
    )
    counts: dict[str, int] = {action: 0 for action in metered_actions}
    for action, cnt in result.all():
        counts[action] = cnt

    # Total metered calls
    total_result = await db.execute(
        select(func.count())
        .select_from(UsageLog)
        .where(
            UsageLog.user_id == current_user.id,
            UsageLog.resource_type == "metered",
            UsageLog.created_at >= month_start,
        )
    )
    total_metered = total_result.scalar() or 0

    # Build limits dict for current plan
    plan_tier = current_user.plan_tier or "free"
    limits: dict[str, int | str] = {}
    for action in metered_actions:
        if plan_tier == "free" and action in FREE_TIER_LIMITS:
            limits[action] = FREE_TIER_LIMITS[action]
        else:
            limits[action] = "unlimited"

    return {
        "data": {
            "period": month_start.strftime("%Y-%m"),
            "plan_tier": plan_tier,
            "total_metered_calls": total_metered,
            "counts": counts,
            "limits": limits,
        },
        "meta": {},
    }


@router.get("/me/history")
async def usage_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> dict:
    """Paginated list of the current user's usage log entries."""
    # Count total
    total_result = await db.execute(
        select(func.count())
        .select_from(UsageLog)
        .where(UsageLog.user_id == current_user.id)
    )
    total = total_result.scalar() or 0
    total_pages = max(1, math.ceil(total / per_page))

    # Fetch page
    offset = (page - 1) * per_page
    result = await db.execute(
        select(UsageLog)
        .where(UsageLog.user_id == current_user.id)
        .order_by(UsageLog.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    entries = list(result.scalars())

    data = [
        {
            "id": str(entry.id),
            "action": entry.action,
            "resource_type": entry.resource_type,
            "metadata": entry.metadata_,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        }
        for entry in entries
    ]

    return {
        "data": data,
        "meta": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
    }
