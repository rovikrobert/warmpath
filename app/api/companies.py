import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.company import Company
from app.models.contact import Contact
from app.models.user import User
from app.schemas.contact import PaginationMeta
from app.utils.security import get_current_user

router = APIRouter()


@router.get("")
async def list_companies(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    search: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List companies that have at least one contact belonging to the current user."""
    # Build query: companies with contact counts scoped to this user
    base_query = (
        select(
            Company.id,
            Company.name,
            Company.domain,
            Company.industry,
            Company.company_size,
            Company.headquarters,
            Company.created_at,
            func.count(Contact.id).label("contact_count"),
        )
        .join(Contact, Contact.company_id == Company.id)
        .where(
            Contact.user_id == current_user.id,
            Contact.deleted_at.is_(None),
        )
        .group_by(Company.id)
    )

    if search:
        pattern = f"%{search}%"
        base_query = base_query.having(Company.name.ilike(pattern))

    # Count total distinct companies
    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Sort by contact count descending (most connected companies first)
    base_query = base_query.order_by(func.count(Contact.id).desc())

    # Paginate
    offset = (page - 1) * per_page
    base_query = base_query.offset(offset).limit(per_page)

    result = await db.execute(base_query)
    rows = result.all()

    data = [
        {
            "id": str(row.id),
            "name": row.name,
            "domain": row.domain,
            "industry": row.industry,
            "company_size": row.company_size,
            "headquarters": row.headquarters,
            "contact_count": row.contact_count,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]

    return {
        "data": data,
        "meta": PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=max(1, math.ceil(total / per_page)),
        ).model_dump(),
    }
