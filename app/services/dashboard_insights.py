"""Dashboard insights: personalized welcome card with three tiers of insight.

Tier 1 — Job Market Trends: reuses get_recommendations() job scanner
Tier 2 — Network Analysis: pure SQL on Contact table
Tier 3 — Daily Tip: static curated list, rotates by day of year
"""

import logging
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.contact import Contact
from app.models.enrichment import EnrichmentCache
from app.models.job import UserJobPreferences
from app.models.search_request import SearchRequest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cache helpers (same pattern as job_recommendations.py)
# ---------------------------------------------------------------------------


async def _read_cache(cache_key: str, db: AsyncSession) -> dict | None:
    """Read from EnrichmentCache if not expired."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(EnrichmentCache).where(
            EnrichmentCache.cache_key == cache_key,
            EnrichmentCache.expires_at > now,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        return None
    return entry.data


async def _write_cache(
    cache_key: str, data: dict, ttl_hours: int, db: AsyncSession
) -> None:
    """Upsert into EnrichmentCache with TTL."""
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

    result = await db.execute(
        select(EnrichmentCache).where(EnrichmentCache.cache_key == cache_key)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.data = data
        existing.expires_at = expires_at
        existing.updated_at = datetime.now(timezone.utc)
    else:
        db.add(
            EnrichmentCache(
                cache_key=cache_key,
                source="dashboard_insights",
                data=data,
                expires_at=expires_at,
            )
        )


# ---------------------------------------------------------------------------
# Tier 1 — Job Market Trends
# ---------------------------------------------------------------------------


async def _get_recently_searched_companies(
    user_id: uuid.UUID, db: AsyncSession
) -> list[str]:
    """Return company names the user has searched for in the past 30 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    result = await db.execute(
        select(SearchRequest.target_companies).where(
            SearchRequest.user_id == user_id,
            SearchRequest.created_at >= cutoff,
            SearchRequest.deleted_at.is_(None),
            SearchRequest.target_companies.isnot(None),
        )
    )
    # target_companies is ARRAY(Text), each row may have multiple company names
    names: list[str] = []
    for (companies,) in result.all():
        if isinstance(companies, list):
            names.extend(companies)
        elif isinstance(companies, str):
            # SQLite stores JSON-encoded arrays
            import json as _json

            try:
                parsed = _json.loads(companies)
                if isinstance(parsed, list):
                    names.extend(parsed)
            except (ValueError, TypeError):
                pass
    # Deduplicate while preserving order (most recent first)
    seen: set[str] = set()
    unique: list[str] = []
    for n in names:
        key = n.strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(n.strip())
    return unique


