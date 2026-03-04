import logging
import math
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.utils.performance import timed
from sqlalchemy import case, func, select
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
from app.models.company import Company
from app.models.marketplace import (
    ConnectorReputation,
    MarketplaceListing,
)
from app.services.ai_matcher import score_contacts
from app.services.ai_matcher import run_search
from app.utils.privacy_checks import require_not_restricted
from app.services.board_registry import lookup_careers_url, lookup_or_discover_boards
from app.services.credits import check_and_spend
from app.api.jobs import _upsert_openings
from app.services.job_fetcher import JobFetcher
from app.services.job_recommendations import get_recommendations
from app.services.marketplace_indexer import classify_department
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
    """Create a new search request with target filters."""
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
    await db.flush()

    # Track funnel step
    from app.utils.tracking import track_action

    await track_action(
        db,
        current_user.id,
        "search_create",
        resource_id=search.id,
        metadata_={
            "target_companies": body.target_companies[:5]
            if body.target_companies
            else None
        },
    )

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


@router.get("/recommendations")
@timed("job_recommendations")
async def get_recommendations_endpoint(
    exclude: str | None = Query(
        None, description="Comma-separated company names to exclude"
    ),
    limit: int = Query(8, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Recommend companies with live openings matching the user's target role."""
    pref_result = await db.execute(
        select(UserJobPreferences).where(UserJobPreferences.user_id == current_user.id)
    )
    prefs = pref_result.scalar_one_or_none()

    if not prefs or not prefs.target_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Set job preferences first (PUT /preferences/job with target_role)",
        )

    exclude_companies = (
        [c.strip() for c in exclude.split(",") if c.strip()] if exclude else None
    )

    result = await get_recommendations(
        user_id=current_user.id,
        target_role=prefs.target_role,
        target_seniority=prefs.target_seniority,
        target_locations=prefs.target_locations,
        exclude_companies=exclude_companies,
        limit=limit,
        db=db,
        target_industries=prefs.target_industries,
    )

    return {
        "data": result,
        "meta": {},
    }


@router.get("/{search_id}")
async def get_search(
    search_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a search request by ID, including smart search results if available."""
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

    # Flatten smart search results into top-level response for consistent shape
    # with POST /smart (which returns {id, status, companies, summary, scope})
    if search.results_data:
        resp["results_data"] = search.results_data
        for key in ("companies", "summary", "scope"):
            if key in search.results_data:
                resp[key] = search.results_data[key]
    if search.error_message:
        resp["error"] = search.error_message

    return {
        "data": resp,
        "meta": {},
    }


@router.post("/{search_id}/run")
@timed("search_execute")
async def execute_search(
    search_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Run AI matching for a search request. Rate-limited per user per day."""
    require_not_restricted(current_user)

    # Rate limit check
    allowed, count = await check_rate_limit(
        current_user.id,
        "search_run",
        settings.RATE_LIMIT_SEARCH_RUNS_PER_DAY,
        db,
        is_admin=current_user.is_admin,
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


def _build_match_row(row_tuple: tuple) -> dict:
    """Build a single match result response dict from a query row."""
    match, contact_name, contact_title, contact_company, warm_score_val = row_tuple
    warm = float(warm_score_val) if warm_score_val is not None else None
    relevance = float(match.relevance_score)
    combined = relevance * 0.5 + (warm or 0) * 0.5
    ctx = match.cultural_context or {}

    return MatchResultResponse(
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


async def _compute_search_stats(
    all_rows: list | None,
    base_query,
    has_company_filter: bool,
    search_id: uuid.UUID,
    user_id: uuid.UUID,
    effective_min_relevance: float,
    match_type: str | None,
    min_warm: float | None,
    db: AsyncSession,
) -> tuple[float | None, float | None, dict]:
    """Compute avg_relevance, avg_warm, and score_distribution.

    When has_company_filter is True, stats are computed from the in-memory
    all_rows list. Otherwise, a single SQL aggregate query is used.
    """
    score_dist = {"90-100": 0, "70-89": 0, "50-69": 0, "20-49": 0}

    if has_company_filter and all_rows is not None:
        stats_pairs = [
            (float(r[0].relevance_score), float(r[4] or 0)) for r in all_rows
        ]
        all_relevance: list[float] = []
        all_warm: list[float] = []
        for rel, warm_val in stats_pairs:
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
        avg_rel = (
            round(sum(all_relevance) / len(all_relevance), 1) if all_relevance else 0
        )
        avg_warm = round(sum(all_warm) / len(all_warm), 1) if all_warm else 0
        return avg_rel, avg_warm, score_dist

    # SQL aggregate path
    stats_base = (
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
            MatchResult.user_id == user_id,
            MatchResult.relevance_score >= effective_min_relevance,
        )
    )
    if match_type is not None:
        stats_base = stats_base.where(MatchResult.match_type == match_type)
    if min_warm is not None:
        stats_base = stats_base.where(
            func.coalesce(WarmScore.total_score, 0) >= min_warm
        )
    subq = stats_base.subquery()
    agg_query = select(
        func.count().label("cnt"),
        func.avg(subq.c.relevance_score).label("avg_rel"),
        func.avg(subq.c.warm).label("avg_warm"),
        func.sum(case((subq.c.relevance_score >= 90, 1), else_=0)).label("b90"),
        func.sum(
            case(
                (
                    (subq.c.relevance_score >= 70) & (subq.c.relevance_score < 90),
                    1,
                ),
                else_=0,
            )
        ).label("b70"),
        func.sum(
            case(
                (
                    (subq.c.relevance_score >= 50) & (subq.c.relevance_score < 70),
                    1,
                ),
                else_=0,
            )
        ).label("b50"),
        func.sum(
            case(
                (
                    (subq.c.relevance_score >= 20) & (subq.c.relevance_score < 50),
                    1,
                ),
                else_=0,
            )
        ).label("b20"),
    ).select_from(subq)
    agg_row = (await db.execute(agg_query)).one()
    avg_rel = round(float(agg_row.avg_rel or 0), 1)
    avg_warm = round(float(agg_row.avg_warm or 0), 1)
    score_dist = {
        "90-100": int(agg_row.b90 or 0),
        "70-89": int(agg_row.b70 or 0),
        "50-69": int(agg_row.b50 or 0),
        "20-49": int(agg_row.b20 or 0),
    }
    return avg_rel, avg_warm, score_dist


@router.get("/{search_id}/results")
@timed("search_results")
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
    """Get paginated match results for a search, with score and type filters."""
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

    if match_type is not None:
        base_query = base_query.where(MatchResult.match_type == match_type)
    if min_warm is not None:
        base_query = base_query.where(
            func.coalesce(WarmScore.total_score, 0) >= min_warm
        )

    combined_expr = MatchResult.relevance_score * Decimal("0.5") + func.coalesce(
        WarmScore.total_score, 0
    ) * Decimal("0.5")

    SEARCH_COMPANY_CAP = 2000
    all_rows_for_stats = None

    if company is not None:
        result = await db.execute(
            base_query.order_by(combined_expr.desc()).limit(SEARCH_COMPANY_CAP)
        )
        all_rows = result.all()
        company_lower = company.lower()
        all_rows = [r for r in all_rows if company_lower in (r[3] or "").lower()]
        total = len(all_rows)
        offset = (page - 1) * per_page
        rows = all_rows[offset : offset + per_page]
        all_rows_for_stats = all_rows
    else:
        count_query = select(func.count()).select_from(base_query.subquery())
        total = (await db.execute(count_query)).scalar() or 0
        offset = (page - 1) * per_page
        result = await db.execute(
            base_query.order_by(combined_expr.desc()).offset(offset).limit(per_page)
        )
        rows = result.all()

    avg_rel, avg_warm, score_dist = await _compute_search_stats(
        all_rows_for_stats,
        base_query,
        company is not None,
        search_id,
        current_user.id,
        effective_min_relevance,
        match_type,
        min_warm,
        db,
    )

    data = [_build_match_row(row) for row in rows]

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
            "avg_relevance": avg_rel if avg_rel is not None else 0,
            "avg_warm": avg_warm if avg_warm is not None else 0,
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

    scope = body.scope

    # Marketplace scope costs credits
    if scope == "marketplace" and not await check_and_spend(
        current_user.id, 5, "smart_search_marketplace", db
    ):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient credits for marketplace search. "
            "You need 5 credits. Earn credits by uploading your network.",
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
            scope=scope,
            db=db,
        )

        search_req.status = "completed"
        search_req.results_data = results
        search_req.last_run_at = datetime.now(timezone.utc)

        # Funnel instrumentation: search + first_search
        from app.utils.tracking import track_action

        await track_action(
            db,
            current_user.id,
            "search",
            resource_id=search_id,
            metadata_={"scope": scope, "companies": body.company_names[:5]},
        )

        # Track first_search milestone (idempotent via unique constraint)
        from app.models.milestone import UserMilestone

        existing = await db.execute(
            select(UserMilestone.id).where(
                UserMilestone.user_id == current_user.id,
                UserMilestone.milestone_type == "first_search",
            )
        )
        if existing.scalar_one_or_none() is None:
            db.add(
                UserMilestone(
                    user_id=current_user.id,
                    milestone_type="first_search",
                    milestone_value=1,
                    credits_awarded=0,
                )
            )
            await track_action(
                db,
                current_user.id,
                "first_search",
                resource_id=search_id,
                metadata_={"scope": scope, "companies": body.company_names[:5]},
            )

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
    scope: str = "own_network",
) -> dict:
    """Execute the smart search pipeline for each company."""
    fetcher = JobFetcher()

    # Load user's job preferences for location/remote filtering
    pref_result = await db.execute(
        select(UserJobPreferences).where(UserJobPreferences.user_id == user.id)
    )
    prefs = pref_result.scalar_one_or_none()
    target_locations = prefs.target_locations if prefs else None
    open_to_remote = prefs.open_to_remote if prefs else True

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
            target_locations=target_locations,
            open_to_remote=open_to_remote,
            all_contacts=all_contacts,
            search_req=search_req,
            profile=profile,
            user=user,
            fetcher=fetcher,
            db=db,
        )

        # If marketplace scope, also search marketplace listings
        if scope == "marketplace":
            marketplace_paths = await _search_marketplace_for_company(
                company_name=company_name,
                user_id=user.id,
                db=db,
            )
            company_data["referral_paths"].extend(marketplace_paths)
            if marketplace_paths:
                company_data["has_referral_paths"] = True

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

    return {"companies": companies_results, "summary": summary, "scope": scope}


