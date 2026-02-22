"""Job openings API — scan company career pages and list stored openings."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.company import Company
from app.models.job import JobOpening, UserJobPreferences
from app.models.search_request import SearchRequest
from app.models.user import User
from app.services.board_registry import lookup_boards, lookup_or_discover_boards
from app.services.job_fetcher import JobFetcher
from app.utils.security import get_current_user

router = APIRouter()
fetcher = JobFetcher()


async def _upsert_openings(
    db: AsyncSession,
    jobs: list[dict],
    company_id: uuid.UUID | None = None,
) -> list[JobOpening]:
    """Insert or update job openings. Dedup by (source, source_job_id)."""
    results: list[JobOpening] = []

    # Batch-load existing openings for dedup (avoids N+1)
    dedup_pairs = [
        (jd["source"], jd.get("source_job_id"))
        for jd in jobs
        if jd.get("source_job_id")
    ]
    existing_map: dict[tuple[str, str], JobOpening] = {}
    if dedup_pairs:
        conditions = [
            and_(JobOpening.source == src, JobOpening.source_job_id == sid)
            for src, sid in dedup_pairs
        ]
        er = await db.execute(select(JobOpening).where(or_(*conditions)))
        existing_map = {(jo.source, jo.source_job_id): jo for jo in er.scalars()}

    for job_data in jobs:
        source = job_data["source"]
        source_job_id = job_data.get("source_job_id")

        existing = existing_map.get((source, source_job_id)) if source_job_id else None

        if existing:
            existing.title = job_data["title"]
            existing.department = job_data.get("department")
            existing.location = job_data.get("location")
            existing.url = job_data["url"]
            existing.is_remote = job_data.get("is_remote", False)
            existing.posted_at = job_data.get("posted_at")
            existing.is_active = True
            existing.raw_data = job_data.get("raw_data")
            existing.updated_at = datetime.now(timezone.utc)
            results.append(existing)
        else:
            opening = JobOpening(
                company_id=company_id,
                title=job_data["title"],
                department=job_data.get("department"),
                location=job_data.get("location"),
                url=job_data["url"],
                source=source,
                source_job_id=source_job_id,
                is_remote=job_data.get("is_remote", False),
                posted_at=job_data.get("posted_at"),
                is_active=True,
                raw_data=job_data.get("raw_data"),
            )
            db.add(opening)
            results.append(opening)

    return results


@router.get("/scan/{company_name}")
async def scan_company_jobs(
    company_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fetch live jobs for a company from Greenhouse/Lever, with auto-discovery and career page fallback."""
    boards, was_discovered = await lookup_or_discover_boards(company_name, db)

    # Let fetch_jobs_for_company run the full fallback chain
    # (ATS boards → career page → JobSpy → Adzuna) even if no board is known.
    jobs = await fetcher.fetch_jobs_for_company(company_name, boards)

    # Try to link to existing company record
    result = await db.execute(
        select(Company).where(Company.name.ilike(f"%{company_name}%"))
    )
    company = result.scalar_one_or_none()
    company_id = company.id if company else None

    openings = await _upsert_openings(db, jobs, company_id=company_id)
    await db.commit()

    # Determine how jobs were found
    if boards and was_discovered:
        discovery_status = "discovered"
    elif boards:
        discovery_status = "known"
    elif openings:
        discovery_status = "scraped"
    else:
        discovery_status = "no_listings"

    return {
        "data": [
            {
                "id": str(o.id),
                "title": o.title,
                "department": o.department,
                "location": o.location,
                "url": o.url,
                "source": o.source,
                "is_remote": o.is_remote,
                "posted_at": o.posted_at.isoformat() if o.posted_at else None,
            }
            for o in openings
        ],
        "meta": {
            "company": company_name,
            "openings_count": len(openings),
            "discovery_status": discovery_status,
        },
    }


@router.get("/openings")
async def list_openings(
    company_id: uuid.UUID | None = Query(None),
    role: str | None = Query(None, description="Filter by role keyword"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List stored job openings, optionally filtered by company and role."""
    query = select(JobOpening).where(JobOpening.is_active.is_(True))

    if company_id is not None:
        query = query.where(JobOpening.company_id == company_id)
    if role is not None:
        query = query.where(JobOpening.title.ilike(f"%{role}%"))

    query = query.order_by(JobOpening.discovered_at.desc())
    offset = (page - 1) * per_page
    result = await db.execute(query.offset(offset).limit(per_page))
    openings = result.scalars().all()

    return {
        "data": [
            {
                "id": str(o.id),
                "title": o.title,
                "department": o.department,
                "location": o.location,
                "url": o.url,
                "source": o.source,
                "is_remote": o.is_remote,
                "posted_at": o.posted_at.isoformat() if o.posted_at else None,
                "company_id": str(o.company_id) if o.company_id else None,
            }
            for o in openings
        ],
        "meta": {"page": page, "per_page": per_page, "shown": len(openings)},
    }


@router.post("/scan-targets")
async def scan_target_companies(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Scan all target companies from user's searches for relevant openings."""
    # Get user's job preferences for role matching
    prefs_result = await db.execute(
        select(UserJobPreferences).where(UserJobPreferences.user_id == current_user.id)
    )
    prefs = prefs_result.scalar_one_or_none()
    target_role = prefs.target_role if prefs else None
    target_seniority = prefs.target_seniority if prefs else None

    # Collect target companies from all user searches
    searches_result = await db.execute(
        select(SearchRequest).where(
            SearchRequest.user_id == current_user.id,
            SearchRequest.deleted_at.is_(None),
        )
    )
    searches = searches_result.scalars().all()

    target_companies: set[str] = set()
    for s in searches:
        companies = s.target_companies
        if isinstance(companies, str):
            import json

            companies = json.loads(companies)
        if companies:
            target_companies.update(c.strip().lower() for c in companies)

    companies_scanned = 0
    total_openings = 0
    relevant_openings = 0

    # Pre-load company records for all target companies (avoids N+1)
    company_id_cache: dict[str, uuid.UUID | None] = {}
    if target_companies:
        cr = await db.execute(
            select(Company).where(
                or_(*[Company.name.ilike(f"%{cn}%") for cn in target_companies])
            )
        )
        for c in cr.scalars():
            company_id_cache[c.name.lower()] = c.id

    for company_name in target_companies:
        boards = lookup_boards(company_name)
        # Let fetch_jobs_for_company run the full fallback chain for every target
        jobs = await fetcher.fetch_jobs_for_company(company_name, boards)
        companies_scanned += 1
        total_openings += len(jobs)

        # Link to existing company record (from pre-loaded cache)
        company_id = company_id_cache.get(company_name)

        # Upsert all openings
        await _upsert_openings(db, jobs, company_id=company_id)

        # Count role-relevant ones
        if target_role:
            matched = await fetcher.match_jobs_to_role(
                jobs, target_role, target_seniority
            )
            relevant_openings += len(matched)

    await db.commit()

    return {
        "data": {
            "companies_scanned": companies_scanned,
            "openings_found": total_openings,
            "relevant_to_role": relevant_openings,
        },
        "meta": {},
    }
