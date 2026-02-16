"""Warm score computation — optimized for referral likelihood.

Scores each contact on how likely they are to actually refer the user
for a job. Four components weighted to reflect referral dynamics:
- Recency (35%): Recent contacts are more likely to help
- Relationship (30%): Shared history = stronger referral signal
- Role relevance (20%): Can this person actually refer me?
- Tenure (15%): Longer-tenured employees refer more effectively
"""

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

ALGORITHM_VERSION = "v2-referral"

# Weights for each component (must sum to 1.0)
WEIGHT_RECENCY = 0.35
WEIGHT_RELATIONSHIP = 0.30
WEIGHT_ROLE = 0.20
WEIGHT_TENURE = 0.15


@dataclass
class WarmScoreResult:
    total_score: float
    recency_score: float
    relationship_score: float
    role_score: float
    tenure_score: float
    factors: dict


@dataclass
class ReferralScoreResult:
    total_score: float
    recency_score: float
    relationship_score: float
    role_score: float
    tenure_score: float
    referral_likelihood: str  # "high", "medium", "low"
    factors: dict


# ---------------------------------------------------------------------------
# Component: Recency Score (0-100, weight: 35%)
# ---------------------------------------------------------------------------


def compute_recency_score(connected_on: date | None) -> float:
    """Score based on how recently the contact was connected.

    Recent contacts are much more likely to refer you.
    """
    if connected_on is None:
        return 30.0  # neutral default

    today = date.today()
    delta_days = (today - connected_on).days
    months = delta_days / 30.44  # avg days per month

    if months < 6:
        return 100.0
    elif months < 12:
        return 85.0
    elif months < 24:
        return 70.0
    elif months < 36:
        return 55.0
    elif months < 60:
        return 35.0
    else:
        return 15.0


# ---------------------------------------------------------------------------
# Component: Relationship Score (0-100, weight: 30%)
# ---------------------------------------------------------------------------


def compute_relationship_score(
    contact: Contact,
    profile: ConnectorProfile | None,
) -> tuple[float, dict]:
    """Score based on relationship strength between user and contact.

    Shared work history is the strongest referral signal.
    Returns (score, factors_dict) for transparency.
    """
    if profile is None:
        return 0.0, {"reason": "no connector profile set"}

    score = 0.0
    factors: dict[str, bool] = {}

    # Previously worked at same company (+40) — strongest referral signal
    # Check enriched_data for work history overlap
    former_colleague = False
    enriched = getattr(contact, "enriched_data", None) or {}
    if isinstance(enriched, dict):
        work_history = enriched.get("work_history", [])
        user_company = (profile.current_company or "").strip().lower()
        if user_company:
            for entry in work_history:
                company_name = (entry.get("company", "") or "").strip().lower()
                if company_name and _fuzzy_eq(company_name, user_company):
                    former_colleague = True
                    break

    if former_colleague:
        score += 40
        factors["former_colleague"] = True
    else:
        factors["former_colleague"] = False

    # Same current company (+35)
    if (
        profile.current_company
        and contact.current_company
        and _fuzzy_eq(profile.current_company, contact.current_company)
    ):
        score += 35
        factors["same_company"] = True
    else:
        factors["same_company"] = False

    # Same industry (+20)
    if profile.industry and contact.current_company:
        contact_industry = ""
        if hasattr(contact, "company") and contact.company:
            contact_industry = (getattr(contact.company, "industry", "") or "").lower()
        if contact_industry and profile.industry.strip().lower() in contact_industry:
            score += 20
            factors["same_industry"] = True
        else:
            factors["same_industry"] = False
    else:
        factors["same_industry"] = False

    # Same location (+15)
    if (
        profile.location
        and contact.location
        and _fuzzy_eq(profile.location, contact.location)
    ):
        score += 15
        factors["same_location"] = True
    else:
        factors["same_location"] = False

    # Same school (+15) — from enrichment data
    same_school = False
    user_schools = enriched.get("schools", [])
    profile_bio = (getattr(profile, "bio_summary", "") or "").lower()
    if isinstance(user_schools, list):
        for school in user_schools:
            school_name = (school if isinstance(school, str) else "").lower()
            if school_name and school_name in profile_bio:
                same_school = True
                break
    if same_school:
        score += 15
        factors["same_school"] = True
    else:
        factors["same_school"] = False

    return min(score, 100.0), factors


