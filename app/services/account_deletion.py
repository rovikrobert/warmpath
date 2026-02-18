"""Account deletion service — GDPR Article 17 right to erasure.

Provides complete user data purge with credit archival for audit trail.
Called when a user requests account deletion via privacy endpoints.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact, CsvUpload
from app.models.credits import CreditTransaction
from app.models.enrichment import UsageLog
from app.models.job import Application, UserJobPreferences
from app.models.marketplace import (
    IntroFacilitation,
    MarketplaceListing,
    NetworkSharingPreferences,
)
from app.models.match_result import IntroRequest, MatchResult, WarmScore
from app.models.privacy import ArchivedCreditTransaction, ConsentRecord, DataRequest
from app.models.search_request import SearchRequest
from app.models.user import ConnectorProfile, User
from app.services.audit_logger import log_event
from app.services.suppression import add_to_suppression


async def delete_user_data(
    user_id: uuid.UUID,
    db: AsyncSession,
    *,
    requester_email: str = "",
) -> dict:
    """Permanently delete all user data (GDPR Article 17).

    Steps:
    1. Archive credit transactions (24-month audit retention)
    2. Add user email to suppression list (prevents re-import)
    3. Delete all user-owned data across all tables
    4. Anonymize the user record (keep row for FK integrity)
    5. Log the deletion to audit trail

    Returns summary of deleted records.
    """
    counts: dict[str, int] = {}

    # 1. Archive credit transactions before deleting
    credit_result = await db.execute(
        select(CreditTransaction).where(CreditTransaction.user_id == user_id)
    )
    credits = list(credit_result.scalars())
    counts["credits_archived"] = len(credits)

    purge_after = datetime.now(timezone.utc) + timedelta(days=730)  # 24 months
    for txn in credits:
        db.add(
            ArchivedCreditTransaction(
                original_user_id=user_id,
                original_transaction_id=txn.id,
                amount=txn.amount,
                type=txn.type,
                reason=txn.reason,
                original_created_at=txn.created_at,
                purge_after=purge_after,
            )
        )

    # 2. Add to suppression list (prevents re-import of this person's data)
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user and user.email:
        await add_to_suppression(
            email=user.email,
            first_name="",
            last_name="",
            company="",
            reason="account_deleted",
            db=db,
        )

    # 3. Delete user-owned data (order matters for FK constraints)
    # Marketplace listings first (depends on contacts)
    r = await db.execute(
        delete(MarketplaceListing).where(
            MarketplaceListing.network_holder_id == user_id
        )
    )
    counts["marketplace_listings"] = r.rowcount

    # Intro facilitations (as job seeker or network holder)
    r = await db.execute(
        delete(IntroFacilitation).where(
            (IntroFacilitation.job_seeker_id == user_id)
            | (IntroFacilitation.network_holder_id == user_id)
        )
    )
    counts["intro_facilitations"] = r.rowcount

    # Warm scores
    r = await db.execute(delete(WarmScore).where(WarmScore.user_id == user_id))
    counts["warm_scores"] = r.rowcount

    # Match results (via search requests)
    search_ids_result = await db.execute(
        select(SearchRequest.id).where(SearchRequest.user_id == user_id)
    )
    search_ids = [row[0] for row in search_ids_result]
    if search_ids:
        r = await db.execute(
            delete(MatchResult).where(MatchResult.search_request_id.in_(search_ids))
        )
        counts["match_results"] = r.rowcount

    # Search requests
    r = await db.execute(delete(SearchRequest).where(SearchRequest.user_id == user_id))
    counts["search_requests"] = r.rowcount

    # Applications
    r = await db.execute(delete(Application).where(Application.user_id == user_id))
    counts["applications"] = r.rowcount

    # Job preferences
    r = await db.execute(
        delete(UserJobPreferences).where(UserJobPreferences.user_id == user_id)
    )
    counts["job_preferences"] = r.rowcount

    # Contacts and CSV uploads
    r = await db.execute(delete(Contact).where(Contact.user_id == user_id))
    counts["contacts"] = r.rowcount

    r = await db.execute(delete(CsvUpload).where(CsvUpload.user_id == user_id))
    counts["csv_uploads"] = r.rowcount

    # Credit transactions (already archived above)
    r = await db.execute(
        delete(CreditTransaction).where(CreditTransaction.user_id == user_id)
    )
    counts["credit_transactions"] = r.rowcount

    # Network sharing preferences
    r = await db.execute(
        delete(NetworkSharingPreferences).where(
            NetworkSharingPreferences.user_id == user_id
        )
    )
    counts["sharing_preferences"] = r.rowcount

    # Connector profile
    r = await db.execute(
        delete(ConnectorProfile).where(ConnectorProfile.user_id == user_id)
    )
    counts["connector_profiles"] = r.rowcount

    # Consent records
    r = await db.execute(delete(ConsentRecord).where(ConsentRecord.user_id == user_id))
    counts["consent_records"] = r.rowcount

    # Usage logs
    r = await db.execute(delete(UsageLog).where(UsageLog.user_id == user_id))
    counts["usage_logs"] = r.rowcount

    # Data requests — keep but anonymize (for compliance audit)
    await db.execute(
        update(DataRequest)
        .where(DataRequest.user_id == user_id)
        .values(user_id=None, requester_email="[deleted]")
    )

    # 4. Anonymize user record (soft delete — keep for FK integrity in audit_logs)
    if user:
        user.email = f"deleted-{user_id}@warmpath.local"
        user.full_name = "[Deleted User]"
        user.password_hash = None
        user.deleted_at = datetime.now(timezone.utc)
        user.token_version = (user.token_version or 0) + 1  # Invalidate all sessions

    # 5. Audit log (append-only, preserved)
    await log_event(
        db,
        "account_deleted",
        user_id=user_id,
        metadata={"records_deleted": counts},
    )

    await db.flush()
    return counts