async def _fetch_and_filter_openings(
    company_name: str,
    target_role: str,
    target_seniority: str | None,
    target_locations: list[str] | None,
    open_to_remote: bool,
    fetcher: JobFetcher,
    db: AsyncSession,
) -> tuple[list[dict], int, int, str]:
    """Fetch job board openings, filter, and return (openings, fetched, matched, status)."""
    boards, was_discovered = await lookup_or_discover_boards(company_name, db)

    # Pass first target location as hint for JobSpy/Adzuna fallback
    location_hint = target_locations[0] if target_locations else None

    # Let fetch_jobs_for_company run the full fallback chain
    # (ATS boards → career page → JobSpy → Adzuna) even without a known board.
    raw_jobs = await fetcher.fetch_jobs_for_company(
        company_name, boards, location_hint=location_hint
    )
    total_jobs_fetched = len(raw_jobs)

    if raw_jobs:
        company_result = await db.execute(
            select(Company).where(Company.name.ilike(f"%{company_name}%")).limit(1)
        )
        company_record = company_result.scalar_one_or_none()
        await _upsert_openings(
            db, raw_jobs, company_id=company_record.id if company_record else None
        )

    matched_jobs = await fetcher.match_jobs_to_role(
        raw_jobs, target_role, target_seniority, company_name=company_name
    )
    filtered_jobs = fetcher.filter_and_rank_jobs(
        matched_jobs,
        target_role,
        target_seniority=target_seniority,
        target_locations=target_locations,
        open_to_remote=open_to_remote,
    )
    total_matched = len(filtered_jobs)

    if not boards and raw_jobs:
        # Jobs came from JobSpy/Adzuna fallback (no ATS board)
        scan_status = "scraped" if filtered_jobs else "no_match"
    elif was_discovered:
        scan_status = "discovered" if filtered_jobs else "no_match"
    else:
        scan_status = "matched" if filtered_jobs else "no_match"

    active_openings = [
        {
            "title": job.get("title", ""),
            "url": job.get("url", ""),
            "department": job.get("department"),
            "location": job.get("location"),
            "is_remote": job.get("is_remote", False),
            "relevance": job.get("role_relevance", 0),
            "fit_score": job.get("fit_score", 0),
            "source": job.get("source", ""),
            "in_target_region": job.get("in_target_region", True),
        }
        for job in filtered_jobs[:10]
    ]

    return active_openings, total_jobs_fetched, total_matched, scan_status


