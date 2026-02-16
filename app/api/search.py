import logging
import math
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.middleware.rate_limit import check_rate_limit
from app.models.contact import Contact
from app.models.job import UserJobPreferences
from app.models.match_result import MatchResult, WarmScore
from app.models.search_request import SearchRequest
from app.models.user import ConnectorProfile, User
from app.schemas.contact import PaginationMeta
from app.schemas.search import (
    MatchResultResponse,
    SearchRequestCreate,
    SearchRequestResponse,
    SmartSearchCreate,
)
from app.services.ai_matcher import score_contacts
from app.services.ai_matcher import run_search
from app.services.board_registry import lookup_boards
from app.services.job_fetcher import JobFetcher
from app.services.warm_scorer import compute_warm_score
from app.utils.exceptions import RateLimitError
from app.utils.security import get_current_user

logger = logging.getLogger(__name__)

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
        target_role=body.target_role,
        target_seniority=body.target_seniority,
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

    resp = SearchRequestResponse.model_validate(search).model_dump(mode="json")

    # Include smart search results if available
    if search.results_data:
        resp["results_data"] = search.results_data
    if search.error_message:
        resp["error"] = search.error_message

    return {
        "data": resp,
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
    min_score: float = Query(
        40.0,
        ge=0,
        le=100,
        description="Minimum relevance score (alias for min_relevance)",
    ),
    min_relevance: float | None = Query(
        None, ge=0, le=100, description="Minimum relevance score"
    ),
    min_warm: float | None = Query(
        None, ge=0, le=100, description="Minimum warm score"
    ),
    match_type: str | None = Query(
        None, description="Filter by match type: direct, indirect, or weak"
    ),
    company: str | None = Query(
        None, description="Filter by company name (substring match)"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # min_relevance takes precedence over min_score for backwards compat
    effective_min_relevance = min_relevance if min_relevance is not None else min_score

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
            MatchResult.relevance_score >= effective_min_relevance,
        )
    )

    # Apply optional filters
    if match_type is not None:
        base_query = base_query.where(MatchResult.match_type == match_type)
    if company is not None:
        base_query = base_query.where(Contact.current_company.ilike(f"%{company}%"))
    if min_warm is not None:
        base_query = base_query.where(
            func.coalesce(WarmScore.total_score, 0) >= min_warm
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

    # Build response data + collect stats
    data = []
    all_relevance: list[float] = []
    all_warm: list[float] = []
    score_dist = {"90-100": 0, "70-89": 0, "50-69": 0, "20-49": 0}

    # We need all matching rows for stats, not just the current page.
    # Run a lightweight stats query over the full filtered set.
    stats_query = (
        select(
            MatchResult.relevance_score,
            func.coalesce(WarmScore.total_score, 0).label("warm"),
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
            MatchResult.relevance_score >= effective_min_relevance,
        )
    )
    if match_type is not None:
        stats_query = stats_query.where(MatchResult.match_type == match_type)
    if company is not None:
        stats_query = stats_query.where(Contact.current_company.ilike(f"%{company}%"))
    if min_warm is not None:
        stats_query = stats_query.where(
            func.coalesce(WarmScore.total_score, 0) >= min_warm
        )

    stats_rows = (await db.execute(stats_query)).all()
    for rel, warm_val in stats_rows:
        r = float(rel)
        w = float(warm_val)
        all_relevance.append(r)
        all_warm.append(w)
        if r >= 90:
            score_dist["90-100"] += 1
        elif r >= 70:
            score_dist["70-89"] += 1
        elif r >= 50:
            score_dist["50-69"] += 1
        else:
            score_dist["20-49"] += 1

    for match, contact_name, contact_title, contact_company, warm_score_val in rows:
        warm = float(warm_score_val) if warm_score_val is not None else None
        relevance = float(match.relevance_score)
        combined = relevance * 0.5 + (warm or 0) * 0.5

        # Extract cultural context fields
        ctx = match.cultural_context or {}

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
                referral_likelihood=ctx.get("referral_likelihood"),
                cultural_context=ctx,
                recommended_channel=ctx.get("recommended_channel"),
                message_sequence=ctx.get("message_sequence"),
                contact_name=contact_name,
                contact_title=contact_title,
                contact_company=contact_company,
                created_at=match.created_at,
            ).model_dump(mode="json")
        )

    return {
        "data": data,
        "meta": {
            **PaginationMeta(
                page=page,
                per_page=per_page,
                total=total,
                total_pages=max(1, math.ceil(total / per_page)),
            ).model_dump(),
            "total_matches": total,
            "shown": len(data),
            "avg_relevance": round(sum(all_relevance) / len(all_relevance), 1)
            if all_relevance
            else 0,
            "avg_warm": round(sum(all_warm) / len(all_warm), 1) if all_warm else 0,
            "score_distribution": score_dist,
        },
    }