def _fuzzy_eq(a: str, b: str) -> bool:
    """Case-insensitive, whitespace-normalized comparison."""
    return a.strip().lower() == b.strip().lower()


# ---------------------------------------------------------------------------
# Component: Role Relevance Score (0-100, weight: 20%)
# ---------------------------------------------------------------------------

# Department/function keywords for matching
_DEPT_KEYWORDS: dict[str, list[str]] = {
    "engineering": ["engineer", "developer", "software", "sre", "devops", "platform", "backend", "frontend", "fullstack", "infrastructure"],
    "product": ["product manager", "product lead", "product owner", "pm"],
    "design": ["designer", "ux", "ui", "design lead"],
    "data": ["data scientist", "data engineer", "data analyst", "machine learning", "ml", "analytics"],
    "marketing": ["marketing", "growth", "brand", "content", "communications"],
    "sales": ["sales", "account executive", "ae", "business development", "bdr", "sdr"],
    "finance": ["finance", "accounting", "controller", "treasury", "fp&a"],
    "hr": ["hr", "human resources", "people", "talent", "recruiting", "recruiter"],
    "operations": ["operations", "ops", "logistics", "supply chain"],
    "legal": ["legal", "counsel", "compliance", "attorney"],
}

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


def _detect_department(title: str) -> str | None:
    """Detect department from a job title."""
    title_lower = title.lower()
    for dept, keywords in _DEPT_KEYWORDS.items():
        if any(kw in title_lower for kw in keywords):
            return dept
    return None


def compute_role_score(title: str | None, target_role: str | None = None) -> float:
    """Score based on referral ability — can this person actually refer me?

    For referrals, a senior engineer at Google is more likely to refer you
    for an eng role than the CEO. Peer-level contacts in the same department
    are the strongest referrers.
    """
    if not title:
        return 30.0  # unknown

    title_lower = title.lower()

    # If we have a target role, check department alignment
    if target_role:
        contact_dept = _detect_department(title)
        target_dept = _detect_department(target_role)

        if contact_dept and target_dept:
            same_dept = contact_dept == target_dept
            adjacent = (contact_dept, target_dept) in [
                ("engineering", "product"), ("product", "engineering"),
                ("engineering", "data"), ("data", "engineering"),
                ("product", "design"), ("design", "product"),
                ("marketing", "product"), ("product", "marketing"),
                ("sales", "marketing"), ("marketing", "sales"),
            ]

            if same_dept:
                # Same department — score by seniority for referral ability
                if _SENIOR_PATTERN.search(title):
                    return 100.0  # Senior IC in same dept — best referrer
                if _MANAGER_PATTERN.search(title):
                    return 100.0  # Manager in same dept — knows hiring manager
                if _DIRECTOR_PATTERN.search(title):
                    return 95.0  # Director in same dept
                if _VP_PATTERN.search(title):
                    return 85.0  # VP in same dept
                return 80.0  # Any IC in same dept

            if adjacent:
                return 70.0  # Adjacent department

    # Fallback: no target role or no department match — score by seniority
    if _MANAGER_PATTERN.search(title) or _DIRECTOR_PATTERN.search(title):
        return 60.0  # Manager/Director can refer to any role
    if _SENIOR_PATTERN.search(title):
        return 55.0  # Senior IC in relevant dept
    if _VP_PATTERN.search(title):
        return 50.0  # VP+ can refer to any role
    if _CSUITE_PATTERN.search(title):
        return 40.0  # C-suite — too senior, won't bother for a referral
    # IC/Associate in unrelated dept
    return 20.0


# ---------------------------------------------------------------------------
# Component: Tenure Score (0-100, weight: 15%)
# ---------------------------------------------------------------------------


def compute_tenure_score(months_at_company: int | None = None) -> float:
    """Score based on tenure at current company.

    People who've been there longer can refer more effectively.
    1-3 years is the sweet spot — enough credibility, still engaged.
    """
    if months_at_company is None:
        return 50.0  # unknown — neutral default

    if months_at_company < 6:
        return 40.0  # new hire, not enough cred yet
    elif months_at_company < 12:
        return 70.0
    elif months_at_company <= 36:
        return 100.0  # sweet spot: 1-3 years
    elif months_at_company <= 60:
        return 85.0  # 3-5 years
    else:
        return 70.0  # 5+ years — established but may be less engaged


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------


