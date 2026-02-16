"""AI-powered contact matching service.

Uses the Anthropic Claude API to score contacts against search criteria.
When AI_MOCK_MODE=true (default), returns deterministic fake scores so
development and testing work without an API key.
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.contact import Contact
from app.models.enrichment import UsageLog
from app.models.match_result import MatchResult
from app.models.search_request import SearchRequest

logger = logging.getLogger(__name__)

BATCH_SIZE = 50  # contacts per Claude API call
CLAUDE_MODEL = "claude-sonnet-4-20250514"


@dataclass
class ContactMatch:
    contact_id: uuid.UUID
    relevance_score: float
    reasoning: str
    match_type: str  # "direct", "indirect", "weak"


@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int


def _ensu[RESEND_KEY_REDACTED](val: list | str | None) -> list:
    """Convert ARRAY column values that may come back as JSON strings from SQLite."""
    if val is None:
        return []
    if isinstance(val, str):
        return json.loads(val)
    return val


# ---------------------------------------------------------------------------
# Mock AI (deterministic scoring for dev/test)
# ---------------------------------------------------------------------------


def _mock_sco[RESEND_KEY_REDACTED](
    search: SearchRequest,
    contacts: list[Contact],
) -> list[ContactMatch]:
    """Return deterministic mock scores based on simple heuristics."""
    results: list[ContactMatch] = []

    target_titles = [t.lower() for t in _ensu[RESEND_KEY_REDACTED](search.target_titles)]
    target_companies = [c.lower() for c in _ensu[RESEND_KEY_REDACTED](search.target_companies)]
    target_locations = [loc.lower() for loc in _ensu[RESEND_KEY_REDACTED](search.target_locations)]
    target_keywords = [k.lower() for k in _ensu[RESEND_KEY_REDACTED](search.target_keywords)]

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

        match_type = (
            "direct" if score >= 50 else ("indirect" if score >= 20 else "weak")
        )

        results.append(
            ContactMatch(
                contact_id=contact.id,
                relevance_score=round(score, 2),
                reasoning="; ".join(reasons)
                if reasons
                else "No matching criteria found",
                match_type=match_type,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Real Claude API
# ---------------------------------------------------------------------------


def _build_prompt(search: SearchRequest, contacts: list[Contact]) -> str:
    """Build the Claude prompt for a batch of contacts."""
    criteria = []
    titles = _ensu[RESEND_KEY_REDACTED](search.target_titles)
    companies = _ensu[RESEND_KEY_REDACTED](search.target_companies)
    industries = _ensu[RESEND_KEY_REDACTED](search.target_industries)
    locations = _ensu[RESEND_KEY_REDACTED](search.target_locations)
    keywords = _ensu[RESEND_KEY_REDACTED](search.target_keywords)
    if titles:
        criteria.append(f"Target titles: {', '.join(titles)}")
    if companies:
        criteria.append(f"Target companies: {', '.join(companies)}")
    if industries:
        criteria.append(f"Target industries: {', '.join(industries)}")
    if locations:
        criteria.append(f"Target locations: {', '.join(locations)}")
    if keywords:
        criteria.append(f"Keywords: {', '.join(keywords)}")
    if search.description:
        criteria.append(f"Description: {search.description}")

    contacts_data = []
    for c in contacts:
        contacts_data.append(
            {
                "contact_id": str(c.id),
                "name": c.full_name,
                "title": c.current_title,
                "company": c.current_company,
                "location": c.location,
            }
        )

    return f"""You are a sales intelligence assistant. Score each contact for relevance to the following search criteria.

SEARCH CRITERIA:
{chr(10).join(criteria)}

CONTACTS:
{json.dumps(contacts_data, indent=2)}

For each contact, return a JSON array of objects. Only include contacts that score 20 or above. Skip contacts with no meaningful match.

