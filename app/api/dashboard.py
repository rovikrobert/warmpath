from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.dashboard_insights import get_dashboard_insights
from app.utils.security import get_current_user
from app.utils.tracking import track_action

router = APIRouter()


@router.get("/insights")
async def dashboard_insights(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return personalized dashboard insights (job trends, network analysis, daily tip)."""
    # Track funnel step
    await track_action(db, current_user.id, "dashboard_view")
    await db.commit()

    data = await get_dashboard_insights(current_user.id, db)
    return {"data": data, "meta": {}}