async def _get_job_market_trends(
    prefs: UserJobPreferences, user_id: uuid.UUID, db: AsyncSession
) -> dict | None:
    """Scan top companies for the user's target role and summarize."""
    cache_key = f"dashboard_trends:{user_id}"
    cached = await _read_cache(cache_key, db)
    if cached is not None:
        return cached

    from app.services.job_recommendations import get_recommendations

    result = await get_recommendations(
        target_role=prefs.target_role,
        target_seniority=prefs.target_seniority,
        target_locations=prefs.target_locations if prefs.target_locations else None,
        exclude_companies=None,
        limit=20,
        db=db,
    )

    recs = result.get("recommendations", [])

    if not recs:
        return None

    companies_hiring = len(recs)

    # Check which of the user's recently-searched companies are hiring
    recent_companies = await _get_recently_searched_companies(user_id, db)
    rec_display_names = {r["display_name"].lower(): r for r in recs}
    rec_keys = {r["company"].lower(): r for r in recs}

    searched_and_hiring: list[str] = []
    for name in recent_companies:
        lower = name.lower()
        if lower in rec_display_names:
            searched_and_hiring.append(rec_display_names[lower]["display_name"])
        elif lower in rec_keys:
            searched_and_hiring.append(rec_keys[lower]["display_name"])

    # Deduplicate trending titles across all recommendations
    title_counts: dict[str, int] = {}
    for rec in recs:
        for title in rec.get("top_titles", []):
            normalized = title.strip()
            if normalized:
                title_counts[normalized] = title_counts.get(normalized, 0) + 1
    trending_titles = sorted(title_counts, key=title_counts.get, reverse=True)[:5]

    # Top companies by score (prioritize user's searched companies)
    searched_set = {n.lower() for n in searched_and_hiring}
    # Split recs: user-searched first, then the rest
    searched_recs = [r for r in recs if r["display_name"].lower() in searched_set]
    other_recs = [r for r in recs if r["display_name"].lower() not in searched_set]
    prioritized_recs = searched_recs + other_recs
    top_companies = [r["display_name"] for r in prioritized_recs[:3]]

    # Region breakdown
    region_counts: dict[str, int] = {}
    for rec in recs:
        region = rec.get("region") or "Other"
        region_counts[region] = region_counts.get(region, 0) + 1

    # Build personalized summary
    role = prefs.target_role or "your target role"
    top_names = ", ".join(top_companies)
    if searched_and_hiring:
        # Personalized: mention their searched companies specifically
        names_str = ", ".join(searched_and_hiring[:3])
        others = companies_hiring - len(searched_and_hiring)
        if others > 0:
            summary = (
                f"{names_str} and {others} other {'company' if others == 1 else 'companies'} "
                f"are actively hiring for {role} roles."
            )
        else:
            summary = f"{names_str} {'is' if len(searched_and_hiring) == 1 else 'are'} actively hiring for {role} roles."
    else:
        # Generic but not "scanned" language
        summary = (
            f"{companies_hiring} companies are actively hiring for {role} roles "
            f"in your target market. Top: {top_names}."
        )

    trends = {
        "summary": summary,
        "companies_hiring": companies_hiring,
        "trending_titles": trending_titles,
        "top_companies": top_companies,
        "searched_and_hiring": searched_and_hiring,
        "region_breakdown": region_counts,
    }

    await _write_cache(cache_key, trends, settings.DASHBOARD_TRENDS_CACHE_TTL_HOURS, db)
    return trends


# ---------------------------------------------------------------------------
# Tier 2 — Network Analysis
# ---------------------------------------------------------------------------


async def _get_network_analysis(
    user_id: uuid.UUID, db: AsyncSession, prefs: UserJobPreferences | None = None
) -> dict | None:
    """Analyze the user's contacts to show network strengths."""
    cache_key = f"dashboard_network:{user_id}"
    cached = await _read_cache(cache_key, db)
    if cached is not None:
        return cached

    # Total contact count
    total_result = await db.execute(
        select(func.count(Contact.id)).where(
            Contact.user_id == user_id,
            Contact.deleted_at.is_(None),
        )
    )
    total_contacts = total_result.scalar() or 0

    if total_contacts == 0:
        return None

    # Top 10 companies by contact count — in-memory because current_company
    # is encrypted and cannot be grouped/compared at SQL level
    contacts_result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.deleted_at.is_(None),
        )
    )
    all_contacts = list(contacts_result.scalars())
    company_counts = Counter(
        c.current_company
        for c in all_contacts
        if c.current_company and c.current_company.strip()
    )
    top_companies = [
        {"company": co, "count": n} for co, n in company_counts.most_common(10)
    ]

    # Relationship type breakdown
    rel_result = await db.execute(
        select(
            Contact.relationship_type,
            func.count(Contact.id).label("cnt"),
        )
        .where(
            Contact.user_id == user_id,
            Contact.deleted_at.is_(None),
        )
        .group_by(Contact.relationship_type)
        .order_by(func.count(Contact.id).desc())
    )
    relationship_breakdown = {
        (row[0] or "unclassified"): row[1] for row in rel_result.all()
    }

    # Build summary
    top_names = ", ".join(f"{c['company']} ({c['count']})" for c in top_companies[:3])
    # Find the most common relationship type
    top_rel = (
        max(relationship_breakdown, key=relationship_breakdown.get)
        if relationship_breakdown
        else None
    )
    top_rel_count = relationship_breakdown.get(top_rel, 0) if top_rel else 0

    parts = [f"You have {total_contacts} contacts."]
    if top_companies:
        parts.append(f"Strongest networks: {top_names}.")
    if top_rel and top_rel != "unclassified":
        parts.append(f"{top_rel_count} {top_rel} connections.")

    summary = " ".join(parts)

    # Network gaps: if user has target locations, check coverage
    network_gaps = None
    if prefs and prefs.target_locations:
        from app.services.board_registry import (
            companies_for_locations,
            get_display_name,
        )

        target_companies = companies_for_locations(prefs.target_locations)[:15]
        user_company_names = {
            c["company"].lower() for c in top_companies if c["company"]
        }

        missing = []
        for key in target_companies:
            display = get_display_name(key)
            if (
                display.lower() not in user_company_names
                and key not in user_company_names
            ):
                missing.append(display)

        if missing:
            network_gaps = missing[:5]

    analysis = {
        "summary": summary,
        "total_contacts": total_contacts,
        "top_companies": top_companies,
        "relationship_breakdown": relationship_breakdown,
        "network_gaps": network_gaps,
    }

    await _write_cache(
        cache_key, analysis, settings.DASHBOARD_NETWORK_CACHE_TTL_HOURS, db
    )
    return analysis