async def _build_referral_paths(
    contacts: list[Contact],
    search_req: SearchRequest,
    profile: ConnectorProfile | None,
    user_name: str,
    target_role: str,
) -> list[dict]:
    """Score contacts and build referral path dicts."""
    matches = score_contacts(search_req, contacts, profile, user_name)
    if hasattr(matches, "__await__"):
        matches = await matches

    contact_map = {c.id: c for c in contacts}
    referral_paths: list[dict] = []

    # Classify the target role's department for function matching
    target_dept = classify_department(target_role)

    for match in matches:
        if match.relevance_score < 20:
            continue
        contact = contact_map.get(match.contact_id)
        if contact is None:
            continue

        # Job function matching bonus
        contact_dept = classify_department(contact.current_title)
        if contact_dept == target_dept and target_dept != "other":
            dept_bonus = 20
        elif contact_dept == "hr" or (
            contact.current_title and "recruiter" in contact.current_title.lower()
        ):
            dept_bonus = 10
        else:
            dept_bonus = 0

        adjusted_relevance = min(100, match.relevance_score + dept_bonus)

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
                    "linkedin_url": contact.linkedin_url,
                    "relationship_type": contact.relationship_type,
                },
                "match_type": match.match_type,
                "relevance_score": adjusted_relevance,
                "cultural_context": match.cultural_context,
                "recommended_channel": match.recommended_channel,
                "source": "own_network",
            }
        )

    referral_paths.sort(key=lambda p: p["relevance_score"], reverse=True)
    return referral_paths


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
    target_locations: list[str] | None = None,
    open_to_remote: bool = True,
) -> dict:
    """Process a single company: fetch openings + find referral paths."""
    (
        active_openings,
        total_jobs_fetched,
        total_matched_openings,
        job_scan_status,
    ) = await _fetch_and_filter_openings(
        company_name,
        target_role,
        target_seniority,
        target_locations,
        open_to_remote,
        fetcher,
        db,
    )

    # Find user's contacts who work at this company
    # Match via normalized company name (companies table) since
    # current_company may be encrypted at rest.
    company_lower = company_name.lower()
    company_contacts = [
        c
        for c in all_contacts
        if (c.company and c.company.name and company_lower in c.company.name.lower())
        or (c.current_company and company_lower in c.current_company.lower())
    ]

    # Diagnostic: log matching results for debugging
    logger.info(
        "Company match: query=%r total_contacts=%d matched=%d "
        "sample_companies=[%s] sample_company_fks=[%s]",
        company_name,
        len(all_contacts),
        len(company_contacts),
        ", ".join(
            repr(c.current_company) for c in all_contacts[:10] if c.current_company
        ),
        ", ".join(
            repr(c.company.name) if c.company else "None" for c in all_contacts[:10]
        ),
    )

    referral_paths: list[dict] = []
    if company_contacts:
        referral_paths = await _build_referral_paths(
            company_contacts, search_req, profile, user.full_name, target_role
        )

    return {
        "name": company_name,
        "active_openings": active_openings,
        "referral_paths": referral_paths,
        "has_openings": len(active_openings) > 0,
        "has_referral_paths": len(referral_paths) > 0,
        "job_scan_status": job_scan_status,
        "total_jobs_fetched": total_jobs_fetched,
        "total_matched_openings": total_matched_openings,
        "has_more_openings": total_matched_openings > 10,
        "careers_url": lookup_careers_url(company_name),
        "source": "own_network",
    }


