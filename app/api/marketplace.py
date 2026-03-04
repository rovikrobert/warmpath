"""Marketplace API — cross-network search, intro facilitation, sharing prefs.

Endpoints:
  POST   /marketplace/search               — anonymized marketplace search
  POST   /marketplace/request-intro         — job seeker requests intro
  GET    /marketplace/my-requests           — job seeker's pending/past requests
  GET    /marketplace/incoming-requests     — network holder's incoming requests
  PATCH  /marketplace/requests/{id}         — approve or decline
  PUT    /marketplace/sharing-preferences   — configure sharing prefs
  GET    /marketplace/sharing-preferences   — get current prefs
  GET    /marketplace/my-listings           — holder's own listings (with PII)
"""

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from app.utils.performance import timed

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.middleware.rate_limit import check_rate_limit
from app.models.company import Company
from app.models.contact import Contact
from app.models.marketplace import (
    ConnectorReputation,
    IntroFacilitation,
    MarketplaceListing,
    NetworkSharingPreferences,
)
from app.models.job import UserJobPreferences
from app.models.user import ConnectorProfile, User
from app.schemas.marketplace import (
    IntroFacilitationActionBody,
    IntroFacilitationHolderResponse,
    IntroFacilitationRequest,
    IntroFacilitationResponse,
    MarketplaceListingDetailResponse,
    MarketplaceSearchBody,
    MarketplaceSearchResult,
    NetworkSharingPreferencesResponse,
    NetworkSharingPrefsUpdate,
)
from app.services.credits import (
    check_and_spend,
    earn_credits,
    refund_credits,
)
from app.services.audit_logger import log_event
from app.services.friendship_service import get_friend_and_fof_ids, get_friend_ids
from app.services.marketplace_indexer import (
    build_seeker_hash_set,
    filter_vault_overlap,
    generate_marketplace_listings,
)
from app.utils.exceptions import RateLimitError
from app.utils.privacy_checks import require_not_restricted
from app.utils.security import get_current_user, require_verified_email

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_listing_summary(
    listing: MarketplaceListing,
    company_name: str,
    reputation: ConnectorReputation | None,
) -> MarketplaceSearchResult:
    """Build an anonymized search result from a listing."""
    rep_dict = None
    if reputation:
        rep_dict = {
            "intros_facilitated": reputation.intros_facilitated,
            "response_rate": reputation.response_rate,
            "avg_rating": reputation.avg_rating,
        }
    return MarketplaceSearchResult(
        listing_id=listing.id,
        company_name=company_name,
        role_level=listing.role_level,
        department_category=listing.department_category,
        warm_score_range=listing.warm_score_range,
        connection_recency=listing.connection_recency,
        network_holder_reputation=rep_dict,
    )


async def _update_connector_reputation(
    user_id: uuid.UUID, action: str, db: AsyncSession
) -> None:
    """Load or create reputation record and increment on approve."""
    rep_result = await db.execute(
        select(ConnectorReputation).where(ConnectorReputation.user_id == user_id)
    )
    reputation = rep_result.scalar_one_or_none()
    if reputation is None:
        reputation = ConnectorReputation(user_id=user_id)
        db.add(reputation)
        await db.flush()

    if action == "approve":
        reputation.intros_facilitated += 1


async def _check_contact_in_vault(
    listing: MarketplaceListing, seeker_user_id: uuid.UUID, db: AsyncSession
) -> bool:
    """Check if the listing's contact already exists in the seeker's vault.

    Uses hash comparison only — never exposes the network holder's contact PII.
    """
    seeker_hashes = await build_seeker_hash_set(seeker_user_id, db)
    remaining = await filter_vault_overlap([listing], seeker_hashes, db)
    return len(remaining) == 0


