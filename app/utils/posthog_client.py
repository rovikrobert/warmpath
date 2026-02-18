"""PostHog API client for querying analytics data.

Used by GTM agent scanners to pull funnel metrics, SEO referrals, and
content performance data. Not used in user-facing endpoints.
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _is_configured() -> bool:
    return bool(settings.POSTHOG_API_KEY and settings.POSTHOG_PROJECT_ID)


async def query_funnel(
    steps: list[str],
    date_from: str = "-30d",
    date_to: str | None = None,
) -> dict:
    """Query PostHog for funnel conversion rates."""
    if not _is_configured():
        return {"configured": False, "steps": [], "overall_conversion": None}

    payload = {
        "insight": "FUNNELS",
        "events": [{"id": s, "type": "events"} for s in steps],
        "date_from": date_from,
        "funnel_window_days": 14,
    }
    if date_to:
        payload["date_to"] = date_to
    return await _query(payload)


async def query_trends(
    events: list[str],
    date_from: str = "-30d",
    date_to: str | None = None,
    interval: str = "day",
) -> dict:
    """Query PostHog for event trends over time."""
    if not _is_configured():
        return {"configured": False, "results": []}

    payload = {
        "insight": "TRENDS",
        "events": [{"id": e, "type": "events"} for e in events],
        "date_from": date_from,
        "interval": interval,
    }
    if date_to:
        payload["date_to"] = date_to
    return await _query(payload)


async def query_referral_sources(
    date_from: str = "-30d",
    date_to: str | None = None,
) -> dict:
    """Query PostHog for top referral sources."""
    if not _is_configured():
        return {"configured": False, "sources": []}

    payload = {
        "insight": "TRENDS",
        "events": [{"id": "$pageview", "type": "events"}],
        "breakdown": "$referring_domain",
        "breakdown_type": "event",
        "date_from": date_from,
    }
    if date_to:
        payload["date_to"] = date_to
    return await _query(payload)


async def _query(payload: dict) -> dict:
    """Execute a PostHog insight query."""
    url = f"{settings.POSTHOG_HOST}/api/projects/{settings.POSTHOG_PROJECT_ID}/insights/trend/"
    headers = {"Authorization": f"Bearer {settings.POSTHOG_API_KEY}"}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as e:
        logger.error("PostHog query failed: %s", e)
        return {"error": str(e), "results": []}