# ---------------------------------------------------------------------------
# Tier 3 — Daily Rotating Tip
# ---------------------------------------------------------------------------

TIPS = [
    # Networking
    {
        "tip": "When requesting a referral, always include a 2-sentence summary of why you're a strong fit for the specific role.",
        "category": "networking",
    },
    {
        "tip": "Reach out to former colleagues before current ones \u2014 they've already seen your work and are more likely to vouch for you.",
        "category": "networking",
    },
    {
        "tip": "Before contacting someone for a referral, check if they've been at their company for at least 6 months. Newer employees rarely have enough capital to refer.",
        "category": "networking",
    },
    {
        "tip": "Don't ask 'Can you refer me?' \u2014 ask 'Would you be comfortable referring me for this role?' It gives them an easy out and builds trust.",
        "category": "networking",
    },
    {
        "tip": "Follow up on referral requests after 3-5 business days. People are busy, not uninterested.",
        "category": "networking",
    },
    {
        "tip": "When reaching out to a former manager, reference a specific project you worked on together. It triggers positive recall.",
        "category": "networking",
    },
    # Resume
    {
        "tip": "Tailor your resume for each referral. The person referring you will often forward it directly \u2014 make it easy for them to advocate.",
        "category": "resume",
    },
    {
        "tip": "Lead every bullet point with a measurable impact: revenue generated, time saved, users served, or systems built.",
        "category": "resume",
    },
    {
        "tip": "Keep your resume to one page if you have under 10 years of experience. Recruiters spend 6-8 seconds on initial scan.",
        "category": "resume",
    },
    {
        "tip": "Remove objective statements. Replace with a 2-line professional summary that matches the role's requirements.",
        "category": "resume",
    },
    {
        "tip": "Include the exact job title you're targeting in your resume header. ATS systems match on this.",
        "category": "resume",
    },
    {
        "tip": "If you've been promoted, show it clearly with dates. Internal promotions signal that previous employers valued your work.",
        "category": "resume",
    },
    # Interviewing
    {
        "tip": "Prepare 3-5 STAR stories that cover: a technical challenge, cross-team collaboration, handling ambiguity, and driving impact.",
        "category": "interviewing",
    },
    {
        "tip": "Research your interviewer on LinkedIn before the call. Mention shared interests or background to build rapport.",
        "category": "interviewing",
    },
    {
        "tip": "Always ask 'What does success look like in this role in the first 90 days?' It shows you're already thinking about contribution.",
        "category": "interviewing",
    },
    {
        "tip": "After each interview, send a thank-you email within 24 hours that references something specific you discussed.",
        "category": "interviewing",
    },
    {
        "tip": "When you don't know an answer, say so honestly, then walk through how you'd approach finding it. Interviewers value intellectual honesty.",
        "category": "interviewing",
    },
    {
        "tip": "Practice your introduction until it's under 90 seconds. Cover: who you are, your strongest relevant experience, and why this role.",
        "category": "interviewing",
    },
    # Mindset
    {
        "tip": "Job searching is a numbers game with skill. Track your conversion rates: applications \u2192 screens \u2192 interviews \u2192 offers.",
        "category": "mindset",
    },
    {
        "tip": "Rejections are data, not verdicts. After each one, note what you'd do differently and move on.",
        "category": "mindset",
    },
    {
        "tip": "Block 2 hours per day for job search activities. Treat it like a meeting \u2014 consistent effort beats sporadic bursts.",
        "category": "mindset",
    },
    {
        "tip": "Celebrate small wins: a response, an interview invite, positive feedback. Job searching is a marathon.",
        "category": "mindset",
    },
    {
        "tip": "Take at least one full day off per week from job searching. Burnout reduces the quality of every interaction.",
        "category": "mindset",
    },
    {
        "tip": "Join communities of other job seekers. Shared experiences reduce isolation and often surface hidden opportunities.",
        "category": "mindset",
    },
    # Strategy
    {
        "tip": "Target 5-10 companies deeply rather than applying to 50 superficially. Warm intros beat cold applications 10:1.",
        "category": "strategy",
    },
    {
        "tip": "Map your network by company before you start searching. You often have more connections than you think.",
        "category": "strategy",
    },
    {
        "tip": "Apply to roles posted within the last 2 weeks. Older listings often have candidates already in pipeline.",
        "category": "strategy",
    },
    {
        "tip": "If a company doesn't have an open role that fits, connect with a team lead anyway. Roles open faster than they're posted.",
        "category": "strategy",
    },
    {
        "tip": "Negotiate salary after you have a written offer, not before. Your leverage is highest when they've committed.",
        "category": "strategy",
    },
    {
        "tip": "Always have at least 2-3 active opportunities in parallel. It reduces desperation and improves your negotiating position.",
        "category": "strategy",
    },
]