async def _apply_intro_approve(
    facilitation: IntroFacilitation,
    body: IntroFacilitationActionBody,
    current_user: User,
    now: datetime,
    db: AsyncSession,
) -> Contact | None:
    """Apply approve flow and return contact used for potential fallback response."""
    allowed, current_count = await check_rate_limit(
        current_user.id,
        "intro_approve",
        settings.RATE_LIMIT_INTRO_APPROVALS_PER_DAY,
        db,
        is_admin=current_user.is_admin,
    )
    if not allowed:
        await log_event(
            db,
            "velocity_limit_hit",
            user_id=current_user.id,
            metadata={
                "action": "intro_approve",
                "count": current_count,
                "max_per_day": settings.RATE_LIMIT_INTRO_APPROVALS_PER_DAY,
                "facilitation_id": str(facilitation.id),
            },
        )
        await db.commit()
        raise RateLimitError(
            f"Daily intro approval limit reached ({settings.RATE_LIMIT_INTRO_APPROVALS_PER_DAY}/day)"
        )

    facilitation.status = "approved"
    facilitation.reviewed_at = now
    if body.notes:
        facilitation.network_holder_notes = body.notes

    listing = await db.get(MarketplaceListing, facilitation.marketplace_listing_id)
    contact = await db.get(Contact, listing.contact_id) if listing else None

    if contact and contact.email:
        # Email relay path — send intro via email, defer credits to delivery.
        from app.services.email_engagement import send_intro_relay_email
        from app.services.referral_service import create_referral_code

        nh_ref_code = await create_referral_code(current_user.id, db)
        nh_referral_code = nh_ref_code.code if nh_ref_code else ""

        js_snapshot = facilitation.job_seeker_profile_snapshot or {}
        contact_first = contact.first_name or "there"
        js_name = js_snapshot.get("full_name", "a professional")
        js_role = js_snapshot.get("headline", "")
        js_message = js_snapshot.get("message", "")
        js_blurb = js_snapshot.get("candidate_blurb", "")

        intro_body = f"Hey {contact_first},\n\nI'd like to introduce you to {js_name}"
        if js_role:
            intro_body += f", {js_role}"
        intro_body += "."
        if js_blurb:
            intro_body += f"\n\n{js_blurb}"
        if js_message:
            intro_body += f"\n\n{js_message}"
        intro_body += (
            "\n\nI think you two should connect — happy to share more context."
        )

        review_token = secrets.token_urlsafe(32)
        facilitation.review_token = review_token
        facilitation.review_token_expires_at = now + timedelta(days=90)
        view_intro_url = f"{settings.FRONTEND_URL}/intro/{review_token}"

        message_id = await send_intro_relay_email(
            to_email=contact.email,
            nh_name=current_user.full_name or current_user.email,
            nh_email=current_user.email,
            job_seeker_name=js_name,
            job_seeker_role=js_role,
            target_company=contact.current_company or "",
            intro_message=intro_body,
            nh_referral_code=nh_referral_code,
            db=db,
            facilitation_id=facilitation.id,
            view_intro_url=view_intro_url,
        )

        facilitation.delivery_method = "email_relay"
        facilitation.delivery_status = "sent" if message_id else "failed"
        facilitation.relay_message_id = message_id

    await log_event(
        db,
        "marketplace_approved",
        user_id=current_user.id,
        metadata={"facilitation_id": str(facilitation.id)},
    )
    return contact


async def _apply_intro_decline(
    facilitation: IntroFacilitation,
    body: IntroFacilitationActionBody,
    current_user: User,
    now: datetime,
    db: AsyncSession,
) -> None:
    """Apply decline flow."""
    facilitation.status = "declined"
    facilitation.reviewed_at = now
    if body.notes:
        facilitation.network_holder_notes = body.notes

    # Refund 15 of 20 credits to job seeker (5 credit fee).
    await refund_credits(
        facilitation.job_seeker_id,
        15,
        "intro_declined_refund",
        db,
        reference_id=facilitation.id,
    )
    await log_event(
        db,
        "marketplace_declined",
        user_id=current_user.id,
        metadata={"facilitation_id": str(facilitation.id)},
    )


def _apply_linkedin_fallback_response(
    facilitation: IntroFacilitation,
    contact: Contact | None,
    resp_data: dict,
) -> None:
    """Attach fallback fields when approval uses manual LinkedIn flow."""
    if contact and contact.linkedin_url:
        resp_data["linkedin_url"] = contact.linkedin_url

    js_snapshot = facilitation.job_seeker_profile_snapshot or {}
    js_name = js_snapshot.get("full_name", "a professional")
    js_role = js_snapshot.get("headline", "")
    contact_first = contact.first_name if contact and contact.first_name else "there"

    drafted = f"Hey {contact_first}, I'd like to introduce you to {js_name}"
    if js_role:
        drafted += f", {js_role}"
    drafted += "."
    js_blurb = js_snapshot.get("candidate_blurb", "")
    if js_blurb:
        drafted += f" {js_blurb}"
    resp_data["drafted_message"] = drafted


def _summarize_work_history(work_history: list) -> list[str]:
    """Summarize work history entries as 'Company — Title (Start–End)' strings."""
    lines = []
    for entry in work_history:
        company = entry.get("company", "Unknown")
        title = entry.get("title", "Unknown")
        start = entry.get("start_date", "?")
        end = entry.get("end_date") or "Present"
        lines.append(f"{company} — {title} ({start}–{end})")
    return lines


