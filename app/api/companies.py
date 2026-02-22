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
    """List companies that have at least one contact belonging to the current user.

    Contacts are matched via the ``company_id`` FK **and** via
    ``current_company`` (the raw CSV value).  This ensures contacts imported
    before company normalisation still appear in search previews.
    """
    # --- 1. FK-based query (contacts linked to a Company row) -------------
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

    # --- 2. Unlinked contacts (company_id IS NULL, matched by current_company)
    # These are contacts imported from CSV before company normalisation ran.
    if search:
        unlinked_query = (
            select(
                Contact.current_company,
                func.count(Contact.id).label("contact_count"),
            )
            .where(
                Contact.user_id == current_user.id,
                Contact.deleted_at.is_(None),
                Contact.company_id.is_(None),
                Contact.current_company.ilike(f"%{search}%"),
            )
            .group_by(Contact.current_company)
        )
        unlinked_result = await db.execute(unlinked_query)
        unlinked_rows = unlinked_result.all()

        # Merge: add unlinked counts to existing entries or create new ones
        existing_names = {d["name"].lower() for d in data}
        for row in unlinked_rows:
            name_lower = (row.current_company or "").lower()
            # Check if this company already appeared in the FK results
            merged = False
            for d in data:
                if d["name"].lower() == name_lower:
                    d["contact_count"] += row.contact_count
                    merged = True
                    break
            if not merged and name_lower not in existing_names:
                existing_names.add(name_lower)
                data.append(
                    {
                        "id": None,
                        "name": row.current_company,
                        "domain": None,
                        "industry": None,
                        "company_size": None,
                        "headquarters": None,
                        "contact_count": row.contact_count,
                        "created_at": None,
                    }
                )
                total += 1

        # Re-sort by contact_count after merging
        data.sort(key=lambda d: d["contact_count"], reverse=True)

    return {
        "data": data,
        "meta": PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=max(1, math.ceil(total / per_page)),
        ).model_dump(),
    }
