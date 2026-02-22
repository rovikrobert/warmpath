"""Compute action-based user capabilities from DB state."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.marketplace import IntroFacilitation, MarketplaceListing
from app.models.search_request import SearchRequest
from app.models.user import User
from app.schemas.user import UserCapabilities

if TYPE_CHECKING:
    from app.models.user import ConnectorProfile


def compute_profile_completeness(profile: "ConnectorProfile | None") -> dict:
    """Compute profile completeness from ConnectorProfile fields."""
    fields = [
        "headline",
        "current_title",
        "current_company",
        "industry",
        "location",
        "bio_summary",
        "work_history",
        "github_url",
        "portfolio_url",
    ]
    if not profile:
        return {"score": 0, "missing": fields, "total_fields": len(fields)}
    filled = [f for f in fields if getattr(profile, f, None)]
    missing = [f for f in fields if not getattr(profile, f, None)]
    score = round(len(filled) / len(fields) * 100)
    return {"score": score, "missing": missing, "total_fields": len(fields)}


async def compute_user_capabilities(
    user_id: uuid.UUID, db: AsyncSession
) -> UserCapabilities:
    """Derive capabilities from user's actual actions in DB."""
    has_contacts = (
        await db.scalar(
            select(func.count()).select_from(Contact).where(Contact.user_id == user_id)
        )
        or 0
    ) > 0

    has_searches = (
        await db.scalar(
            select(func.count())
            .select_from(SearchRequest)
            .where(SearchRequest.user_id == user_id)
        )
        or 0
    ) > 0

    has_listings = (
        await db.scalar(
            select(func.count())
            .select_from(MarketplaceListing)
            .where(MarketplaceListing.network_holder_id == user_id)
        )
        or 0
    ) > 0

    # Subscription: check plan_tier != 'free'
    user = await db.get(User, user_id)
    has_subscription = user is not None and user.plan_tier not in ("free", None)

    facilitation_count = (
        await db.scalar(
            select(func.count())
            .select_from(IntroFacilitation)
            .where(
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