def _build_seeker_profile_snapshot(
    user: User,
    visibility: str,
    profile: "ConnectorProfile | None" = None,
    prefs: "UserJobPreferences | None" = None,
    request_type: str = "specific_role",
    job_title: str | None = None,
    job_url: str | None = None,
    job_description: str | None = None,
    exploration_context: str | None = None,
    message: str | None = None,
) -> dict:
    """Build a profile snapshot based on visibility level, enriched with profile and prefs."""
    # 1. Visibility-based name/email
    snapshot: dict = {}
    if visibility == "full":
        snapshot["full_name"] = user.full_name
        snapshot["email"] = user.email
    elif visibility == "summary":
        snapshot["full_name"] = user.full_name

    # 2. Enrich with ConnectorProfile fields
    if profile:
        for field in (
            "headline",
            "current_title",
            "current_company",
            "bio_summary",
            "github_url",
            "portfolio_url",
        ):
            value = getattr(profile, field, None)
            if value:
                snapshot[field] = value

        # Work history summarized as list of strings
        if profile.work_history:
            snapshot["work_history_summary"] = _summarize_work_history(
                profile.work_history
            )

    # 3. Enrich with UserJobPreferences
    if prefs:
        for field in ("target_role", "target_seniority", "career_level", "key_skills"):
            value = getattr(prefs, field, None)
            if value:
                snapshot[field] = value
        if prefs.years_experience is not None:
            snapshot["years_experience"] = prefs.years_experience

    # 4. Request type + conditional context fields
    snapshot["request_type"] = request_type
    for key, val in (
        ("job_title", job_title),
        ("job_url", job_url),
        ("job_description", job_description),
        ("exploration_context", exploration_context),
        ("message", message),
    ):
        if val:
            snapshot[key] = val

    return snapshot


# ---------------------------------------------------------------------------
# Vector marketplace search helper
# ---------------------------------------------------------------------------


async def _apply_friend_filter(
    query, friend_filter: str | None, user_id: uuid.UUID, db: AsyncSession
):
    """Apply friend filter to marketplace query. Returns (query, empty_result_or_None)."""
    if not friend_filter or friend_filter == "all":
        return query, None
    if friend_filter == "friends_only":
        fids = await get_friend_ids(user_id, db)
        if not fids:
            return query, {"data": [], "meta": {"total": 0}}
        return query.where(MarketplaceListing.network_holder_id.in_(fids)), None
    if friend_filter == "friends_and_fof":
        fids, fof_ids = await get_friend_and_fof_ids(user_id, db)
        all_ids = fids | fof_ids
        if not all_ids:
            return query, {"data": [], "meta": {"total": 0}}
        return query.where(MarketplaceListing.network_holder_id.in_(all_ids)), None
    return query, None


async def _run_vector_marketplace_search(
    body, current_user_id: uuid.UUID, db: AsyncSession
) -> dict | None:
    """Execute vector marketplace search and return formatted results, or None."""
    listing_ids = await _vector_marketplace_search(
        query=body.query,
        role_levels=body.role_levels,
        departments=body.departments,
    )
    if not listing_ids:
        return None

    stmt = select(MarketplaceListing).where(
        MarketplaceListing.id.in_([uuid.UUID(lid) for lid in listing_ids]),
        MarketplaceListing.is_available.is_(True),
        MarketplaceListing.deleted_at.is_(None),
        MarketplaceListing.network_holder_id != current_user_id,
    )
    if body.role_levels:
        stmt = stmt.where(MarketplaceListing.role_level.in_(body.role_levels))
    if body.departments:
        stmt = stmt.where(MarketplaceListing.department_category.in_(body.departments))
    vresult = await db.execute(stmt)
    vlistings = list(vresult.scalars())
    if not vlistings:
        return None

    # Exclude listings for contacts already in the seeker's vault
    seeker_hashes = await build_seeker_hash_set(current_user_id, db)
    vlistings = await filter_vault_overlap(vlistings, seeker_hashes, db)
    if not vlistings:
        return None

    vcompany_ids = {vl.company_id for vl in vlistings}
    cresult = await db.execute(select(Company).where(Company.id.in_(vcompany_ids)))
    vcompany_map = {c.id: c.name for c in cresult.scalars()}
    vholder_ids = {vl.network_holder_id for vl in vlistings}
    rep_result = await db.execute(
        select(ConnectorReputation).where(ConnectorReputation.user_id.in_(vholder_ids))
    )
    vrep_map = {r.user_id: r for r in rep_result.scalars()}
    results = []
    for listing in vlistings:
        company_name = vcompany_map.get(listing.company_id, "Unknown")
        reputation = vrep_map.get(listing.network_holder_id)
        results.append(
            _build_listing_summary(listing, company_name, reputation).model_dump(
                mode="json"
            )
        )
    return {"data": results, "meta": {"total": len(results)}}


