"""Credit service — earn/spend/balance logic for the marketplace.

Credit economy:
- Earn: CSV upload (100), successful intro facilitation (50), welcome bonus (50)
- Spend: Cross-network search (5), request intro facilitation (20)
- Credits are non-transferable, expire after 12 months.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credits import CreditTransaction


async def get_balance(user_id: uuid.UUID, db: AsyncSession) -> int:
    """Get user's current credit balance (sum of non-expired transactions).

    Excludes:
    - Transactions whose expires_at has passed (expired by date)
    - type='expired' ledger offsets (created by expire_stale_credits sweep)
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
            CreditTransaction.user_id == user_id,
            CreditTransaction.type != "expired",
            (CreditTransaction.expires_at.is_(None))
            | (CreditTransaction.expires_at > now),
        )
    )
    return int(result.scalar())


async def get_credit_summary(user_id: uuid.UUID, db: AsyncSession) -> dict:
    """Get detailed credit summary: balance, lifetime totals, expiring soon (single query)."""
    now = datetime.now(timezone.utc)
    thirty_days = now + timedelta(days=30)

    balance_cond = (
        (CreditTransaction.type != "expired")
        & (
            (CreditTransaction.expires_at.is_(None))
            | (CreditTransaction.expires_at > now)
        )
    )
    earned_cond = CreditTransaction.amount > 0
    spent_cond = CreditTransaction.amount < 0
    expiring_cond = (
        (CreditTransaction.amount > 0)
        & (CreditTransaction.expires_at.isnot(None))
        & (CreditTransaction.expires_at > now)
        & (CreditTransaction.expires_at <= thirty_days)
    )

    q = select(
        func.coalesce(func.sum(case((balance_cond, CreditTransaction.amount), else_=0)), 0).label("balance"),
        func.coalesce(func.sum(case((earned_cond, CreditTransaction.amount), else_=0)), 0).label("earned"),
        func.coalesce(func.sum(case((spent_cond, CreditTransaction.amount), else_=0)), 0).label("spent"),
        func.coalesce(func.sum(case((expiring_cond, CreditTransaction.amount), else_=0)), 0).label("expiring"),
    ).where(CreditTransaction.user_id == user_id)

    row = (await db.execute(q)).one()
    return {
        "balance": int(row.balance),
        "earned_total": int(row.earned),
        "spent_total": abs(int(row.spent)),
        "expiring_soon": int(row.expiring),
    }


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
        raise ValueError(f"Insufficient credits: have {balance}, need {amount}")
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


async def expire_stale_credits(db: AsyncSession) -> int:
    """Expire credits past their expiry date.

    Finds all users with positive-amount transactions where expires_at < now.
    For each user, calculates the expired amount (sum of expired positive txns)
    and creates an offsetting negative 'expired' transaction — but only up to
    the user's current balance (never expire into negative).

    Returns count of users whose credits were expired.
    """
    now = datetime.now(timezone.utc)

    # Find users with expired positive transactions
    expired_query = (
        select(
            CreditTransaction.user_id,
            func.sum(CreditTransaction.amount).label("expired_amount"),
        )
        .where(
            CreditTransaction.amount > 0,
            CreditTransaction.type == "earned",
            CreditTransaction.expires_at.isnot(None),
            CreditTransaction.expires_at <= now,
        )
        .group_by(CreditTransaction.user_id)
    )
    expired_rows = (await db.execute(expired_query)).all()

    # Batch-load already-expired sums and effective balances (avoids N+1)
    user_ids = [uid for uid, _ in expired_rows]

    already_expired_map: dict = {}
    effective_balance_map: dict = {}
    if user_ids:
        ae_result = await db.execute(
            select(
                CreditTransaction.user_id,
                func.coalesce(func.sum(CreditTransaction.amount), 0),
            )
            .where(
                CreditTransaction.user_id.in_(user_ids),
                CreditTransaction.type == "expired",
            )
            .group_by(CreditTransaction.user_id)
        )
        already_expired_map = {row[0]: abs(int(row[1])) for row in ae_result.all()}

        eb_result = await db.execute(
            select(
                CreditTransaction.user_id,
                func.coalesce(func.sum(CreditTransaction.amount), 0),
            )
            .where(
                CreditTransaction.user_id.in_(user_ids),
                (CreditTransaction.expires_at.is_(None))
                | (CreditTransaction.expires_at > now),
            )
            .group_by(CreditTransaction.user_id)
        )
        effective_balance_map = {row[0]: int(row[1]) for row in eb_result.all()}

    count = 0
    for user_id, expired_amount in expired_rows:
        expired_amount = int(expired_amount)
        if expired_amount <= 0:
            continue

        already_expired = already_expired_map.get(user_id, 0)
        to_expire = expired_amount - already_expired
        if to_expire <= 0:
            continue

        effective_balance = effective_balance_map.get(user_id, 0)
        to_expire = min(to_expire, effective_balance)
        if to_expire <= 0:
            continue

        txn = CreditTransaction(
            user_id=user_id,
            amount=-to_expire,
            type="expired",
            reason="credits_expired",
        )
        db.add(txn)
        count += 1

    await db.flush()
    return count
