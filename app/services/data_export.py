"""Data export service — GDPR/CCPA data portability.

Assembles all personal data for a user into a structured JSON bundle.
Decrypts PII fields so the user receives their data in plaintext.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.utils.performance import timed
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.contact import Contact, CsvUpload
from app.models.credits import CreditTransaction
from app.models.job import Application, UserJobPreferences
from app.models.marketplace import (
    IntroFacilitation,
    MarketplaceListing,
    NetworkSharingPreferences,
)
from app.models.search_request import SearchRequest
from app.models.user import User


# ---------------------------------------------------------------------------
# Per-table export helpers
# ---------------------------------------------------------------------------


async def _export_user_profile(user_id: uuid.UUID, db: AsyncSession) -> dict:
    result = await db.execute(
        select(User)
        .options(selectinload(User.connector_profile))
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError("User not found")

    profile_data = None
    if user.connector_profile:
        p = user.connector_profile
        profile_data = {
            "headline": p.headline,
            "current_company": p.current_company,
            "current_title": p.current_title,
            "industry": p.industry,
            "location": p.location,
            "linkedin_url": p.linkedin_url,
            "bio_summary": p.bio_summary,
            "work_history": p.work_history,
        }

    return {
        "email": user.email,
        "full_name": user.full_name,
        "intent": user.intent,
        "plan_tier": user.plan_tier,
        "email_verified": user.email_verified,
        "created_at": _dt(user.created_at),
        "profile": profile_data,
    }


async def _export_contacts(user_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.deleted_at.is_(None),
        )
    )
    return [
        {
            "first_name": c.first_name,
            "last_name": c.last_name,
            "email": c.email,
            "current_company": c.current_company,
            "current_title": c.current_title,
            "location": c.location,
            "relationship_type": c.relationship_type,
            "created_at": _dt(c.created_at),
        }
        for c in result.scalars()
    ]


async def _export_job_preferences(
    user_id: uuid.UUID, db: AsyncSession
) -> dict | None:
    result = await db.execute(
        select(UserJobPreferences).where(UserJobPreferences.user_id == user_id)
    )
    prefs = result.scalar_one_or_none()
    if not prefs:
        return None
    return {
        "target_role": prefs.target_role,
        "target_seniority": prefs.target_seniority,
        "target_industries": prefs.target_industries,
        "target_locations": prefs.target_locations,
        "open_to_remote": prefs.open_to_remote,
        "job_search_status": prefs.job_search_status,
    }


async def _export_applications(user_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(Application).where(
            Application.user_id == user_id,
            Application.deleted_at.is_(None),
        )
    )
    return [
        {
            "company_name": a.company_name,
            "role_title": a.role_title,
            "status": a.status,
            "created_at": _dt(a.created_at),
        }
        for a in result.scalars()
    ]


async def _export_search_history(user_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(SearchRequest).where(
            SearchRequest.user_id == user_id,
            SearchRequest.deleted_at.is_(None),
        )
    )
    return [
        {
            "name": s.name,
            "status": s.status,
            "created_at": _dt(s.created_at),
        }
        for s in result.scalars()
    ]


async def _export_credit_transactions(
    user_id: uuid.UUID, db: AsyncSession
) -> list[dict]:
    result = await db.execute(
        select(CreditTransaction).where(CreditTransaction.user_id == user_id)
    )
    return [
        {
            "amount": t.amount,
            "type": t.type,
            "reason": t.reason,
            "created_at": _dt(t.created_at),
        }
        for t in result.scalars()
    ]


async def _export_csv_uploads(user_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    result = await db.execute(select(CsvUpload).where(CsvUpload.user_id == user_id))
    return [
        {
            "filename": cu.filename,
            "row_count": cu.row_count,
            "status": cu.status,
            "created_at": _dt(cu.created_at),
        }
        for cu in result.scalars()
    ]


async def _export_marketplace_listings(
    user_id: uuid.UUID, db: AsyncSession
) -> list[dict]:
    result = await db.execute(
        select(MarketplaceListing).where(
            MarketplaceListing.network_holder_id == user_id,
            MarketplaceListing.deleted_at.is_(None),
        )
    )
    return [
        {
            "role_level": ml.role_level,
            "department_category": ml.department_category,
            "warm_sco[RESEND_KEY_REDACTED]": ml.warm_sco[RESEND_KEY_REDACTED],
            "is_available": ml.is_available,
            "created_at": _dt(ml.created_at),
        }
        for ml in result.scalars()
    ]


async def _export_intro_facilitations(
    user_id: uuid.UUID, db: AsyncSession
) -> list[dict]:
    seeker_result = await db.execute(
        select(IntroFacilitation).where(IntroFacilitation.job_seeker_id == user_id)
    )
    holder_result = await db.execute(
        select(IntroFacilitation).where(IntroFacilitation.network_holder_id == user_id)
    )
    return [
        {
            "status": i.status,
            "role": "seeker" if i.job_seeker_id == user_id else "holder",
            "created_at": _dt(i.created_at),
        }
        for i in list(seeker_result.scalars()) + list(holder_result.scalars())
    ]


async def _export_sharing_preferences(
    user_id: uuid.UUID, db: AsyncSession
) -> dict | None:
    result = await db.execute(
        select(NetworkSharingPreferences).where(
            NetworkSharingPreferences.user_id == user_id
        )
    )
    sharing = result.scalar_one_or_none()
    if not sharing:
        return None
    return {
        "opt_in_marketplace": sharing.opt_in_marketplace,
        "category_filters": sharing.category_filters,
        "excluded_contact_ids": [
            str(c) for c in (sharing.excluded_contact_ids or [])
        ],
    }


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


@timed("data_export")
async def export_user_data(user_id: uuid.UUID, db: AsyncSession) -> dict:
    """Export all personal data for a user (DSAR / data portability).

    Returns a structured JSON-serializable dict with all categories of
    personal data we hold for this user.
    """
    return {
        "export_version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": await _export_user_profile(user_id, db),
        "contacts": await _export_contacts(user_id, db),
        "job_preferences": await _export_job_preferences(user_id, db),
        "applications": await _export_applications(user_id, db),
        "search_history": await _export_search_history(user_id, db),
        "credit_transactions": await _export_credit_transactions(user_id, db),
        "csv_uploads": await _export_csv_uploads(user_id, db),
        "marketplace_listings": await _export_marketplace_listings(user_id, db),
        "intro_facilitations": await _export_intro_facilitations(user_id, db),
        "sharing_preferences": await _export_sharing_preferences(user_id, db),
    }


def _dt(val: datetime | None) -> str | None:
    """Format datetime as ISO string."""
    if val is None:
        return None
    return val.isoformat()