def _get_daily_tip(day_of_year: int | None = None) -> dict:
    """Return the tip for the given day (rotates through the list)."""
    if day_of_year is None:
        day_of_year = datetime.now(timezone.utc).timetuple().tm_yday
    idx = day_of_year % len(TIPS)
    tip = TIPS[idx]
    return {
        "tip": tip["tip"],
        "category": tip["category"],
        "day_index": idx,
    }


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


async def get_dashboard_insights(user_id: uuid.UUID, db: AsyncSession) -> dict:
    """Return all three tiers of dashboard insights."""
    # Load user preferences
    result = await db.execute(
        select(UserJobPreferences).where(UserJobPreferences.user_id == user_id)
    )
    prefs = result.scalar_one_or_none()

    # Tier 1: Job market trends (skip if no preferences)
    job_market_trends = None
    if prefs and prefs.target_role:
        try:
            job_market_trends = await _get_job_market_trends(prefs, user_id, db)
        except Exception:
            logger.exception("Failed to get job market trends for user %s", user_id)

    # Tier 2: Network analysis
    network_analysis = None
    try:
        network_analysis = await _get_network_analysis(user_id, db, prefs)
    except Exception:
        logger.exception("Failed to get network analysis for user %s", user_id)

    # Tier 3: Daily tip (always works)
    daily_tip = _get_daily_tip()

    return {
        "job_market_trends": job_market_trends,
        "network_analysis": network_analysis,
        "daily_tip": daily_tip,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
