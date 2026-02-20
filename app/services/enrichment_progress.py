"""Enrichment progress tracking and milestone rewards.

Computes enrichment completion percentage and awards bonus credits
when users cross milestone thresholds (10/25/50/75/100%).
"""

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.milestone import UserMilestone
from app.services.credits import earn_credits

# Milestone thresholds: percent -> credits awarded
MILESTONES = {
    10: 10,
    25: 25,
    50: 50,
    75: 75,
    100: 100,
}


async def get_enrichment_stats(user_id: uuid.UUID, db: AsyncSession) -> dict:
    """Get enrichment progress stats for a user's contacts."""
    result = await db.execute(
        select(
            func.count().label("total"),
            func.count(Contact.relationship_type).label("enriched"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            (Contact.relationship_type.isnot(None))
                            & (Contact.would_refer.isnot(None)),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("fully_enriched"),
        ).where(
            Contact.user_id == user_id,
            Contact.deleted_at.is_(None),
        )
    )
    row = result.one()
    total = int(row.total)
    enriched = int(row.enriched)
    fully_enriched = int(row.fully_enriched)
    percentage = round((enriched / total * 100) if total > 0 else 0.0, 1)

    return {
        "total_contacts": total,
        "enriched_contacts": enriched,
        "fully_enriched": fully_enriched,
        "percentage": percentage,
    }


async def get_claimed_milestones(user_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """Get list of milestones already claimed by user."""
    result = await db.execute(
        select(UserMilestone)
        .where(
            UserMilestone.user_id == user_id,
            UserMilestone.milestone_type == "enrichment",
        )
        .order_by(UserMilestone.milestone_value)
    )
    return [
        {
            "milestone_value": m.milestone_value,
            "credits_awarded": m.credits_awarded,
            "claimed_at": m.claimed_at.isoformat() if m.claimed_at else None,
        }
        for m in result.scalars().all()
    ]


def compute_next_milestone(
    percentage: float, claimed_values: set[int]
) -> tuple[int | None, int | None]:
    """Find the next unclaimed milestone above current percentage.

    Returns (next_milestone_percent, credits_at_next) or (None, None).
    """
    for pct in sorted(MILESTONES.keys()):
        if pct not in claimed_values and pct > percentage:
            return pct, MILESTONES[pct]
    return None, None


async def get_enrichment_progress(user_id: uuid.UUID, db: AsyncSession) -> dict:
    """Full enrichment progress response for the API."""
    stats = await get_enrichment_stats(user_id, db)
    milestones_claimed = await get_claimed_milestones(user_id, db)
    claimed_values = {m["milestone_value"] for m in milestones_claimed}

    next_milestone, credits_at_next = compute_next_milestone(
        stats["percentage"], claimed_values
    )

    return {
        **stats,
        "next_milestone": next_milestone,
        "credits_at_next_milestone": credits_at_next,
        "milestones_claimed": milestones_claimed,
    }


async def check_and_award_milestones(
    user_id: uuid.UUID, db: AsyncSession
) -> dict | None:
    """Check if any new milestones were crossed and award credits.

    Called after an enrichment response updates a contact.
    Returns milestone info if one was just claimed, else None.
    """
    stats = await get_enrichment_stats(user_id, db)
    percentage = stats["percentage"]

    # Get already-claimed milestones
    result = await db.execute(
        select(UserMilestone.milestone_value).where(
            UserMilestone.user_id == user_id,
            UserMilestone.milestone_type == "enrichment",
        )
    )
    claimed = {row[0] for row in result.all()}

    # Check each threshold — award the highest newly crossed one
    awarded = None
    for pct in sorted(MILESTONES.keys()):
        if pct not in claimed and percentage >= pct:
            credits = MILESTONES[pct]
            milestone = UserMilestone(
                user_id=user_id,
                milestone_type="enrichment",
                milestone_value=pct,
                credits_awarded=credits,
            )
            db.add(milestone)
            await earn_credits(
                user_id,
                credits,
                "enrichment_milestone",
                db,
                skip_daily_cap=True,
            )
            awarded = {"percent": pct, "credits": credits}

    return awarded
