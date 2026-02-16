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

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.company import Company
from app.models.marketplace import (
    ConnectorReputation,
    IntroFacilitation,
    MarketplaceListing,
    NetworkSharingPreferences,
)
from app.models.user import User
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
from app.services.credits import earn_credits, get_balance, refund_credits, spend_credits
from app.services.marketplace_indexer import generate_marketplace_listings
from app.utils.security import get_current_user

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


def _build_seeker_profile_snapshot(
    user: User, visibility: str
) -> dict:
    """Build a profile snapshot based on visibility level."""
    if visibility == "full":
        return {
            "full_name": user.full_name,
            "email": user.email,
            "user_type": user.user_type,
        }
    elif visibility == "summary":
        return {
            "full_name": user.full_name,
            "user_type": user.user_type,
        }
    else:  # minimal
        return {
            "user_type": user.user_type,
        }


# ---------------------------------------------------------------------------
# POST /marketplace/search
# ---------------------------------------------------------------------------


@router.post("/search")
async def marketplace_search(
    body: MarketplaceSearchBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Search the anonymized marketplace index. Costs 5 credits."""
    # Check credits
    balance = await get_balance(current_user.id, db)
    if balance < 5:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient credits. You need 5 credits for a marketplace search. "
            "Upgrade your plan or earn credits by uploading your network.",
        )

    # Deduct credits
    await spend_credits(current_user.id, 5, "marketplace_search", db)

    # Look up company IDs by name
    company_map: dict[uuid.UUID, str] = {}
    for name in body.company_names:
        result = await db.execute(
            select(Company).where(Company.name.ilike(f"%{name}%"))
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

    result = await db.execute(query)
    listings = list(result.scalars())

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
    current_user: User = Depends(get_current_user),
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

    # Check credits (20 per intro request)
    balance = await get_balance(current_user.id, db)
    if balance < 20:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient credits. You need 20 credits to request an intro.",
        )

    # Deduct credits
    await spend_credits(current_user.id, 20, "intro_request", db)

    # Build profile snapshot
    snapshot = _build_seeker_profile_snapshot(current_user, body.profile_visibility)
    if body.message_to_holder:
        snapshot["message"] = body.message_to_holder

    # Create facilitation record
    facilitation = IntroFacilitation(
        job_seeker_id=current_user.id,
        network_holder_id=listing.network_holder_id,
        marketplace_listing_id=listing.id,
        status="requested",
        job_seeker_profile_snapshot=snapshot,
    )
    db.add(facilitation)
    await db.flush()

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

    data = []
    for f in facilitations:
        resp = IntroFacilitationResponse.model_validate(f).model_dump(mode="json")
        # Load listing summary for context
        listing_result = await db.execute(
            select(MarketplaceListing).where(MarketplaceListing.id == f.marketplace_listing_id)
        )
        listing = listing_result.scalar_one_or_none()
        if listing:
            company_result = await db.execute(
                select(Company).where(Company.id == listing.company_id)
            )
            company = company_result.scalar_one_or_none()
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

    data = []
    for f in facilitations:
        resp = IntroFacilitationHolderResponse.model_validate(f).model_dump(mode="json")

        # Load listing + contact details (holder's own contact)
        listing_result = await db.execute(
            select(MarketplaceListing)
            .where(MarketplaceListing.id == f.marketplace_listing_id)
            .options(selectinload(MarketplaceListing.contact))
        )
        listing = listing_result.scalar_one_or_none()
        if listing:
            company_result = await db.execute(
                select(Company).where(Company.id == listing.company_id)
            )
            company = company_result.scalar_one_or_none()
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

    if body.action == "approve":
        facilitation.status = "approved"
        facilitation.reviewed_at = now
        if body.notes:
            facilitation.network_holder_notes = body.notes

        # Award 50 credits to network holder
        await earn_credits(
            current_user.id,
            50,
            "intro_facilitation",
            db,
            reference_id=facilitation.id,
        )

    elif body.action == "decline":
        facilitation.status = "declined"
        facilitation.reviewed_at = now
        if body.notes:
            facilitation.network_holder_notes = body.notes

        # Refund 15 of 20 credits to job seeker (5 credit fee)
        await refund_credits(
            facilitation.job_seeker_id,
            15,
            "intro_declined_refund",
            db,
            reference_id=facilitation.id,
        )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action must be 'approve' or 'decline'",
        )

    # Update connector reputation
    rep_result = await db.execute(
        select(ConnectorReputation).where(
            ConnectorReputation.user_id == current_user.id
        )
    )
    reputation = rep_result.scalar_one_or_none()
    if reputation is None:
        reputation = ConnectorReputation(user_id=current_user.id)
        db.add(reputation)
        await db.flush()

    if body.action == "approve":
        reputation.intros_facilitated += 1

    await db.flush()

    return {
        "data": IntroFacilitationResponse.model_validate(facilitation).model_dump(
            mode="json"
        ),
        "meta": {},
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
    """Get current sharing preferences."""
    result = await db.execute(
        select(NetworkSharingPreferences).where(
            NetworkSharingPreferences.user_id == current_user.id
        )
    )
    prefs = result.scalar_one_or_none()

    if prefs is None:
        return {
            "data": {
                "opt_in_marketplace": False,
                "category_filters": None,
                "excluded_contact_ids": None,
                "is_paused": False,
            },
            "meta": {},
        }

    return {
        "data": NetworkSharingPreferencesResponse.model_validate(prefs).model_dump(
            mode="json"
        ),
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