async def _search_marketplace_for_company(
    company_name: str,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[dict]:
    """Search marketplace listings for a company and return anonymized paths."""
    # Find company by name
    company_result = await db.execute(
        select(Company).where(Company.name.ilike(f"%{company_name}%"))
    )
    companies = list(company_result.scalars())
    if not companies:
        return []

    company_ids = [c.id for c in companies]

    # Query active marketplace listings (not the user's own)
    result = await db.execute(
        select(MarketplaceListing).where(
            MarketplaceListing.company_id.in_(company_ids),
            MarketplaceListing.is_available.is_(True),
            MarketplaceListing.deleted_at.is_(None),
            MarketplaceListing.network_holder_id != user_id,
        )
    )
    listings = list(result.scalars())

    # Exclude listings for contacts already in the seeker's vault
    from app.services.marketplace_indexer import (
        build_seeker_hash_set,
        filter_vault_overlap,
    )

    seeker_hashes = await build_seeker_hash_set(user_id, db)
    listings = await filter_vault_overlap(listings, seeker_hashes, db)

    # Load reputations
    holder_ids = {listing.network_holder_id for listing in listings}
    rep_map: dict[uuid.UUID, ConnectorReputation] = {}
    if holder_ids:
        rep_result = await db.execute(
            select(ConnectorReputation).where(
                ConnectorReputation.user_id.in_(holder_ids)
            )
        )
        for rep in rep_result.scalars():
            rep_map[rep.user_id] = rep

    paths: list[dict] = []
    for listing in listings:
        reputation = rep_map.get(listing.network_holder_id)
        rep_dict = None
        if reputation:
            rep_dict = {
                "intros_facilitated": reputation.intros_facilitated,
                "response_rate": reputation.response_rate,
                "avg_rating": reputation.avg_rating,
            }

        paths.append(
            {
                "listing": {
                    "id": str(listing.id),
                    "role_level": listing.role_level,
                    "department_category": listing.department_category,
                    "warm_score_range": listing.warm_score_range,
                    "connection_recency": listing.connection_recency,
                },
                "network_holder_reputation": rep_dict,
                "source": "marketplace",
            }
        )

    return paths