async def _vector_marketplace_search(
    query: str,
    role_levels: list[str] | None = None,
    departments: list[str] | None = None,
    limit: int = 50,
) -> list[str]:
    """Search marketplace listings by semantic similarity. Returns listing IDs."""
    from app.services.embedding_service import generate_embeddings
    from app.services.vector_service import search_similar

    vectors = await generate_embeddings([query])
    if not vectors:
        return []

    results = await search_similar(
        query_vector=vectors[0],
        doc_type="listing",
        limit=limit,
    )

    return [r["payload"]["listing_id"] for r in results]


# ---------------------------------------------------------------------------
# POST /marketplace/search
# ---------------------------------------------------------------------------


@router.post("/search")
@timed("marketplace_search")
async def marketplace_search(
    body: MarketplaceSearchBody,
    current_user: User = Depends(require_verified_email),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Search the anonymized marketplace index. Costs 5 credits."""
    require_not_restricted(current_user)

    # Check and deduct credits
    if not await check_and_spend(current_user.id, 5, "marketplace_search", db):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient credits. You need 5 credits for a marketplace search. "
            "Upgrade your plan or earn credits by uploading your network.",
        )

    # Vector search path (when enabled and query is provided)
    if settings.VECTOR_SEARCH_ENABLED and body.query:
        try:
            vresult = await _run_vector_marketplace_search(body, current_user.id, db)
            if vresult is not None:
                return vresult
        except Exception:
            logger.exception("Vector marketplace search failed, falling back")

    # Look up company IDs by name (single query instead of per-name loop)
    company_map: dict[uuid.UUID, str] = {}
    if body.company_names:
        result = await db.execute(
            select(Company).where(
                or_(*[Company.name.ilike(f"%{n}%") for n in body.company_names])
            )
        )
        for c in result.scalars():
            company_map[c.id] = c.name

    if not company_map:
        return {"data": [], "meta": {"total": 0}}

    # Query active marketplace listings at those companies
    query = select(MarketplaceListing).where(
        MarketplaceListing.company_id.in_(company_map.keys()),
        MarketplaceListing.is_available.is_(True),
        MarketplaceListing.deleted_at.is_(None),
        # Don't show the user's own listings
        MarketplaceListing.network_holder_id != current_user.id,
    )

    if body.role_levels:
        query = query.where(MarketplaceListing.role_level.in_(body.role_levels))
    if body.departments:
        query = query.where(
            MarketplaceListing.department_category.in_(body.departments)
        )

    # Friend filter: restrict to network holders who are friends (or FoF)
    query, early_return = await _apply_friend_filter(
        query, body.friend_filter, current_user.id, db
    )
    if early_return is not None:
        return early_return

    result = await db.execute(query)
    listings = list(result.scalars())

    # Exclude listings for contacts already in the seeker's vault
    seeker_hashes = await build_seeker_hash_set(current_user.id, db)
    listings = await filter_vault_overlap(listings, seeker_hashes, db)

    # Load reputations for unique holder IDs
    holder_ids = {listing.network_holder_id for listing in listings}
    rep_map: dict[uuid.UUID, ConnectorReputation] = {}
    if holder_ids:
        rep_result = await db.execute(
            select(ConnectorReputation).where(
                ConnectorReputation.user_id.in_(holder_ids)
            )
        )
        for rep in rep_result.scalars():
            rep_map[rep.user_id] = rep

    # Build anonymized results grouped by company
    results: list[dict] = []
    for listing in listings:
        company_name = company_map.get(listing.company_id, "Unknown")
        reputation = rep_map.get(listing.network_holder_id)
        results.append(
            _build_listing_summary(listing, company_name, reputation).model_dump(
                mode="json"
            )
        )

    return {"data": results, "meta": {"total": len(results)}}


# ---------------------------------------------------------------------------
# POST /marketplace/request-intro
# ---------------------------------------------------------------------------


@router.post("/request-intro", status_code=status.HTTP_201_CREATED)
async def request_intro(
    body: IntroFacilitationRequest,
    current_user: User = Depends(require_verified_email),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Job seeker requests an intro via a marketplace listing. Costs 20 credits."""
    # Verify listing exists and is available
    listing_result = await db.execute(
        select(MarketplaceListing).where(
            MarketplaceListing.id == body.marketplace_listing_id,
            MarketplaceListing.is_available.is_(True),
            MarketplaceListing.deleted_at.is_(None),
        )
    )
    listing = listing_result.scalar_one_or_none()
    if listing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Marketplace listing not found or unavailable",
        )

    # Can't request intro on your own listing
    if listing.network_holder_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot request intro on your own listing",
        )

    # Check for duplicate pending request
    dup_result = await db.execute(
        select(IntroFacilitation).where(
            IntroFacilitation.job_seeker_id == current_user.id,
            IntroFacilitation.marketplace_listing_id == body.marketplace_listing_id,
            IntroFacilitation.status == "requested",
        )
    )
    if dup_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a pending request for this listing",
        )

    # Duplicate detection: check if the underlying contact is already in
    # the job seeker's vault.
    if await _check_contact_in_vault(listing, current_user.id, db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This person is already in your network "
            "— you can reach out directly from your contacts page.",
        )

    # Check and deduct credits (20 per intro request)
    allowed, current_count = await check_rate_limit(
        current_user.id,
        "intro_request",
        settings.RATE_LIMIT_INTRO_REQUESTS_PER_DAY,
        db,
        is_admin=current_user.is_admin,
    )
    if not allowed:
        await log_event(
            db,
            "velocity_limit_hit",
            user_id=current_user.id,
            metadata={
                "action": "intro_request",
                "count": current_count,
                "max_per_day": settings.RATE_LIMIT_INTRO_REQUESTS_PER_DAY,
            },
        )
        await db.commit()
        raise RateLimitError(
            f"Daily intro request limit reached ({settings.RATE_LIMIT_INTRO_REQUESTS_PER_DAY}/day)"
        )

    if not await check_and_spend(current_user.id, 20, "intro_request", db):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient credits. You need 20 credits to request an intro.",
        )

    # Load seeker's profile and job preferences for snapshot enrichment
    profile_result = await db.execute(
        select(ConnectorProfile).where(ConnectorProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()

    prefs_result = await db.execute(
        select(UserJobPreferences).where(UserJobPreferences.user_id == current_user.id)
    )
    prefs = prefs_result.scalar_one_or_none()

    # Build profile snapshot
    snapshot = _build_seeker_profile_snapshot(
        user=current_user,
        visibility=body.profile_visibility,
        profile=profile,
        prefs=prefs,
        request_type=body.request_type,
        job_title=body.job_title,
        job_url=body.job_url,
        job_description=body.job_description,
        exploration_context=body.exploration_context,
        message=body.message_to_holder,
    )

    # Generate candidate blurb for NH forwarding
    from app.services.candidate_blurb import generate_candidate_blurb

    contact_result = await db.execute(
        select(Contact).where(
            Contact.id == listing.contact_id,
            Contact.user_id == listing.network_holder_id,
        )
    )
    contact_for_blurb = contact_result.scalar_one_or_none()

    if contact_for_blurb:
        blurb = await generate_candidate_blurb(
            profile=profile,
            contact=contact_for_blurb,
            prefs=prefs,
            request_type=body.request_type,
            job_title=body.job_title,
            job_description=body.job_description,
            exploration_context=body.exploration_context,
        )
        snapshot["candidate_blurb"] = blurb

    # Create facilitation record
    facilitation = IntroFacilitation(
        job_seeker_id=current_user.id,
        network_holder_id=listing.network_holder_id,
        marketplace_listing_id=listing.id,
        status="requested",
        job_seeker_profile_snapshot=snapshot,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(facilitation)
    await db.flush()

    # Track funnel step
    from app.utils.tracking import track_action

    await track_action(
        db,
        current_user.id,
        "intro_request",
        resource_id=facilitation.id,
        metadata_={"listing_id": str(listing.id)},
    )

    await db.commit()

    # Send immediate email notification to network holder
    from app.services.email_engagement import send_intro_request_notification

    nh_user_result = await db.execute(
        select(User).where(User.id == listing.network_holder_id)
    )
    nh_user = nh_user_result.scalar_one_or_none()
    if nh_user:
        company_result = await db.execute(
            select(Company.name).where(Company.id == listing.company_id)
        )
        company_name = company_result.scalar_one_or_none() or "a company"
        try:
            await send_intro_request_notification(
                nh_user=nh_user,
                company_name=company_name,
                role_level=listing.role_level or "unknown",
                job_seeker_snapshot=snapshot,
                facilitation_id=facilitation.id,
                db=db,
            )
            await db.commit()
        except Exception:
            logger.warning(
                "Failed to send intro request email for facilitation %s",
                facilitation.id,
                exc_info=True,
            )

    return {
        "data": IntroFacilitationResponse.model_validate(facilitation).model_dump(
            mode="json"
        ),
        "meta": {},
    }


# ---------------------------------------------------------------------------
# GET /marketplace/my-requests
# ---------------------------------------------------------------------------


@router.get("/my-requests")
async def my_requests(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Job seeker's pending and past intro requests."""
    result = await db.execute(
        select(IntroFacilitation)
        .where(IntroFacilitation.job_seeker_id == current_user.id)
        .order_by(IntroFacilitation.created_at.desc())
    )
    facilitations = list(result.scalars())

    # Batch-load listings and companies to avoid N+1
    listing_ids = [f.marketplace_listing_id for f in facilitations]
    listings_map: dict = {}
    companies_map: dict = {}
    if listing_ids:
        lr = await db.execute(
            select(MarketplaceListing).where(MarketplaceListing.id.in_(listing_ids))
        )
        listings_map = {listing.id: listing for listing in lr.scalars()}
        company_ids = {
            listing.company_id
            for listing in listings_map.values()
            if listing.company_id
        }
        if company_ids:
            cr = await db.execute(select(Company).where(Company.id.in_(company_ids)))
            companies_map = {c.id: c for c in cr.scalars()}

    data = []
    for f in facilitations:
        resp = IntroFacilitationResponse.model_validate(f).model_dump(mode="json")
        listing = listings_map.get(f.marketplace_listing_id)
        if listing:
            company = companies_map.get(listing.company_id)
            company_name = company.name if company else "Unknown"
            resp["listing_summary"] = _build_listing_summary(
                listing, company_name, None
            ).model_dump(mode="json")
        data.append(resp)

    return {"data": data, "meta": {"total": len(data)}}


# ---------------------------------------------------------------------------
# GET /marketplace/incoming-requests
# ---------------------------------------------------------------------------


@router.get("/incoming-requests")
async def incoming_requests(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Network holder's incoming intro requests to review.

    Includes contact details (it's their data) + job seeker snapshot.
    """
    result = await db.execute(
        select(IntroFacilitation)
        .where(IntroFacilitation.network_holder_id == current_user.id)
        .order_by(IntroFacilitation.created_at.desc())
    )
    facilitations = list(result.scalars())

    # Batch-load listings (with contacts) and companies to avoid N+1
    listing_ids = [f.marketplace_listing_id for f in facilitations]
    listings_map: dict = {}
    companies_map: dict = {}
    if listing_ids:
        lr = await db.execute(
            select(MarketplaceListing)
            .where(MarketplaceListing.id.in_(listing_ids))
            .options(selectinload(MarketplaceListing.contact))
        )
        listings_map = {listing.id: listing for listing in lr.scalars()}
        company_ids = {
            listing.company_id
            for listing in listings_map.values()
            if listing.company_id
        }
        if company_ids:
            cr = await db.execute(select(Company).where(Company.id.in_(company_ids)))
            companies_map = {c.id: c for c in cr.scalars()}

    data = []
    for f in facilitations:
        resp = IntroFacilitationHolderResponse.model_validate(f).model_dump(mode="json")

        listing = listings_map.get(f.marketplace_listing_id)
        if listing:
            company = companies_map.get(listing.company_id)
            company_name = company.name if company else "Unknown"
            resp["listing_summary"] = _build_listing_summary(
                listing, company_name, None
            ).model_dump(mode="json")

            # Include full contact info for the holder
            contact = listing.contact
            if contact:
                resp["contact_name"] = contact.full_name
                resp["contact_title"] = contact.current_title
                resp["contact_email"] = contact.email
                resp["contact_company"] = contact.current_company

                # Relationship context for NH decision-making
                resp["relationship_type"] = contact.relationship_type
                resp["would_refer"] = contact.would_refer
                resp["how_you_know"] = contact.how_you_know

        data.append(resp)

    return {"data": data, "meta": {"total": len(data)}}


# ---------------------------------------------------------------------------
# PATCH /marketplace/requests/{facilitation_id}
# ---------------------------------------------------------------------------


@router.patch("/requests/{facilitation_id}")
async def update_facilitation(
    facilitation_id: uuid.UUID,
    body: IntroFacilitationActionBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Network holder approves or declines an intro request."""
    result = await db.execute(
        select(IntroFacilitation).where(
            IntroFacilitation.id == facilitation_id,
            IntroFacilitation.network_holder_id == current_user.id,
        )
    )
    facilitation = result.scalar_one_or_none()
    if facilitation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Facilitation request not found",
        )

    if facilitation.status != "requested":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot update facilitation with status '{facilitation.status}'",
        )

    now = datetime.now(timezone.utc)
    contact: Contact | None = None

    if body.action == "approve":
        contact = await _apply_intro_approve(
            facilitation=facilitation,
            body=body,
            current_user=current_user,
            now=now,
            db=db,
        )
    elif body.action == "decline":
        await _apply_intro_decline(
            facilitation=facilitation,
            body=body,
            current_user=current_user,
            now=now,
            db=db,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action must be 'approve' or 'decline'",
        )

    # Update connector reputation
    await _update_connector_reputation(current_user.id, body.action, db)

    # Track funnel step
    from app.utils.tracking import track_action

    action_name = "intro_approve" if body.action == "approve" else "intro_decline"
    await track_action(
        db,
        current_user.id,
        action_name,
        metadata_={"facilitation_id": str(facilitation.id)},
    )

    await db.flush()

    await db.commit()

    # Build response — for LinkedIn fallback, include linkedin_url and drafted_message
    resp_data = IntroFacilitationResponse.model_validate(facilitation).model_dump(
        mode="json"
    )
    if body.action == "approve" and not facilitation.delivery_method:
        _apply_linkedin_fallback_response(facilitation, contact, resp_data)

    return {
        "data": resp_data,
        "meta": {},
    }


# ---------------------------------------------------------------------------
# POST /marketplace/requests/{facilitation_id}/confirm-sent
# ---------------------------------------------------------------------------


@router.post("/requests/{facilitation_id}/confirm-sent")
async def confirm_manual_send(
    facilitation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """NH confirms they manually sent the intro (LinkedIn/other channel)."""
    facilitation = await db.get(IntroFacilitation, facilitation_id)
    if not facilitation or facilitation.network_holder_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Facilitation not found",
        )
    if facilitation.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Facilitation not in approved state",
        )
    if (
        facilitation.delivery_method == "linkedin_manual"
        and facilitation.delivery_status == "delivered"
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Manual send already confirmed",
        )
    if facilitation.credits_awarded_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Credits already awarded",
        )

    allowed, current_count = await check_rate_limit(
        current_user.id,
        "manual_intro_confirm",
        settings.RATE_LIMIT_MANUAL_INTRO_CONFIRMS_PER_DAY,
        db,
        is_admin=current_user.is_admin,
    )
    if not allowed:
        await log_event(
            db,
            "velocity_limit_hit",
            user_id=current_user.id,
            metadata={
                "action": "manual_intro_confirm",
                "count": current_count,
                "max_per_day": settings.RATE_LIMIT_MANUAL_INTRO_CONFIRMS_PER_DAY,
                "facilitation_id": str(facilitation.id),
            },
        )
        await db.commit()
        raise RateLimitError(
            f"Daily manual intro confirmation limit reached ({settings.RATE_LIMIT_MANUAL_INTRO_CONFIRMS_PER_DAY}/day)"
        )

    now = datetime.now(timezone.utc)
    facilitation.delivery_method = "linkedin_manual"
    facilitation.delivery_status = "delivered"
    facilitation.delivered_at = now

    credits_awarded = 0
    if settings.manual_intro_credit_award_enabled:
        # Trust-based reward path (enabled for non-production by default).
        # Non-blocking: delivery confirmation is the primary operation.
        try:
            await earn_credits(
                current_user.id,
                50,
                "intro_facilitation",
                db,
                reference_id=facilitation.id,
            )
            facilitation.credits_awarded_at = now
            credits_awarded = 50
        except ValueError:
            logger.warning(
                "Could not award intro facilitation credits for user %s (daily cap)",
                current_user.id,
            )
    else:
        # Phase 0 guardrail: keep delivery confirmation but defer reward.
        await log_event(
            db,
            "manual_intro_credit_deferred",
            user_id=current_user.id,
            metadata={"facilitation_id": str(facilitation.id)},
        )

    from app.utils.tracking import track_action

    await track_action(
        db,
        current_user.id,
        "manual_intro_confirm",
        metadata_={"facilitation_id": str(facilitation.id)},
    )
    await db.commit()

    return {
        "data": {
            "status": "confirmed",
            "credits_awarded": credits_awarded,
            "credits_deferred": credits_awarded == 0,
        }
    }


# ---------------------------------------------------------------------------
# PUT /marketplace/sharing-preferences
# ---------------------------------------------------------------------------


@router.put("/sharing-preferences")
async def update_sharing_preferences(
    body: NetworkSharingPrefsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Configure marketplace sharing preferences.

    When opt_in flips true → generate listings.
    When opt_in flips false → soft-delete listings + cancel pending facilitations.
    """
    result = await db.execute(
        select(NetworkSharingPreferences).where(
            NetworkSharingPreferences.user_id == current_user.id
        )
    )
    prefs = result.scalar_one_or_none()

    was_opted_in = prefs.opt_in_marketplace if prefs else False

    if prefs is None:
        prefs = NetworkSharingPreferences(
            user_id=current_user.id,
            opt_in_marketplace=body.opt_in_marketplace,
            category_filters=body.category_filters,
            excluded_contact_ids=body.excluded_contact_ids,
            is_paused=body.is_paused,
        )
        db.add(prefs)
    else:
        prefs.opt_in_marketplace = body.opt_in_marketplace
        prefs.category_filters = body.category_filters
        prefs.excluded_contact_ids = body.excluded_contact_ids
        prefs.is_paused = body.is_paused

    await db.flush()

    # Opt-in flip: false → true → generate listings
    if body.opt_in_marketplace and not was_opted_in and not body.is_paused:
        await generate_marketplace_listings(current_user.id, db)
        await db.flush()

    # Opt-out flip: true → false → soft-delete listings + cancel pending
    if not body.opt_in_marketplace and was_opted_in:
        # Soft-delete all listings
        listings_result = await db.execute(
            select(MarketplaceListing).where(
                MarketplaceListing.network_holder_id == current_user.id,
                MarketplaceListing.deleted_at.is_(None),
            )
        )
        now = datetime.now(timezone.utc)
        for listing in listings_result.scalars():
            listing.deleted_at = now

        # Cancel pending facilitations
        facil_result = await db.execute(
            select(IntroFacilitation).where(
                IntroFacilitation.network_holder_id == current_user.id,
                IntroFacilitation.status == "requested",
            )
        )
        for f in facil_result.scalars():
            f.status = "expired"

        await db.flush()

    await db.commit()

    return {
        "data": NetworkSharingPreferencesResponse.model_validate(prefs).model_dump(
            mode="json"
        ),
        "meta": {},
    }


# ---------------------------------------------------------------------------
# GET /marketplace/sharing-preferences
# ---------------------------------------------------------------------------


@router.get("/sharing-preferences")
async def get_sharing_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get current sharing preferences.

    For NH/both users who went through onboarding but never had a row
    created (e.g. unchecked opt-in checkbox), auto-creates a default
    row so the onboarding checklist can mark the step as configured.
    """
    result = await db.execute(
        select(NetworkSharingPreferences).where(
            NetworkSharingPreferences.user_id == current_user.id
        )
    )
    prefs = result.scalar_one_or_none()

    if prefs is None:
        # For NH/both users, lazily create a default row so checklist
        # recognises sharing as configured after first visit to settings.
        if current_user.intent in ("share_network", "explore"):
            prefs = NetworkSharingPreferences(
                user_id=current_user.id,
                opt_in_marketplace=False,
            )
            db.add(prefs)
            await db.commit()
            await db.refresh(prefs)
            data = NetworkSharingPreferencesResponse.model_validate(prefs).model_dump(
                mode="json"
            )
            data["is_configured"] = True
            return {"data": data, "meta": {}}

        return {
            "data": {
                "opt_in_marketplace": False,
                "category_filters": None,
                "excluded_contact_ids": None,
                "is_paused": False,
                "is_configured": False,
            },
            "meta": {},
        }

    data = NetworkSharingPreferencesResponse.model_validate(prefs).model_dump(
        mode="json"
    )
    data["is_configured"] = True
    return {
        "data": data,
        "meta": {},
    }


# ---------------------------------------------------------------------------
# GET /marketplace/my-listings
# ---------------------------------------------------------------------------


@router.get("/my-listings")
async def my_listings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Network holder's own marketplace listings — includes full contact info."""
    result = await db.execute(
        select(MarketplaceListing)
        .where(
            MarketplaceListing.network_holder_id == current_user.id,
            MarketplaceListing.deleted_at.is_(None),
        )
        .options(selectinload(MarketplaceListing.contact))
    )
    listings = list(result.scalars())

    data = []
    for listing in listings:
        contact = listing.contact
        data.append(
            MarketplaceListingDetailResponse(
                id=listing.id,
                company_id=listing.company_id,
                role_level=listing.role_level,
                department_category=listing.department_category,
                warm_score_range=listing.warm_score_range,
                connection_recency=listing.connection_recency,
                is_available=listing.is_available,
                created_at=listing.created_at,
                contact_name=contact.full_name if contact else None,
                contact_title=contact.current_title if contact else None,
                contact_email=contact.email if contact else None,
                contact_company=contact.current_company if contact else None,
            ).model_dump(mode="json")
        )

    return {"data": data, "meta": {"total": len(data)}}
