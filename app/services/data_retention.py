"""Data retention service — automated sweeps for privacy compliance.

Implements:
- Usage log anonymization (12-month retention on identifiable data)
- Archived credit transaction purge (24-month retention)
- CSV upload metadata cleanup
- Credit history archival before account deletion
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credits import CreditTransaction
from app.models.enrichment import UsageLog
from app.models.privacy import ArchivedCreditTransaction


async def archive_credit_history(user_id: uuid.UUID, db: AsyncSession) -> int:
    """Copy a user's credit transactions to the archive table before deletion.

    Archived records are retained for 24 months (audit trail), then purged
    by the periodic sweep.

    Returns count of archived transactions.
    """
    result = await db.execute(
        select(CreditTransaction).where(CreditTransaction.user_id == user_id)
    )
    transactions = result.scalars().all()

    purge_after = datetime.now(timezone.utc) + timedelta(days=730)  # 24 months
    count = 0
    for txn in transactions:
        archived = ArchivedCreditTransaction(
            original_user_id=user_id,
            original_transaction_id=txn.id,
            amount=txn.amount,
            type=txn.type,
            reason=txn.reason,
            original_created_at=txn.created_at,
            purge_after=purge_after,
        )
        db.add(archived)
        count += 1

    await db.flush()
    return count


async def purge_old_usage_logs(db: AsyncSession) -> int:
    """Delete usage_logs older than 12 months (identifiable data retention limit)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=365)
    result = await db.execute(
        delete(UsageLog).where(UsageLog.created_at < cutoff)
    )
    await db.flush()
    return result.rowcount


async def purge_expired_archives(db: AsyncSession) -> int:
    """Delete archived credit transactions past their 24-month purge_after date."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        delete(ArchivedCreditTransaction).where(
            ArchivedCreditTransaction.purge_after <= now
        )
    )
    await db.flush()
    return result.rowcount
