"""Usage metering — tier-aware soft rate limits for high-value actions.

Exposes helpers that the main UsageTrackingMiddleware calls in the same
DB session (avoids BaseHTTPMiddleware stacking issues with SQLite).

Free tier limits (standard):
  - marketplace_search: 0 (blocked — needs paid plan)
  - intro_request: 0 (blocked — needs paid plan)
  - smart_search: 3/month
  - intro_draft: 5/month
  - csv_upload: 1/month
  - job_scan, application_create: unlimited

Beta sandbox mode (BETA_SANDBOX_MODE=true) relaxes limits to encourage
exploration during early beta. See get_free_tier_limits().

Never blocks requests — adds X-WarmPath-Usage-Warning headers only.
"""

import re
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enrichment import UsageLog

# ---- metered action definitions ----

_METERED_ROUTES: list[tuple[str, re.Pattern, str]] = [
    ("POST", re.compile(r"^/api/v1/contacts/upload$"), "csv_upload"),
    ("POST", re.compile(r"^/api/v1/search/smart$"), "smart_search"),
    ("POST", re.compile(r"^/api/v1/matches/intros$"), "intro_draft"),
    ("GET", re.compile(r"^/api/v1/jobs/scan/[^/]+$"), "job_scan"),
    ("POST", re.compile(r"^/api/v1/applications$"), "application_create"),
    ("POST", re.compile(r"^/api/v1/marketplace/search$"), "marketplace_search"),
    ("POST", re.compile(r"^/api/v1/marketplace/request-intro$"), "intro_request"),
    ("POST", re.compile(r"^/api/v1/contacts/nlp-search$"), "nlp_search"),
]

_STANDARD_FREE_TIER_LIMITS: dict[str, int] = {
    "smart_search": 3,
    "intro_draft": 5,
    "csv_upload": 1,
    "marketplace_search": 0,
    "intro_request": 0,
    "nlp_search": 10,
}

_BETA_FREE_TIER_LIMITS: dict[str, int] = {
    "smart_search": 25,
    "intro_draft": 25,
    "csv_upload": 5,
    "marketplace_search": 15,
    "intro_request": 10,
    "nlp_search": 50,
}

# Backward compat alias (points to standard limits)
FREE_TIER_LIMITS = _STANDARD_FREE_TIER_LIMITS


def get_free_tier_limits() -> dict[str, int]:
    """Return the active free-tier limits, respecting BETA_SANDBOX_MODE."""
    from app.config import settings

    if settings.BETA_SANDBOX_MODE:
        return _BETA_FREE_TIER_LIMITS
    return _STANDARD_FREE_TIER_LIMITS


_MARKETPLACE_WARNING = (
    "Marketplace access requires a paid plan. Upgrade for full access."
)

_ACTION_LABELS: dict[str, str] = {
    "smart_search": "smart searches",
    "intro_draft": "intro drafts",
    "csv_upload": "CSV uploads",
    "marketplace_search": "marketplace searches",
    "intro_request": "intro requests",
    "nlp_search": "NLP searches",
}


def match_metered_action(method: str, path: str) -> str | None:
    """Return metered action name if this request is metered, else None."""
    for route_method, pattern, action in _METERED_ROUTES:
        if method == route_method and pattern.match(path):
            return action
    return None


async def compute_metering_warning(
    user_id, action: str, db: AsyncSession
) -> str | None:
    """Query current month counts and return a warning string (or None).

    Must be called inside an active session — does NOT commit.
    """
    from app.models.user import User

    # Check plan tier and admin status
    user_result = await db.execute(
        select(User.plan_tier, User.is_admin).where(User.id == user_id)
    )
    row = user_result.one_or_none()
    if row is None:
        return None
    plan_tier, is_admin = row
    plan_tier = plan_tier or "free"

    limits = get_free_tier_limits()
    if is_admin or plan_tier != "free" or action not in limits:
        return None

    limit = limits[action]

    if limit == 0:
        return _MARKETPLACE_WARNING

    # Count this month's metered uses
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    count_result = await db.execute(
        select(func.count())
        .select_from(UsageLog)
        .where(
            UsageLog.user_id == user_id,
            UsageLog.action == action,
            UsageLog.resource_type == "metered",
            UsageLog.created_at >= month_start,
        )
    )
    count = count_result.scalar() or 0

    label = _ACTION_LABELS.get(action, action.replace("_", " "))
    if count >= limit:
        return (
            f"Free tier limit reached for {label} "
            f"({count}/{limit} this month). "
            f"Upgrade for unlimited access."
        )
    elif count >= limit - 1:
        return f"Approaching free tier limit for {label} ({count}/{limit} this month)."
    return None
