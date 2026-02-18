"""Compute action-based user capabilities from DB state."""
from __futu[RESEND_KEY_REDACTED] import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.marketplace import IntroFacilitation, MarketplaceListing
from app.models.search_request import SearchRequest
from app.models.user import User
from app.schemas.user import UserCapabilities


async def compute_user_capabilities(
    user_id: uuid.UUID, db: AsyncSession
) -> UserCapabilities:
    """Derive capabilities from user's actual actions in DB."""
    has_contacts = (
        await db.scalar(
            select(func.count()).select_from(Contact).where(
                Contact.user_id == user_id
            )
        )
        or 0
    ) > 0

    has_searches = (
        await db.scalar(
            select(func.count()).select_from(SearchRequest).where(
                SearchRequest.user_id == user_id
            )
        )
        or 0
    ) > 0

    has_listings = (
        await db.scalar(
            select(func.count()).select_from(MarketplaceListing).where(
                MarketplaceListing.network_holder_id == user_id
            )
        )
        or 0
    ) > 0

    # Subscription: check plan_tier != 'free'
    user = await db.get(User, user_id)
    has_subscription = user is not None and user.plan_tier not in ("free", None)

    facilitation_count = (
        await db.scalar(
            select(func.count()).select_from(IntroFacilitation).where(
                IntroFacilitation.network_holder_id == user_id,
                IntroFacilitation.status == "approved",
            )
        )
        or 0
    )

    return UserCapabilities(
        has_contacts=has_contacts,
        has_searches=has_searches,
        has_listings=has_listings,
        has_subscription=has_subscription,
        facilitation_count=facilitation_count,
    )
