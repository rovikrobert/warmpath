"""Credit service — earn/spend/balance logic for the marketplace.

Credit economy:
- Earn: CSV upload (100), successful intro facilitation (50), welcome bonus (50)
- Spend: Cross-network search (5), request intro facilitation (20)
- Credits are non-transferable, expire after 12 months.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credits import CreditTransaction


async def get_balance(user_id: uuid.UUID, db: AsyncSession) -> int:
    """Get user's current credit balance (sum of non-expired transactions).

    Excludes:
    - Transactions whose expires_at has passed (expired by date)
    - type='expired' ledger offsets (created by expi[RESEND_KEY_REDACTED] sweep)
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
    """Get detailed credit summary: balance, lifetime totals, expiring soon."""
    now = datetime.now(timezone.utc)
    thirty_days = now + timedelta(days=30)

    # Current balance (non-expired)
    balance = await get_balance(user_id, db)

    # Lifetime earned (all positive transactions)
    earned_result = await db.execute(
        select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
            CreditTransaction.user_id == user_id,
            CreditTransaction.amount > 0,
        )
    )
    earned_total = int(earned_result.scalar())

    # Lifetime spent (sum of negative transactions, returned as positive)
    spent_result = await db.execute(
        select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
            CreditTransaction.user_id == user_id,
            CreditTransaction.amount < 0,
        )
    )
    spent_total = abs(int(spent_result.scalar()))

    # Credits expiring in next 30 days (positive transactions with near expiry)
    expiring_result = await db.execute(
        select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
            CreditTransaction.user_id == user_id,
            CreditTransaction.amount > 0,
            CreditTransaction.expires_at.isnot(None),
            CreditTransaction.expires_at > now,
            CreditTransaction.expires_at <= thirty_days,
        )
    )
    expiring_soon = int(expiring_result.scalar())

    return {
        "balance": balance,
        "earned_total": earned_total,
        "spent_total": spent_total,
        "expiring_soon": expiring_soon,
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


async def expi[RESEND_KEY_REDACTED](db: AsyncSession) -> int:
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

    # Also need to find if we've already created expiry offsets for these
    # We'll check by looking for existing 'expired' transactions
    count = 0
    for user_id, expired_amount in expired_rows:
        expired_amount = int(expired_amount)
        if expired_amount <= 0:
            continue

        # Check how much we've already expired for this user
        already_expired_result = await db.execute(
            select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                CreditTransaction.user_id == user_id,
                CreditTransaction.type == "expired",
            )
        )
        already_expired = abs(int(already_expired_result.scalar()))

        # Net new amount to expire
        to_expire = expired_amount - already_expired
        if to_expire <= 0:
            continue

        # Don't expire more than effective balance (includes expiry offsets)
        eff_result = await db.execute(
            select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                CreditTransaction.user_id == user_id,
                (CreditTransaction.expires_at.is_(None))
                | (CreditTransaction.expires_at > now),
            )
        )
        effective_balance = int(eff_result.scalar())
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
