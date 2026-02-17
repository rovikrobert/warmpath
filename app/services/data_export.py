"""Data export service — GDPR/CCPA data portability.

Assembles all personal data for a user into a structured JSON bundle.
Decrypts PII fields so the user receives their data in plaintext.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.contact import Contact, CsvUpload
from app.models.credits import CreditTransaction
from app.models.enrichment import UsageLog
from app.models.job import Application, UserJobPreferences
from app.models.marketplace import (
    IntroFacilitation,
    MarketplaceListing,
    NetworkSharingPreferences,
)
from app.models.search_request import SearchRequest
from app.models.user import ConnectorProfile, User


async def export_user_data(user_id: uuid.UUID, db: AsyncSession) -> dict:
    """Export all personal data for a user (DSAR / data portability).

    Returns a structured JSON-serializable dict with all categories of
    personal data we hold for this user.
    """
    # 1. User profile
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

    user_data = {
        "email": user.email,
        "full_name": user.full_name,
        "user_type": user.user_type,
        "plan_tier": user.plan_tier,
        "email_verified": user.email_verified,
        "created_at": _dt(user.created_at),
        "profile": profile_data,
    }

    # 2. Contacts (decrypted PII)
    contacts_result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.deleted_at.is_(None),
        )
    )
    contacts_data = []
    for c in contacts_result.scalars():
        contacts_data.append({
            "first_name": c.first_name,
            "last_name": c.last_name,
            "email": c.email,
            "current_company": c.current_company,
            "current_title": c.current_title,
            "location": c.location,
            "relationship_type": c.relationship_type,
            "created_at": _dt(c.created_at),
        })

    # 3. Job preferences
    prefs_result = await db.execute(
        select(UserJobPreferences).where(UserJobPreferences.user_id == user_id)
    )
    prefs = prefs_result.scalar_one_or_none()
    prefs_data = None
    if prefs:
        prefs_data = {
            "target_role": prefs.target_role,
            "target_seniority": prefs.target_seniority,
            "target_industries": prefs.target_industries,
            "target_locations": prefs.target_locations,
            "open_to_remote": prefs.open_to_remote,
            "job_search_status": prefs.job_search_status,
        }

    # 4. Applications
    apps_result = await db.execute(
        select(Application).where(
            Application.user_id == user_id,
            Application.deleted_at.is_(None),
        )
    )
    apps_data = []
    for a in apps_result.scalars():
        apps_data.append({
            "company_name": a.company_name,
            "role_title": a.role_title,
            "status": a.status,
            "created_at": _dt(a.created_at),
        })

    # 5. Search history
    searches_result = await db.execute(
        select(SearchRequest).where(
            SearchRequest.user_id == user_id,
            SearchRequest.deleted_at.is_(None),
        )
    )
    searches_data = []
    for s in searches_result.scalars():
        searches_data.append({
            "name": s.name,
            "status": s.status,
            "created_at": _dt(s.created_at),
        })

    # 6. Credit transactions
    credits_result = await db.execute(
        select(CreditTransaction).where(CreditTransaction.user_id == user_id)
    )
    credits_data = []
    for t in credits_result.scalars():
        credits_data.append({
            "amount": t.amount,
            "type": t.type,
            "reason": t.reason,
            "created_at": _dt(t.created_at),
        })

    # 7. CSV uploads metadata
    csv_result = await db.execute(
        select(CsvUpload).where(CsvUpload.user_id == user_id)
    )
    csv_data = []
    for cu in csv_result.scalars():
        csv_data.append({
            "filename": cu.filename,
            "row_count": cu.row_count,
            "status": cu.status,
            "created_at": _dt(cu.created_at),
        })

    # 8. Marketplace listings
    listings_result = await db.execute(
        select(MarketplaceListing).where(
            MarketplaceListing.network_holder_id == user_id,
            MarketplaceListing.deleted_at.is_(None),
        )
    )
    listings_data = []
    for ml in listings_result.scalars():
        listings_data.append({
            "role_level": ml.role_level,
            "department_category": ml.department_category,
            "warm_score_range": ml.warm_score_range,
            "is_available": ml.is_available,
            "created_at": _dt(ml.created_at),
        })

    # 9. Intro facilitations (as seeker and holder)
    intros_seeker_result = await db.execute(
        select(IntroFacilitation).where(IntroFacilitation.job_seeker_id == user_id)
    )
    intros_holder_result = await db.execute(
        select(IntroFacilitation).where(IntroFacilitation.network_holder_id == user_id)
    )
    intros_data = []
    for i in list(intros_seeker_result.scalars()) + list(intros_holder_result.scalars()):
        intros_data.append({
            "status": i.status,
            "role": "seeker" if i.job_seeker_id == user_id else "holder",
            "created_at": _dt(i.created_at),
        })

    # 10. Sharing preferences
    sharing_result = await db.execute(
        select(NetworkSharingPreferences).where(
            NetworkSharingPreferences.user_id == user_id
        )
    )
    sharing = sharing_result.scalar_one_or_none()
    sharing_data = None
    if sharing:
        sharing_data = {
            "opt_in_marketplace": sharing.opt_in_marketplace,
            "category_filters": sharing.category_filters,
            "excluded_contact_ids": [str(c) for c in (sharing.excluded_contact_ids or [])],
        }

    return {
        "export_version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": user_data,
        "contacts": contacts_data,
        "job_preferences": prefs_data,
        "applications": apps_data,
        "search_history": searches_data,
        "credit_transactions": credits_data,
        "csv_uploads": csv_data,
        "marketplace_listings": listings_data,
        "intro_facilitations": intros_data,
        "sharing_preferences": sharing_data,
    }


def _dt(val: datetime | None) -> str | None:
    """Format datetime as ISO string."""
    if val is None:
        return None
    return val.isoformat()