def compute_warm_score(
    contact: Contact,
    connector_profile: ConnectorProfile | None,
    target_role: str | None = None,
) -> WarmScoreResult:
    """Compute the full warm score for a single contact."""
    recency = compute_recency_score(contact.connected_on)
    relationship, relationship_factors = compute_relationship_score(
        contact, connector_profile
    )
    role = compute_role_score(contact.current_title, target_role=target_role)

    # Extract tenure from enrichment data if available
    months_at_company = None
    enriched = getattr(contact, "enriched_data", None) or {}
    if isinstance(enriched, dict):
        months_at_company = enriched.get("months_at_company")
    tenure = compute_tenure_score(months_at_company)

    total = (
        recency * WEIGHT_RECENCY
        + relationship * WEIGHT_RELATIONSHIP
        + role * WEIGHT_ROLE
        + tenure * WEIGHT_TENURE
    )
    total = round(min(total, 100.0), 2)

    factors = {
        "recency": {"score": recency, "weight": WEIGHT_RECENCY},
        "relationship": {
            "score": relationship,
            "weight": WEIGHT_RELATIONSHIP,
            **relationship_factors,
        },
        "role": {
            "score": role,
            "weight": WEIGHT_ROLE,
            "title": contact.current_title,
            "target_role": target_role,
        },
        "tenure": {
            "score": tenure,
            "weight": WEIGHT_TENURE,
            "months_at_company": months_at_company,
        },
    }

    return WarmScoreResult(
        total_score=total,
        recency_score=recency,
        relationship_score=relationship,
        role_score=role,
        tenure_score=tenure,
        factors=factors,
    )


def compute_referral_score(
    contact: Contact,
    user_profile: ConnectorProfile | None,
    target_role: str | None = None,
) -> ReferralScoreResult:
    """Compute warm score with referral likelihood classification.

    high: warm_score >= 70
    medium: warm_score 45-69
    low: warm_score < 45
    """
    ws = compute_warm_score(contact, user_profile, target_role=target_role)

    if ws.total_score >= 70:
        likelihood = "high"
    elif ws.total_score >= 45:
        likelihood = "medium"
    else:
        likelihood = "low"

    return ReferralScoreResult(
        total_score=ws.total_score,
        recency_score=ws.recency_score,
        relationship_score=ws.relationship_score,
        role_score=ws.role_score,
        tenure_score=ws.tenure_score,
        referral_likelihood=likelihood,
        factors=ws.factors,
    )


# ---------------------------------------------------------------------------
# Batch computation
# ---------------------------------------------------------------------------


async def batch_compute_scores(
    user_id: uuid.UUID,
    db: AsyncSession,
    target_role: str | None = None,
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
        ref_result = compute_referral_score(contact, profile, target_role=target_role)

        # Upsert: check for existing score row
        existing_result = await db.execute(
            select(WarmScore).where(
                WarmScore.user_id == user_id,
                WarmScore.contact_id == contact.id,
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            existing.total_score = Decimal(str(ref_result.total_score))
            existing.recency_score = Decimal(str(ref_result.recency_score))
            existing.context_score = Decimal(str(ref_result.relationship_score))
            existing.role_score = Decimal(str(ref_result.role_score))
            existing.tenure_score = Decimal(str(ref_result.tenure_score))
            existing.score_factors = ref_result.factors
            existing.referral_likelihood = ref_result.referral_likelihood
            existing.algorithm_version = ALGORITHM_VERSION
            existing.computed_at = datetime.now(timezone.utc)
            scores.append(existing)
        else:
            ws = WarmScore(
                user_id=user_id,
                contact_id=contact.id,
                total_score=Decimal(str(ref_result.total_score)),
                recency_score=Decimal(str(ref_result.recency_score)),
                context_score=Decimal(str(ref_result.relationship_score)),
                role_score=Decimal(str(ref_result.role_score)),
                tenure_score=Decimal(str(ref_result.tenure_score)),
                score_factors=ref_result.factors,
                referral_likelihood=ref_result.referral_likelihood,
                algorithm_version=ALGORITHM_VERSION,
                computed_at=datetime.now(timezone.utc),
            )
            db.add(ws)
            scores.append(ws)

    await db.flush()
    return scores
