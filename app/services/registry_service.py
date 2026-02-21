"""Service layer for the DB-backed company board registry.

Provides CRUD operations and a lookup chain:
  1. DB table (company_boards)
  2. Static BOARD_REGISTRY dict (fallback)
  3. Auto-discovery via ATS probing
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.registry import CompanyBoard
from app.services.board_registry import (
    BOARD_REGISTRY,
    CAREERS_URLS,
    REGIONS,
    discover_boards,
    get_display_name,
)

logger = logging.getLogger(__name__)

# Reverse lookup for seeding: company_key → region
_KEY_TO_REGION: dict[str, str] = {}
for _region, _keys in REGIONS.items():
    for _key in _keys:
        _KEY_TO_REGION[_key] = _region


async def list_boards(
    db: AsyncSession,
    *,
    region: str | None = None,
    is_active: bool | None = None,
    page: int = 1,
    per_page: int = 50,
) -> tuple[list[CompanyBoard], int]:
    """List registered company boards with optional filters."""
    query = select(CompanyBoard)
    count_query = select(func.count(CompanyBoard.id))

    if region is not None:
        query = query.where(CompanyBoard.region == region)
        count_query = count_query.where(CompanyBoard.region == region)
    if is_active is not None:
        query = query.where(CompanyBoard.is_active == is_active)
        count_query = count_query.where(CompanyBoard.is_active == is_active)

    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(CompanyBoard.company_key)
    offset = (page - 1) * per_page
    result = await db.execute(query.offset(offset).limit(per_page))
    boards = list(result.scalars().all())

    return boards, total


async def get_board_by_key(db: AsyncSession, company_key: str) -> CompanyBoard | None:
    """Get a single board entry by normalized company key."""
    result = await db.execute(
        select(CompanyBoard).where(
            CompanyBoard.company_key == company_key.strip().lower()
        )
    )
    return result.scalar_one_or_none()


async def get_board_by_id(db: AsyncSession, board_id: str) -> CompanyBoard | None:
    """Get a single board entry by UUID."""
    import uuid

    try:
        uid = uuid.UUID(board_id)
    except ValueError:
        return None
    result = await db.execute(select(CompanyBoard).where(CompanyBoard.id == uid))
    return result.scalar_one_or_none()


async def create_board(
    db: AsyncSession,
    *,
    company_key: str,
    display_name: str,
    board_source: str,
    board_slug: str | None = None,
    career_page_url: str | None = None,
    region: str | None = None,
) -> CompanyBoard:
    """Create a new company board entry."""
    key = company_key.strip().lower()

    # Check for duplicate
    existing = await get_board_by_key(db, key)
    if existing is not None:
        raise ValueError(f"Company board '{key}' already exists")

    valid_sources = {"greenhouse", "lever", "ashby", "career_page"}
    if board_source not in valid_sources:
        raise ValueError(f"board_source must be one of {valid_sources}")

    board = CompanyBoard(
        company_key=key,
        display_name=display_name,
        board_source=board_source,
        board_slug=board_slug,
        career_page_url=career_page_url,
        region=region,
        is_active=True,
    )
    db.add(board)
    await db.flush()
    return board


async def update_board(
    db: AsyncSession,
    board: CompanyBoard,
    **kwargs: str | bool | None,
) -> CompanyBoard:
    """Update fields on an existing board entry."""
    valid_sources = {"greenhouse", "lever", "ashby", "career_page"}
    allowed = {
        "display_name",
        "board_source",
        "board_slug",
        "career_page_url",
        "region",
        "is_active",
    }

    for key, value in kwargs.items():
        if key not in allowed:
            continue
        if key == "board_source" and value not in valid_sources:
            raise ValueError(f"board_source must be one of {valid_sources}")
        setattr(board, key, value)

    await db.flush()
    return board


async def verify_board(db: AsyncSession, board: CompanyBoard) -> bool:
    """Probe the ATS endpoint to verify the board is still live.

    Updates verified_at on success, sets is_active=False on failure.
    Returns True if verification succeeded.
    """
    if board.board_source == "career_page":
        # Career pages can't be reliably probed via HEAD
        board.verified_at = datetime.now(timezone.utc)
        await db.flush()
        return True

    if not board.board_slug:
        return False

    from app.services.board_registry import _probe_ats

    result = await _probe_ats(board.board_slug)
    if result is not None:
        board.verified_at = datetime.now(timezone.utc)
        board.is_active = True
        await db.flush()
        return True

    board.is_active = False
    await db.flush()
    return False


async def lookup_boards_db(
    db: AsyncSession, company_name: str
) -> dict[str, str] | None:
    """Look up board identifiers from the DB table.

    Returns a dict like {"greenhouse": "stripe"} or None.
    """
    board = await get_board_by_key(db, company_name)
    if board is None or not board.is_active:
        return None

    if board.board_source == "career_page":
        url = board.career_page_url or ""
        return {"career_page": url}
    elif board.board_slug:
        return {board.board_source: board.board_slug}

    return None


async def batch_discover(
    db: AsyncSession,
    company_names: list[str],
) -> dict[str, dict]:
    """Probe ATS platforms for a list of company names and persist results.

    For each company:
      1. Skip if already in DB
      2. Probe Greenhouse/Lever/Ashby via slug candidates
      3. Persist discovered boards to company_boards table

    Returns a dict of {company_name: {status, board_source, board_slug}} for
    each company processed.
    """
    results: dict[str, dict] = {}

    # Batch-load all existing boards in one query
    unique_keys: list[str] = []
    seen: set[str] = set()
    for name in company_names:
        key = name.strip().lower()
        if key and key not in seen:
            unique_keys.append(key)
            seen.add(key)

    existing_boards: dict[str, CompanyBoard] = {}
    if unique_keys:
        existing_result = await db.execute(
            select(CompanyBoard).where(CompanyBoard.company_key.in_(unique_keys))
        )
        for board in existing_result.scalars().all():
            existing_boards[board.company_key] = board

    for name in company_names:
        key = name.strip().lower()
        if not key:
            continue

        # Skip duplicates within the batch
        if key in results:
            continue

        # Check batch-loaded results
        existing = existing_boards.get(key)
        if existing is not None:
            results[key] = {
                "status": "exists",
                "board_source": existing.board_source,
                "board_slug": existing.board_slug,
            }
            continue

        # Probe ATS platforms
        discovered = await discover_boards(key)

        if discovered is not None:
            source = list(discovered.keys())[0]
            slug = discovered[source]
            board = CompanyBoard(
                company_key=key,
                display_name=get_display_name(key),
                board_source=source,
                board_slug=slug,
                is_active=True,
                verified_at=datetime.now(timezone.utc),
            )
            db.add(board)
            await db.flush()
            results[key] = {
                "status": "discovered",
                "board_source": source,
                "board_slug": slug,
            }
            logger.info(
                "Batch discover: found %s for '%s' (slug: %s)", source, key, slug
            )
        else:
            results[key] = {
                "status": "not_found",
                "board_source": None,
                "board_slug": None,
            }
            logger.info("Batch discover: no ATS found for '%s'", key)

    return results


async def seed_from_static(db: AsyncSession) -> int:
    """Seed the company_boards table from the static BOARD_REGISTRY dict.

    Skips entries that already exist (by company_key). Returns count of
    entries created.
    """
    created = 0

    # Batch-load all existing keys (avoids N+1 per company)
    existing_result = await db.execute(select(CompanyBoard.company_key))
    existing_keys = {r[0] for r in existing_result.all()}

    for company_key, boards_dict in BOARD_REGISTRY.items():
        if company_key in existing_keys:
            continue

        # Extract source and slug from the dict
        source = list(boards_dict.keys())[0]
        slug_or_url = boards_dict[source]

        board = CompanyBoard(
            company_key=company_key,
            display_name=get_display_name(company_key),
            board_source=source,
            board_slug=slug_or_url if source != "career_page" else None,
            career_page_url=(
                slug_or_url
                if source == "career_page"
                else CAREERS_URLS.get(company_key)
            ),
            region=_KEY_TO_REGION.get(company_key),
            is_active=True,
        )
        db.add(board)
        created += 1

    await db.flush()
    logger.info("Seeded %d company board entries from static registry", created)
    return created