Each object must have:
- "contact_id": the exact contact_id string from the input
- "relevance_score": integer 0-100
- "reasoning": 1-2 sentence explanation of why this contact matches (or doesn't)
- "match_type": one of "direct", "indirect", or "weak"

Scoring guidelines:
- 80-100: Strong direct match — title AND company/industry closely align with criteria
- 50-79: Good indirect match — partial criteria overlap (e.g. right title, wrong industry)
- 20-49: Weak match — tangential connection (e.g. adjacent role or industry)
- Below 20: No meaningful match — omit from results

match_type rules:
- "direct" if relevance_score >= 50
- "indirect" if relevance_score 20-49
- "weak" should be rare; use only for borderline 20-29 cases

Return ONLY the JSON array. No markdown fences, no explanation, no other text."""


async def _call_claude_api(
    search: SearchRequest,
    contacts: list[Contact],
) -> tuple[list[ContactMatch], TokenUsage]:
    """Call the real Claude API. Returns matches and token usage."""
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    prompt = _build_prompt(search, contacts)

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    usage = TokenUsage(
        input_tokens=message.usage.input_tokens,
        output_tokens=message.usage.output_tokens,
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0].strip()

    parsed = json.loads(raw)

    # Build a set of valid contact IDs for this batch
    valid_ids = {str(c.id) for c in contacts}

    results: list[ContactMatch] = []
    for item in parsed:
        cid = item.get("contact_id", "")
        if cid not in valid_ids:
            logger.warning("Claude returned unknown contact_id: %s — skipping", cid)
            continue
        results.append(
            ContactMatch(
                contact_id=uuid.UUID(cid),
                relevance_score=max(0, min(100, float(item["relevance_score"]))),
                reasoning=item.get("reasoning", ""),
                match_type=item.get("match_type", "weak"),
            )
        )

    return results, usage


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def sco[RESEND_KEY_REDACTED](
    search: SearchRequest,
    contacts: list[Contact],
    user_id: uuid.UUID | None = None,
    db: AsyncSession | None = None,
) -> list[ContactMatch]:
    """Score contacts against search criteria.

    Uses mock mode when AI_MOCK_MODE=true, real Claude API otherwise.
    Handles batching internally. Logs token usage when db is provided.
    """
    if settings.AI_MOCK_MODE:
        return _mock_sco[RESEND_KEY_REDACTED](search, contacts)

    all_results: list[ContactMatch] = []
    total_input_tokens = 0
    total_output_tokens = 0

    for i in range(0, len(contacts), BATCH_SIZE):
        batch = contacts[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        try:
            batch_results, usage = await _call_claude_api(search, batch)
            all_results.extend(batch_results)
            total_input_tokens += usage.input_tokens
            total_output_tokens += usage.output_tokens
            logger.info(
                "Batch %d: scored %d contacts, %d matches (tokens: %d in / %d out)",
                batch_num,
                len(batch),
                len(batch_results),
                usage.input_tokens,
                usage.output_tokens,
            )
        except anthropic.APIError as exc:
            logger.error(
                "Claude API error on batch %d (%d contacts): %s — skipping batch",
                batch_num,
                len(batch),
                exc,
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.error(
                "Failed to parse Claude response for batch %d: %s — skipping batch",
                batch_num,
                exc,
            )

    # Log token usage
    if db is not None and user_id is not None and total_input_tokens > 0:
        usage_log = UsageLog(
            user_id=user_id,
            action="ai_match",
            resource_type="search_request",
            resource_id=search.id,
            metadata_={
                "model": CLAUDE_MODEL,
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "total_tokens": total_input_tokens + total_output_tokens,
                "contacts_scored": len(contacts),
                "matches_returned": len(all_results),
                "batches": (len(contacts) + BATCH_SIZE - 1) // BATCH_SIZE,
            },
        )
        db.add(usage_log)

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
    matches = await sco[RESEND_KEY_REDACTED](search, contacts, user_id=user_id, db=db)

    # Upsert match results (skip scores below 20 to keep the database clean)
    MIN_PERSIST_SCORE = 20.0
    model_version = "mock-v1" if settings.AI_MOCK_MODE else CLAUDE_MODEL
    match_results: list[MatchResult] = []
    for m in matches:
        if m.relevance_score < MIN_PERSIST_SCORE:
            continue
        existing_result = await db.execute(
            select(MatchResult).where(
                MatchResult.search_request_id == search_id,
                MatchResult.contact_id == m.contact_id,
            )
        )
        existing = existing_result.scalar_one_or_none()

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
