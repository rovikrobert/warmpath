"""AI-powered contact matching service.

Uses the Anthropic Claude API to score contacts against search criteria.
When AI_MOCK_MODE=true (default), returns deterministic fake scores so
development and testing work without an API key.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.contact import Contact
from app.models.match_result import MatchResult, WarmScore
from app.models.search_request import SearchRequest


BATCH_SIZE = 50  # contacts per Claude API call


@dataclass
class ContactMatch:
    contact_id: uuid.UUID
    relevance_score: float
    reasoning: str
    match_type: str  # "direct", "indirect", "weak"


# ---------------------------------------------------------------------------
# Mock AI (deterministic scoring for dev/test)
# ---------------------------------------------------------------------------

def _mock_score_contacts(
    search: SearchRequest,
    contacts: list[Contact],
) -> list[ContactMatch]:
    """Return deterministic mock scores based on simple heuristics."""
    results: list[ContactMatch] = []

    target_titles = [t.lower() for t in (search.target_titles or [])]
    target_companies = [c.lower() for c in (search.target_companies or [])]
    target_locations = [loc.lower() for loc in (search.target_locations or [])]
    target_keywords = [k.lower() for k in (search.target_keywords or [])]

    for contact in contacts:
        score = 0.0
        reasons: list[str] = []
        ct = (contact.current_title or "").lower()
        cc = (contact.current_company or "").lower()
        cl = (contact.location or "").lower()

        # Title match (+40)
        for title in target_titles:
            if title in ct:
                score += 40
                reasons.append(f"Title matches '{title}'")
                break

        # Company match (+30)
        for company in target_companies:
            if company in cc:
                score += 30
                reasons.append(f"Works at target company '{company}'")
                break

        # Location match (+15)
        for loc in target_locations:
            if loc in cl:
                score += 15
                reasons.append(f"Located in '{loc}'")
                break

        # Keyword match (+15)
        profile_text = f"{ct} {cc} {cl}".lower()
        for kw in target_keywords:
            if kw in profile_text:
                score += 15
                reasons.append(f"Profile contains keyword '{kw}'")
                break

        score = min(score, 100.0)

        if score == 0:
            score = 5.0
            reasons.append("No direct criteria match")

        match_type = "direct" if score >= 50 else ("indirect" if score >= 20 else "weak")

        results.append(ContactMatch(
            contact_id=contact.id,
            relevance_score=round(score, 2),
            reasoning="; ".join(reasons) if reasons else "No matching criteria found",
            match_type=match_type,
        ))

    return results


# ---------------------------------------------------------------------------
# Real Claude API (will be activated when API key is configured)
# ---------------------------------------------------------------------------

def _build_prompt(search: SearchRequest, contacts: list[Contact]) -> str:
    """Build the Claude prompt for a batch of contacts."""
    criteria = []
    if search.target_titles:
        criteria.append(f"Target titles: {', '.join(search.target_titles)}")
    if search.target_companies:
        criteria.append(f"Target companies: {', '.join(search.target_companies)}")
    if search.target_industries:
        criteria.append(f"Target industries: {', '.join(search.target_industries)}")
    if search.target_locations:
        criteria.append(f"Target locations: {', '.join(search.target_locations)}")
    if search.target_keywords:
        criteria.append(f"Keywords: {', '.join(search.target_keywords)}")
    if search.description:
        criteria.append(f"Description: {search.description}")

    contacts_data = []
    for c in contacts:
        contacts_data.append({
            "contact_id": str(c.id),
            "name": c.full_name,
            "title": c.current_title,
            "company": c.current_company,
            "location": c.location,
        })

    return f"""You are a sales intelligence assistant. Score each contact for relevance to the following search criteria.

SEARCH CRITERIA:
{chr(10).join(criteria)}

CONTACTS:
{json.dumps(contacts_data, indent=2)}

For each contact, return a JSON array with objects like:
[{{"contact_id": "...", "relevance_score": 85, "reasoning": "VP of Eng at a Series B fintech...", "match_type": "direct"}}]

Scoring guidelines:
- 80-100: Strong direct match (title + company/industry align)
- 50-79: Good indirect match (partial criteria overlap)
- 20-49: Weak match (tangential connection)
- 0-19: No meaningful match

match_type should be: "direct", "indirect", or "weak"

Return ONLY the JSON array, no other text."""


async def _call_claude_api(
    search: SearchRequest,
    contacts: list[Contact],
) -> list[ContactMatch]:
    """Call the real Claude API. Requires ANTHROPIC_API_KEY to be set."""
    import anthropic

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    prompt = _build_prompt(search, contacts)

    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0]

    parsed = json.loads(raw)

    results: list[ContactMatch] = []
    for item in parsed:
        results.append(ContactMatch(
            contact_id=uuid.UUID(item["contact_id"]),
            relevance_score=float(item["relevance_score"]),
            reasoning=item.get("reasoning", ""),
            match_type=item.get("match_type", "weak"),
        ))

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def score_contacts(
    search: SearchRequest,
    contacts: list[Contact],
) -> list[ContactMatch]:
    """Score contacts against search criteria.

    Uses mock mode when AI_MOCK_MODE=true, real Claude API otherwise.
    Handles batching internally.
    """
    if settings.AI_MOCK_MODE:
        return _mock_score_contacts(search, contacts)

    all_results: list[ContactMatch] = []
    for i in range(0, len(contacts), BATCH_SIZE):
        batch = contacts[i : i + BATCH_SIZE]
        batch_results = await _call_claude_api(search, batch)
        all_results.extend(batch_results)

    return all_results


async def run_search(
    search_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[MatchResult]:
    """Execute a search: load contacts, score them, persist MatchResult rows."""
    result = await db.execute(
        select(SearchRequest).where(
            SearchRequest.id == search_id,
            SearchRequest.user_id == user_id,
            SearchRequest.deleted_at.is_(None),
        )
    )
    search = result.scalar_one_or_none()
    if search is None:
        raise ValueError("Search request not found")

    # Load user's active contacts
    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.deleted_at.is_(None),
        )
    )
    contacts = list(result.scalars().all())

    if not contacts:
        search.last_run_at = datetime.now(timezone.utc)
        await db.flush()
        return []

    # Score contacts via AI (mock or real)
    matches = await score_contacts(search, contacts)

    # Upsert match results
    match_results: list[MatchResult] = []
    for m in matches:
        existing_result = await db.execute(
            select(MatchResult).where(
                MatchResult.search_request_id == search_id,
                MatchResult.contact_id == m.contact_id,
            )
        )
        existing = existing_result.scalar_one_or_none()

        model_version = "mock-v1" if settings.AI_MOCK_MODE else "claude-sonnet-4-5"

        if existing:
            existing.relevance_score = Decimal(str(m.relevance_score))
            existing.match_reasoning = m.reasoning
            existing.match_type = m.match_type
            existing.ai_model_version = model_version
            match_results.append(existing)
        else:
            mr = MatchResult(
                search_request_id=search_id,
                contact_id=m.contact_id,
                user_id=user_id,
                relevance_score=Decimal(str(m.relevance_score)),
                match_reasoning=m.reasoning,
                match_type=m.match_type,
                ai_model_version=model_version,
            )
            db.add(mr)
            match_results.append(mr)

    search.last_run_at = datetime.now(timezone.utc)
    search.status = "completed"

    await db.flush()
    return match_results
