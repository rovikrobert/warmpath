"""Company board registry API — manage ATS board mappings at runtime."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services import registry_service
from app.utils.security import get_current_user

router = APIRouter()


def _require_admin(current_user: User) -> None:
    """Raise 403 if user is not an admin."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )


class CreateBoardRequest(BaseModel):
    company_key: str = Field(..., max_length=255, description="Normalized lowercase key")
    display_name: str = Field(..., max_length=500)
    board_source: str = Field(..., max_length=50, description="greenhouse, lever, ashby, or career_page")
    board_slug: str | None = Field(None, max_length=255)
    career_page_url: str | None = Field(None, max_length=1000)
    region: str | None = Field(None, max_length=100)


class UpdateBoardRequest(BaseModel):
    display_name: str | None = Field(None, max_length=500)
    board_source: str | None = Field(None, max_length=50)
    board_slug: str | None = Field(None, max_length=255)
    career_page_url: str | None = Field(None, max_length=1000)
    region: str | None = Field(None, max_length=100)
    is_active: bool | None = None


def _board_to_dict(board) -> dict:
    return {
        "id": str(board.id),
        "company_key": board.company_key,
        "display_name": board.display_name,
        "board_source": board.board_source,
        "board_slug": board.board_slug,
        "career_page_url": board.career_page_url,
        "region": board.region,
        "is_active": board.is_active,
        "verified_at": board.verified_at.isoformat() if board.verified_at else None,
        "created_at": board.created_at.isoformat() if board.created_at else None,
        "updated_at": board.updated_at.isoformat() if board.updated_at else None,
    }


@router.get("")
async def list_registry(
    region: str | None = Query(None),
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List all registered company boards."""
    boards, total = await registry_service.list_boards(
        db, region=region, is_active=is_active, page=page, per_page=per_page
    )
    return {
        "data": [_board_to_dict(b) for b in boards],
        "meta": {"page": page, "per_page": per_page, "total": total},
    }


@router.get("/{company_key}")
async def get_registry_entry(
    company_key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a single registry entry by company key."""
    board = await registry_service.get_board_by_key(db, company_key)
    if board is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No registry entry for '{company_key}'",
        )
    return {"data": _board_to_dict(board)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_registry_entry(
    body: CreateBoardRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Add a new company to the board registry. Admin only."""
    _require_admin(current_user)
    try:
        board = await registry_service.create_board(
            db,
            company_key=body.company_key,
            display_name=body.display_name,
            board_source=body.board_source,
            board_slug=body.board_slug,
            career_page_url=body.career_page_url,
            region=body.region,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(e)
        ) from e
    return {"data": _board_to_dict(board)}


@router.patch("/{board_id}")
async def update_registry_entry(
    board_id: str,
    body: UpdateBoardRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update an existing registry entry. Admin only."""
    _require_admin(current_user)
    board = await registry_service.get_board_by_id(db, board_id)
    if board is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registry entry not found",
        )
    updates = body.model_dump(exclude_none=True)
    try:
        board = await registry_service.update_board(db, board, **updates)
        await db.commit()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e
    return {"data": _board_to_dict(board)}


@router.post("/{board_id}/verify")
async def verify_registry_entry(
    board_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Probe the ATS endpoint to verify a board is still live."""
    board = await registry_service.get_board_by_id(db, board_id)
    if board is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registry entry not found",
        )
    success = await registry_service.verify_board(db, board)
    await db.commit()
    return {
        "data": {
            "verified": success,
            "board": _board_to_dict(board),
        }
    }


class BatchDiscoverRequest(BaseModel):
    companies: list[str] = Field(
        ..., min_length=1, max_length=200,
        description="List of company names to discover ATS boards for",
    )


@router.post("/discover")
async def batch_discover_registry(
    body: BatchDiscoverRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Batch-discover ATS boards for a list of company names. Admin only.

    Probes Greenhouse/Lever/Ashby for each company, persists results to DB.
    Skips companies that already exist in the registry.
    """
    _require_admin(current_user)
    results = await registry_service.batch_discover(db, body.companies)
    await db.commit()
    discovered = sum(1 for r in results.values() if r["status"] == "discovered")
    existed = sum(1 for r in results.values() if r["status"] == "exists")
    not_found = sum(1 for r in results.values() if r["status"] == "not_found")
    return {
        "data": {
            "results": results,
            "summary": {
                "discovered": discovered,
                "already_existed": existed,
                "not_found": not_found,
                "total": len(results),
            },
        }
    }


@router.post("/seed")
async def seed_registry(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Seed DB from the static BOARD_REGISTRY dict. Admin only. Idempotent — skips existing entries."""
    _require_admin(current_user)
    count = await registry_service.seed_from_static(db)
    await db.commit()
    return {"data": {"seeded": count}}