# ---------------------------------------------------------------------------
# Smart Search — combines network analysis + job board scanning
# ---------------------------------------------------------------------------


@router.post("/smart", status_code=status.HTTP_201_CREATED)
async def smart_search(
    body: SmartSearchCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """One-shot search: scan job boards + find referral paths for each company.

    Creates a SearchRequest with status 'running', executes the search,
    then updates to 'completed' with results or 'failed' with error.
    The client can poll GET /search/{id} for progress.
    """
    # Load user's job preferences
    pref_result = await db.execute(
        select(UserJobPreferences).where(UserJobPreferences.user_id == current_user.id)
    )
    prefs = pref_result.scalar_one_or_none()

    target_role = prefs.target_role if prefs else None
    target_seniority = prefs.target_seniority if prefs else None

    if not target_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Set job preferences first (PUT /preferences/job with target_role)",
        )

    # Create SearchRequest for history tracking
    search_req = SearchRequest(
        user_id=current_user.id,
        name=f"Smart search: {', '.join(body.company_names[:3])}",
        target_companies=body.company_names,
        target_role=target_role,
        target_seniority=target_seniority,
        status="running",
    )
    db.add(search_req)
    await db.flush()
    search_id = search_req.id

    try:
        results = await _run_smart_search(
            search_req=search_req,
            company_names=body.company_names,
            target_role=target_role,
            target_seniority=target_seniority,
            user=current_user,
            db=db,
        )

        search_req.status = "completed"
        search_req.results_data = results
        search_req.last_run_at = datetime.now(timezone.utc)
        await db.commit()

        return {
            "data": {
                "id": str(search_id),
                "status": "completed",
                **results,
            },
            "meta": {},
        }

    except Exception as exc:
        logger.exception("Smart search failed for %s", body.company_names)
        search_req.status = "failed"
        search_req.error_message = str(exc)
        await db.commit()

        return {
            "data": {
                "id": str(search_id),
                "status": "failed",
                "error": str(exc),
            },
            "meta": {},
        }


