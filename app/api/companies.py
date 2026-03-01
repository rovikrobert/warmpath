import math

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.company import Company
from app.models.contact import Contact
from app.models.registry import CompanyBoard
from app.models.user import User
from app.schemas.contact import PaginationMeta
from app.services.board_registry import (
    BOARD_REGISTRY,
    lookup_careers_url,
    lookup_or_discover_boards,
)
from app.services.company_normalizer import normalize_company_name
from app.services.job_fetcher import JobFetcher
from app.services.job_recommendations import set_cached_jobs
from app.utils.security import get_current_user


class CompanyDiscoverRequest(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=200)


router = APIRouter()
_fetcher = JobFetcher()


@router.post("/discover")
async def discover_company(
    body: CompanyDiscoverRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Probe a company on-demand: discover ATS boards, fetch jobs via the full
    fallback chain (ATS -> career page -> JobSpy -> Adzuna), cache results."""
    name = body.company_name.strip()
    key = name.lower()

    # 1. Probe ATS boards (persists if found)
    boards, was_discovered = await lookup_or_discover_boards(name, db)

    # 2. Fetch jobs via full chain
    jobs = await _fetcher.fetch_jobs_for_company(name, boards)

    # 3. Cache for recommendations
    if jobs:
        await set_cached_jobs(key, jobs, db)
        await db.commit()

    # 4. Determine discovery status
    if boards and was_discovered:
        discovery_status = "discovered"
    elif boards:
        discovery_status = "known"
    elif jobs:
        discovery_status = "scraped"
    else:
        discovery_status = "no_listings"

    # Determine the primary source of jobs
    board_source = None
    if boards:
        board_source = next(iter(boards.keys()), None)
    elif jobs:
        board_source = jobs[0].get("source", "jobspy")

    careers_url = lookup_careers_url(name) or _guess_careers_url(name)

    # Normalize sample jobs to consistent shape
    sample_jobs = [_normalize_job(j) for j in jobs[:5]]

    return {
        "data": {
            "company_name": name,
            "discovery_status": discovery_status,
            "board_source": board_source,
            "jobs_found": len(jobs),
            "sample_jobs": sample_jobs,
            "careers_url": careers_url,
        }
    }


@router.get("/suggest")
async def suggest_companies(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(8, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Prefix-match companies from the user's contacts, board registry, and
    discovered boards. Returns merged, deduped results prioritized by source."""
    q_lower = q.strip().lower()
    seen: set[str] = set()
    results: list[dict] = []

    # 1. User's own contacts (highest priority)
    contact_query = (
        select(
            Company.name,
            func.count(Contact.id).label("contact_count"),
        )
        .join(Contact, Contact.company_id == Company.id)
        .where(
            Contact.user_id == current_user.id,
            Contact.deleted_at.is_(None),
            Company.name.ilike(f"{q}%"),
        )
        .group_by(Company.name)
        .order_by(func.count(Contact.id).desc())
        .limit(limit)
    )
    rows = (await db.execute(contact_query)).all()
    for row in rows:
        key = row.name.lower()
        if key not in seen:
            seen.add(key)
            results.append(
                {
                    "name": row.name,
                    "contact_count": row.contact_count,
                    "source": "own_contacts",
                }
            )

    # Also check unlinked contacts (company_id IS NULL).
    # NOTE: current_company is EncryptedString — SQL-level ILIKE operates on
    # ciphertext and never matches.  Load rows and filter in Python.
    unlinked_query = select(Contact.current_company).where(
        Contact.user_id == current_user.id,
        Contact.deleted_at.is_(None),
        Contact.company_id.is_(None),
        Contact.current_company.isnot(None),
    )
    unlinked_rows = (await db.execute(unlinked_query)).all()
    company_counts: dict[str, int] = {}
    for (company_name,) in unlinked_rows:
        if not company_name or not company_name.strip():
            continue
        normalized = normalize_company_name(company_name) or company_name
        if normalized.lower().startswith(q_lower):
            key = normalized.lower()
            company_counts[key] = company_counts.get(key, 0) + 1
    for key, count in sorted(company_counts.items(), key=lambda x: x[1], reverse=True):
        if key not in seen:
            seen.add(key)
            results.append(
                {
                    "name": key.title() if key.islower() else key,
                    "contact_count": count,
                    "source": "own_contacts",
                }
            )

    # 2. Board registry (static + discovered)
    if len(results) < limit:
        for reg_key in BOARD_REGISTRY:
            if reg_key.startswith(q_lower) and reg_key not in seen:
                seen.add(reg_key)
                display = BOARD_REGISTRY[reg_key].get("display_name", reg_key.title())
                results.append(
                    {"name": display, "contact_count": 0, "source": "registry"}
                )
                if len(results) >= limit:
                    break

    # 3. Discovered boards from DB
    if len(results) < limit:
        board_query = (
            select(CompanyBoard.display_name, CompanyBoard.company_key)
            .where(
                CompanyBoard.is_active.is_(True),
                CompanyBoard.company_key.ilike(f"{q_lower}%"),
            )
            .limit(limit)
        )
        board_rows = (await db.execute(board_query)).all()
        for row in board_rows:
            key = row.company_key.lower()
            if key not in seen:
                seen.add(key)
                results.append(
                    {
                        "name": row.display_name or row.company_key.title(),
                        "contact_count": 0,
                        "source": "discovered",
                    }
                )

    return {"data": results[:limit]}


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
    # NOTE: current_company is EncryptedString — SQL-level ILIKE operates on
    # ciphertext and never matches.  We must load rows and filter in Python
    # where the ORM decrypts the value transparently.
    if search:
        unlinked_query = select(Contact.current_company).where(
            Contact.user_id == current_user.id,
            Contact.deleted_at.is_(None),
            Contact.company_id.is_(None),
            Contact.current_company.isnot(None),
        )
        unlinked_result = await db.execute(unlinked_query)

        # Decrypt in Python, normalize, and filter by search term.
        # Normalization maps "Google LLC" → "Google" so unlinked counts
        # merge correctly with FK-based Stage 1 results.
        search_lower = search.lower()
        unlinked_counts: dict[str, int] = {}
        for (raw_name,) in unlinked_result:
            if not raw_name or not raw_name.strip():
                continue
            normalized = normalize_company_name(raw_name) or raw_name
            if search_lower in normalized.lower():
                key = normalized.lower()
                unlinked_counts[key] = unlinked_counts.get(key, 0) + 1

        # Merge: add unlinked counts to existing entries or create new ones
        existing_names = {d["name"].lower() for d in data}
        for norm_lower, count in unlinked_counts.items():
            # Check if this company already appeared in the FK results
            merged = False
            for d in data:
                if d["name"].lower() == norm_lower:
                    d["contact_count"] += count
                    merged = True
                    break
            if not merged and norm_lower not in existing_names:
                existing_names.add(norm_lower)
                # Title-case the normalized name for display
                display = (
                    norm_lower.upper() if len(norm_lower) <= 4 else norm_lower.title()
                )
                data.append(
                    {
                        "id": None,
                        "name": display,
                        "domain": None,
                        "industry": None,
                        "company_size": None,
                        "headquarters": None,
                        "contact_count": count,
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


def _guess_careers_url(company_name: str) -> str:
    """Best-effort guess of a company's careers page URL."""
    slug = company_name.strip().lower().replace(" ", "")
    return f"https://{slug}.com/careers"


def _normalize_job(job: dict) -> dict:
    """Normalize a job dict from any source to a consistent shape."""
    return {
        "title": job.get("title", ""),
        "url": job.get("url", ""),
        "department": job.get("department"),
        "location": job.get("location"),
        "source": job.get("source", ""),
        "is_remote": job.get("is_remote", False),
    }
