from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.enrichment import UsageLog
from app.models.user import User
from app.utils.security import get_current_user

router = APIRouter()


@router.get("/health")
def health_check() -> dict:
    return {"data": {"status": "healthy"}, "meta": {}}


@router.get("/api/v1/usage/me")
async def usage_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return current user's usage stats for the current calendar month."""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async def _count(action: str) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(UsageLog)
            .where(
                UsageLog.user_id == current_user.id,
                UsageLog.action == action,
                UsageLog.created_at >= month_start,
            )
        )
        return result.scalar() or 0

    total_result = await db.execute(
        select(func.count())
        .select_from(UsageLog)
        .where(
            UsageLog.user_id == current_user.id,
            UsageLog.created_at >= month_start,
        )
    )
    total_api_calls = total_result.scalar() or 0

    uploads = await _count("csv_upload")
    searches = await _count("search_run")
    intros = await _count("intro_draft")

    return {
        "data": {
            "period": month_start.strftime("%Y-%m"),
            "total_api_calls": total_api_calls,
            "csv_uploads": uploads,
            "searches_run": searches,
            "intros_drafted": intros,
        },
        "meta": {},
    }
