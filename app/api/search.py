import math
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.rate_limit import check_rate_limit
from app.models.contact import Contact
from app.models.match_result import MatchResult, WarmScore
from app.models.search_request import SearchRequest
from app.models.user import User
from app.schemas.contact import PaginationMeta
from app.schemas.search import (
    MatchResultResponse,
    SearchRequestCreate,
    SearchRequestResponse,
)
from app.services.ai_matcher import run_search
from app.utils.exceptions import RateLimitError
from app.utils.security import get_current_user

router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_search(
    body: SearchRequestCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    search = SearchRequest(
        user_id=current_user.id,
        name=body.name,
        description=body.description,
        target_titles=body.target_titles,
        target_companies=body.target_companies,
        target_industries=body.target_industries,
        target_locations=body.target_locations,
        target_keywords=body.target_keywords,
        status="active",
    )
    db.add(search)
    await db.commit()
    await db.refresh(search)

    return {
        "data": SearchRequestResponse.model_validate(search).model_dump(mode="json"),
        "meta": {},
    }


@router.get("")
async def list_searches(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    base_query = select(SearchRequest).where(
        SearchRequest.user_id == current_user.id,
        SearchRequest.deleted_at.is_(None),
    )

    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * per_page
    result = await db.execute(
        base_query.order_by(SearchRequest.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    searches = result.scalars().all()

    return {
        "data": [
            SearchRequestResponse.model_validate(s).model_dump(mode="json")
            for s in searches
        ],
        "meta": PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=max(1, math.ceil(total / per_page)),
        ).model_dump(),
    }


@router.get("/{search_id}")
async def get_search(
    search_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(SearchRequest).where(
            SearchRequest.id == search_id,
            SearchRequest.user_id == current_user.id,
            SearchRequest.deleted_at.is_(None),
        )
    )
    search = result.scalar_one_or_none()
    if search is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Search not found",
        )

    return {
        "data": SearchRequestResponse.model_validate(search).model_dump(mode="json"),
        "meta": {},
    }


@router.post("/{search_id}/run")
async def execute_search(
    search_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Rate limit check
    allowed, count = await check_rate_limit(
        current_user.id, "search_run", settings.RATE_LIMIT_SEARCH_RUNS_PER_DAY, db
    )
    if not allowed:
        raise RateLimitError(
            f"Search run limit reached ({settings.RATE_LIMIT_SEARCH_RUNS_PER_DAY}/day)"
        )

    try:
        match_results = await run_search(search_id, current_user.id, db)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    await db.commit()

    return {
        "data": {"matches_found": len(match_results)},
        "meta": {},
    }


@router.get("/{search_id}/results")
async def get_search_results(
    search_id: uuid.UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Verify search exists and belongs to user
    search_result = await db.execute(
        select(SearchRequest).where(
            SearchRequest.id == search_id,
            SearchRequest.user_id == current_user.id,
            SearchRequest.deleted_at.is_(None),
        )
    )
    if search_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Search not found",
        )

    # Query match results joined with contact info and warm scores
    base_query = (
        select(
            MatchResult,
            Contact.full_name,
            Contact.current_title,
            Contact.current_company,
            WarmScore.total_score,
        )
        .join(Contact, MatchResult.contact_id == Contact.id)
        .outerjoin(
            WarmScore,
            (WarmScore.contact_id == MatchResult.contact_id)
            & (WarmScore.user_id == MatchResult.user_id),
        )
        .where(
            MatchResult.search_request_id == search_id,
            MatchResult.user_id == current_user.id,
        )
    )

    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Sort by combined score: relevance * 0.5 + warm_score * 0.5
    # Use COALESCE for null warm scores
    combined_expr = MatchResult.relevance_score * Decimal("0.5") + func.coalesce(
        WarmScore.total_score, 0
    ) * Decimal("0.5")

    offset = (page - 1) * per_page
    result = await db.execute(
        base_query.order_by(combined_expr.desc()).offset(offset).limit(per_page)
    )
    rows = result.all()

    data = []
    for match, contact_name, contact_title, contact_company, warm_sco[RESEND_KEY_REDACTED] in rows:
        warm = float(warm_sco[RESEND_KEY_REDACTED]) if warm_sco[RESEND_KEY_REDACTED] is not None else None
        relevance = float(match.relevance_score)
        combined = relevance * 0.5 + (warm or 0) * 0.5

        data.append(
            MatchResultResponse(
                id=match.id,
                search_request_id=match.search_request_id,
                contact_id=match.contact_id,
                relevance_score=relevance,
                match_reasoning=match.match_reasoning,
                match_type=match.match_type,
                warm_score=warm,
                combined_score=round(combined, 2),
                contact_name=contact_name,
                contact_title=contact_title,
                contact_company=contact_company,
                created_at=match.created_at,
            ).model_dump(mode="json")
        )

    return {
        "data": data,
        "meta": PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=max(1, math.ceil(total / per_page)),
        ).model_dump(),
    }
