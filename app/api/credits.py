"""Credits API — balance, history, purchase, expiry sweep.

Endpoints:
  GET    /credits/balance   — current balance + summary
  GET    /credits/history   — paginated transaction list
  POST   /credits/purchase  — stub for credit purchase (MVP: direct grant)
  POST   /credits/expire    — trigger expiry sweep
"""

import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.rate_limit import check_rate_limit
from app.models.credits import CreditTransaction
from app.models.user import User
from app.schemas.credits import (
    CreditBalanceResponse,
    CreditHistoryEntry,
    CreditPurchaseRequest,
)
from app.services.audit_logger import log_event
from app.services.credits import earn_credits, expi[RESEND_KEY_REDACTED], get_credit_summary
from app.utils.exceptions import RateLimitError
from app.utils.security import get_current_user, requi[RESEND_KEY_REDACTED]

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /credits/balance
# ---------------------------------------------------------------------------


@router.get("/balance")
async def credit_balance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get current credit balance and summary stats."""
    summary = await get_credit_summary(current_user.id, db)
    return {
        "data": CreditBalanceResponse(**summary).model_dump(),
        "meta": {},
    }


# ---------------------------------------------------------------------------
# GET /credits/history
# ---------------------------------------------------------------------------


@router.get("/history")
async def credit_history(
    type: str | None = Query(
        None, description="Filter by type: earned, spent, expired"
    ),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Paginated credit transaction history."""
    query = select(CreditTransaction).where(
        CreditTransaction.user_id == current_user.id
    )

    if type is not None:
        query = query.where(CreditTransaction.type == type)

    # Count total
    from sqlalchemy import func

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    offset = (page - 1) * per_page
    result = await db.execute(
        query.order_by(CreditTransaction.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    transactions = list(result.scalars())

    data = [
        CreditHistoryEntry.model_validate(t).model_dump(mode="json")
        for t in transactions
    ]

    return {
        "data": data,
        "meta": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": max(1, math.ceil(total / per_page)),
        },
    }


# ---------------------------------------------------------------------------
# POST /credits/purchase
# ---------------------------------------------------------------------------


@router.post("/purchase")
async def purchase_credits(
    body: CreditPurchaseRequest,
    current_user: User = Depends(requi[RESEND_KEY_REDACTED]),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Purchase credits (MVP stub — no payment processing).

    In production, this would integrate with Stripe. For now, it directly
    creates a credit transaction. Useful for testing and admin grants.
    """
    allowed, _count = await check_rate_limit(
        current_user.id,
        "credit_purchase",
        settings.RATE_LIMIT_CREDIT_PURCHASES_PER_DAY,
        db,
        is_admin=current_user.is_admin,
    )
    if not allowed:
        raise RateLimitError(
            f"Credit purchase limit reached ({settings.RATE_LIMIT_CREDIT_PURCHASES_PER_DAY}/day)"
        )

    txn = await earn_credits(
        current_user.id,
        body.amount,
        "purchase",
        db,
        skip_daily_cap=True,
    )
    await log_event(
        db,
        "credit_purchased",
        user_id=current_user.id,
        metadata={"amount": body.amount, "transaction_id": str(txn.id)},
    )
    await db.flush()

    return {
        "data": {
            "transaction_id": str(txn.id),
            "amount": txn.amount,
            "new_balance": (await get_credit_summary(current_user.id, db))["balance"],
        },
        "meta": {},
    }


# ---------------------------------------------------------------------------
# POST /credits/expire
# ---------------------------------------------------------------------------


@router.post("/expire")
async def trigger_expiry(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger credit expiry sweep (admin-only in production).

    For MVP, any authenticated user can trigger it. In production,
    this would be a Celery periodic task or admin-gated endpoint.
    """
    allowed, _count = await check_rate_limit(
        current_user.id,
        "credit_expire",
        settings.RATE_LIMIT_CREDIT_EXPIRE_PER_DAY,
        db,
        is_admin=current_user.is_admin,
    )
    if not allowed:
        raise RateLimitError(
            f"Credit expiry limit reached ({settings.RATE_LIMIT_CREDIT_EXPIRE_PER_DAY}/day)"
        )

    count = await expi[RESEND_KEY_REDACTED](db)
    await db.flush()

    return {
        "data": {"users_expired": count},
        "meta": {},
    }