async def _run_smart_search(
    search_req: SearchRequest,
    company_names: list[str],
    target_role: str,
    target_seniority: str | None,
    user: User,
    db: AsyncSession,
) -> dict:
    """Execute the smart search pipeline for each company."""
    fetcher = JobFetcher()

    # Load user's contacts with companies eagerly
    contacts_result = await db.execute(
        select(Contact)
        .options(selectinload(Contact.company))
        .where(
            Contact.user_id == user.id,
            Contact.deleted_at.is_(None),
        )
    )
    all_contacts = list(contacts_result.scalars().all())

    # Load connector profile for warm scoring
    profile_result = await db.execute(
        select(ConnectorProfile).where(ConnectorProfile.user_id == user.id)
    )
    profile = profile_result.scalar_one_or_none()

    companies_results: list[dict] = []

    for company_name in company_names:
        company_data = await _process_company(
            company_name=company_name,
            target_role=target_role,
            target_seniority=target_seniority,
            all_contacts=all_contacts,
            search_req=search_req,
            profile=profile,
            user=user,
            fetcher=fetcher,
            db=db,
        )
        companies_results.append(company_data)

    # Sort: companies with BOTH openings AND referral paths first,
    # then openings only, then referral paths only, then neither
    def _sort_key(c: dict) -> tuple:
        has_both = c["has_openings"] and c["has_referral_paths"]
        has_openings_only = c["has_openings"] and not c["has_referral_paths"]
        has_paths_only = c["has_referral_paths"] and not c["has_openings"]
        return (
            not has_both,
            not has_openings_only,
            not has_paths_only,
        )

    companies_results.sort(key=_sort_key)

    summary = {
        "companies_searched": len(company_names),
        "with_openings": sum(1 for c in companies_results if c["has_openings"]),
        "with_referral_paths": sum(
            1 for c in companies_results if c["has_referral_paths"]
        ),
        "total_openings": sum(len(c["active_openings"]) for c in companies_results),
        "total_referral_paths": sum(
            len(c["referral_paths"]) for c in companies_results
        ),
    }

    return {"companies": companies_results, "summary": summary}


async def _process_company(
    company_name: str,
    target_role: str,
    target_seniority: str | None,
    all_contacts: list[Contact],
    search_req: SearchRequest,
    profile: ConnectorProfile | None,
    user: User,
    fetcher: JobFetcher,
    db: AsyncSession,
) -> dict:
    """Process a single company: fetch openings + find referral paths."""
    active_openings: list[dict] = []
    referral_paths: list[dict] = []

    # Step 1: Look up board registry and fetch job openings
    boards = lookup_boards(company_name)
    if boards:
        raw_jobs = await fetcher.fetch_jobs_for_company(company_name, boards)
        matched_jobs = await fetcher.match_jobs_to_role(
            raw_jobs, target_role, target_seniority
        )
        for job in matched_jobs:
            active_openings.append(
                {
                    "title": job.get("title", ""),
                    "url": job.get("url", ""),
                    "department": job.get("department"),
                    "location": job.get("location"),
                    "is_remote": job.get("is_remote", False),
                    "relevance": job.get("role_relevance", 0),
                    "source": job.get("source", ""),
                }
            )

    # Step 2: Find user's contacts who work at this company
    company_lower = company_name.lower()
    company_contacts = [
        c
        for c in all_contacts
        if c.current_company and company_lower in c.current_company.lower()
    ]

    # Step 3: Run AI matcher on those contacts
    if company_contacts:
        matches = score_contacts(search_req, company_contacts, profile, user.full_name)
        # score_contacts might be a coroutine
        if hasattr(matches, "__await__"):
            matches = await matches

        for match in matches:
            if match.relevance_score < 20:
                continue

            # Find the contact object for enrichment
            contact = next(
                (c for c in company_contacts if c.id == match.contact_id), None
            )
            if contact is None:
                continue

            # Compute warm score
            warm_result = compute_warm_score(contact, profile, target_role)

            referral_paths.append(
                {
                    "contact": {
                        "id": str(contact.id),
                        "name": contact.full_name,
                        "title": contact.current_title,
                        "company": contact.current_company,
                        "warm_score": warm_result.total_score,
                        "referral_likelihood": match.referral_likelihood,
                    },
                    "match_type": match.match_type,
                    "relevance_score": match.relevance_score,
                    "cultural_context": match.cultural_context,
                    "recommended_channel": match.recommended_channel,
                    "source": "own_network",
                }
            )

        # Sort referral paths by relevance score descending
        referral_paths.sort(key=lambda p: p["relevance_score"], reverse=True)

    return {
        "name": company_name,
        "active_openings": active_openings,
        "referral_paths": referral_paths,
        "has_openings": len(active_openings) > 0,
        "has_referral_paths": len(referral_paths) > 0,
        "source": "own_network",
    }
