import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.match_result import WarmScore
from app.models.user import ConnectorProfile

ALGORITHM_VERSION = "v1"

# Weights for each component (must sum to 1.0)
WEIGHT_RECENCY = 0.30
WEIGHT_CONTEXT = 0.30
WEIGHT_ROLE = 0.25
WEIGHT_TENURE = 0.15


@dataclass
class WarmScoreResult:
    total_score: float
    recency_score: float
    context_score: float
    role_score: float
    tenure_score: float
    factors: dict


# ---------------------------------------------------------------------------
# Component: Recency Score (0-100)
# ---------------------------------------------------------------------------


def compute_recency_score(connected_on: date | None) -> float:
    """Score based on how recently the contact was connected."""
    if connected_on is None:
        return 30.0  # neutral default

    today = date.today()
    delta_days = (today - connected_on).days
    months = delta_days / 30.44  # avg days per month

    if months < 6:
        return 100.0
    elif months < 12:
        return 80.0
    elif months < 24:
        return 60.0
    elif months < 60:
        return 40.0
    else:
        return 20.0


# ---------------------------------------------------------------------------
# Component: Context Score (0-100)
# ---------------------------------------------------------------------------


def compute_context_score(
    contact: Contact,
    profile: ConnectorProfile | None,
) -> tuple[float, dict]:
    """Score based on shared context between user and contact.

    Returns (score, factors_dict) for transparency.
    """
    if profile is None:
        return 0.0, {"reason": "no connector profile set"}

    score = 0.0
    factors: dict[str, bool] = {}

    # Same current company (+40)
    if (
        profile.current_company
        and contact.current_company
        and _fuzzy_eq(profile.current_company, contact.current_company)
    ):
        score += 40
        factors["same_company"] = True

    # Same industry (+25)
    if (
        profile.industry and contact.current_title
        # We don't have industry on contacts directly, but we can
        # check if the profile industry appears in the contact's company
        # context. For now, this is a placeholder — enrichment will improve it.
    ):
        factors["same_industry"] = False

    # Same location (+20)
    if (
        profile.location
        and contact.location
        and _fuzzy_eq(profile.location, contact.location)
    ):
        score += 20
        factors["same_location"] = True

    # Previously at same company (+15) — requires enriched work history.
    # For now, not computable from CSV data alone.
    factors.setdefault("same_company", False)
    factors.setdefault("same_location", False)

    return min(score, 100.0), factors


def _fuzzy_eq(a: str, b: str) -> bool:
    """Case-insensitive, whitespace-normalized comparison."""
    return a.strip().lower() == b.strip().lower()


# ---------------------------------------------------------------------------
# Component: Role Score (0-100)
# ---------------------------------------------------------------------------

_CSUITE_PATTERN = re.compile(
    r"\b(c[eotifsm]o|chief|founder|co-founder|cofounder|president|owner|partner)\b",
    re.IGNORECASE,
)
_VP_PATTERN = re.compile(
    r"\b(vp|vice\s*president|svp|evp|avp)\b",
    re.IGNORECASE,
)
_DIRECTOR_PATTERN = re.compile(
    r"\b(director)\b",
    re.IGNORECASE,
)
_MANAGER_PATTERN = re.compile(
    r"\b(manager|head\s+of|lead|team\s+lead|principal)\b",
    re.IGNORECASE,
)
_SENIOR_PATTERN = re.compile(
    r"\b(senior|sr\.?|staff)\b",
    re.IGNORECASE,
)


def compute_role_score(title: str | None) -> float:
    """Score based on seniority/influence inferred from job title."""
    if not title:
        return 30.0  # unknown

    # Check VP before C-suite because "Vice President" contains "president"
    if _VP_PATTERN.search(title):
        return 85.0
    if _CSUITE_PATTERN.search(title):
        return 100.0
    if _DIRECTOR_PATTERN.search(title):
        return 70.0
    if _MANAGER_PATTERN.search(title):
        return 55.0
    if _SENIOR_PATTERN.search(title):
        return 40.0

    # Default: IC / Associate level
    return 25.0


# ---------------------------------------------------------------------------
# Component: Tenure Score (0-100)
# ---------------------------------------------------------------------------


def compute_tenure_score() -> float:
    """Tenure at current company. Requires enrichment data — default for now."""
    return 50.0


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------


def compute_warm_score(
    contact: Contact,
    connector_profile: ConnectorProfile | None,
) -> WarmScoreResult:
    """Compute the full warm score for a single contact."""
    recency = compute_recency_score(contact.connected_on)
    context, context_factors = compute_context_score(contact, connector_profile)
    role = compute_role_score(contact.current_title)
    tenure = compute_tenure_score()

    total = (
        recency * WEIGHT_RECENCY
        + context * WEIGHT_CONTEXT
        + role * WEIGHT_ROLE
        + tenure * WEIGHT_TENURE
    )
    total = round(min(total, 100.0), 2)

    factors = {
        "recency": {"score": recency, "weight": WEIGHT_RECENCY},
        "context": {"score": context, "weight": WEIGHT_CONTEXT, **context_factors},
        "role": {"score": role, "weight": WEIGHT_ROLE, "title": contact.current_title},
        "tenure": {"score": tenure, "weight": WEIGHT_TENURE},
    }

    return WarmScoreResult(
        total_score=total,
        recency_score=recency,
        context_score=context,
        role_score=role,
        tenure_score=tenure,
        factors=factors,
    )


# ---------------------------------------------------------------------------
# Batch computation
# ---------------------------------------------------------------------------


async def batch_compute_scores(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[WarmScore]:
    """Compute warm scores for all of a user's active contacts.

    Upserts into the warm_scores table (one row per user+contact).
    """
    # Load connector profile
    result = await db.execute(
        select(ConnectorProfile).where(ConnectorProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()

    # Load all active contacts
    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.deleted_at.is_(None),
        )
    )
    contacts = result.scalars().all()

    scores: list[WarmScore] = []
    for contact in contacts:
        ws_result = compute_warm_score(contact, profile)

        # Upsert: check for existing score row
        existing_result = await db.execute(
            select(WarmScore).where(
                WarmScore.user_id == user_id,
                WarmScore.contact_id == contact.id,
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            existing.total_score = Decimal(str(ws_result.total_score))
            existing.recency_score = Decimal(str(ws_result.recency_score))
            existing.context_score = Decimal(str(ws_result.context_score))
            existing.role_score = Decimal(str(ws_result.role_score))
            existing.tenure_score = Decimal(str(ws_result.tenure_score))
            existing.score_factors = ws_result.factors
            existing.algorithm_version = ALGORITHM_VERSION
            existing.computed_at = datetime.now(timezone.utc)
            scores.append(existing)
        else:
            ws = WarmScore(
                user_id=user_id,
                contact_id=contact.id,
                total_score=Decimal(str(ws_result.total_score)),
                recency_score=Decimal(str(ws_result.recency_score)),
                context_score=Decimal(str(ws_result.context_score)),
                role_score=Decimal(str(ws_result.role_score)),
                tenure_score=Decimal(str(ws_result.tenure_score)),
                score_factors=ws_result.factors,
                algorithm_version=ALGORITHM_VERSION,
                computed_at=datetime.now(timezone.utc),
            )
            db.add(ws)
            scores.append(ws)

    await db.flush()
    return scores
