"""Credit service — earn/spend/balance logic for the marketplace.

Credit economy:
- Earn: CSV upload (100), successful intro facilitation (50), keep data fresh (10/quarter)
- Spend: Cross-network search (5), request intro facilitation (20)
- Credits are non-transferable, expire after 12 months.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credits import CreditTransaction


async def get_balance(user_id: uuid.UUID, db: AsyncSession) -> int:
    """Get user's current credit balance (sum of non-expired transactions)."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
            CreditTransaction.user_id == user_id,
            # Exclude expired credits
            (CreditTransaction.expires_at.is_(None))
            | (CreditTransaction.expires_at > now),
        )
    )
    return int(result.scalar())


async def earn_credits(
    user_id: uuid.UUID,
    amount: int,
    reason: str,
    db: AsyncSession,
    reference_id: uuid.UUID | None = None,
) -> CreditTransaction:
    """Award credits to a user. Credits expire after 12 months."""
    txn = CreditTransaction(
        user_id=user_id,
        amount=amount,
        type="earned",
        reason=reason,
        reference_id=reference_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
    )
    db.add(txn)
    await db.flush()
    return txn


async def spend_credits(
    user_id: uuid.UUID,
    amount: int,
    reason: str,
    db: AsyncSession,
    reference_id: uuid.UUID | None = None,
) -> CreditTransaction:
    """Deduct credits from a user. Raises ValueError if insufficient balance."""
    balance = await get_balance(user_id, db)
    if balance < amount:
        raise ValueError(
            f"Insufficient credits: have {balance}, need {amount}"
        )
    txn = CreditTransaction(
        user_id=user_id,
        amount=-amount,
        type="spent",
        reason=reason,
        reference_id=reference_id,
    )
    db.add(txn)
    await db.flush()
    return txn


async def refund_credits(
    user_id: uuid.UUID,
    amount: int,
    reason: str,
    db: AsyncSession,
    reference_id: uuid.UUID | None = None,
) -> CreditTransaction:
    """Refund credits to a user (partial or full)."""
    txn = CreditTransaction(
        user_id=user_id,
        amount=amount,
        type="earned",
        reason=reason,
        reference_id=reference_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
    )
    db.add(txn)
    await db.flush()
    return txn
