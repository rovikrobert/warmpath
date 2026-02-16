"""AI-powered contact matching service.

Uses the Anthropic Claude API to score contacts against search criteria.
When AI_MOCK_MODE=true (default), returns deterministic fake scores so
development and testing work without an API key.
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.contact import Contact
from app.models.enrichment import UsageLog
from app.models.match_result import MatchResult
from app.models.search_request import SearchRequest

logger = logging.getLogger(__name__)

BATCH_SIZE = 100  # contacts per Claude API call
MAX_CONCURRENT_BATCHES = 10  # max batches in flight at once
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


def _ensure_list(val: list | str | None) -> list:
    """Convert ARRAY column values that may come back as JSON strings from SQLite."""
    if val is None:
        return []
    if isinstance(val, str):
        return json.loads(val)
    return val


# ---------------------------------------------------------------------------
# Mock AI (deterministic scoring for dev/test)
# ---------------------------------------------------------------------------


def _mock_score_contacts(
    search: SearchRequest,
    contacts: list[Contact],
) -> list[ContactMatch]:
    """Return deterministic mock scores based on simple heuristics."""
    results: list[ContactMatch] = []

    target_titles = [t.lower() for t in _ensure_list(search.target_titles)]
    target_companies = [c.lower() for c in _ensure_list(search.target_companies)]
    target_locations = [loc.lower() for loc in _ensure_list(search.target_locations)]
    target_keywords = [k.lower() for k in _ensure_list(search.target_keywords)]

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
    titles = _ensure_list(search.target_titles)
    companies = _ensure_list(search.target_companies)
    industries = _ensure_list(search.target_industries)
    locations = _ensure_list(search.target_locations)
    keywords = _ensure_list(search.target_keywords)
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

Scoring guidelines (be strict — differentiate aggressively):
- 90-100: ALL criteria match — right title level AND right company/industry AND right location. Reserve this tier for truly perfect fits.
- 70-89: 2 out of 3 criteria match (e.g. right title + right industry, but wrong location)
- 50-69: 1 criterion matches strongly (e.g. exact title match but unrelated company/industry)
- 20-49: Tangential match — adjacent role, loosely related industry, or only keyword overlap
- Below 20: No meaningful match — omit from results

IMPORTANT: Spread your scores across the full range. If most contacts score similarly, you're not being selective enough. A VP at a non-tech company should NOT score the same as a VP at a target enterprise SaaS company.

match_type rules:
- "direct" if relevance_score >= 70
- "indirect" if relevance_score 50-69
- "weak" if relevance_score 20-49

Return ONLY the JSON array. No markdown fences, no explanation, no other text."""


async def _call_claude_api(
    search: SearchRequest,
    contacts: list[Contact],
) -> tuple[list[ContactMatch], TokenUsage]:
    """Call the real Claude API. Returns matches and token usage."""
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    prompt = _build_prompt(search, contacts)

    message = await client.messages.create(
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
# Pre-filter (cheap local filter before sending to the API)
# ---------------------------------------------------------------------------

# Common title synonyms — if search mentions one, also match the others
_TITLE_SYNONYMS: list[set[str]] = [
    {"vp", "vice president"},
    {"head of", "director"},
    {"ceo", "chief executive officer"},
    {"cto", "chief technology officer"},
    {"cfo", "chief financial officer"},
    {"coo", "chief operating officer"},
    {"cmo", "chief marketing officer"},
    {"svp", "senior vice president"},
    {"evp", "executive vice president"},
    {"avp", "assistant vice president"},
    {"md", "managing director"},
    {"gm", "general manager"},
]


def _expand_title_synonyms(titles: list[str]) -> list[str]:
    """Expand title terms with known synonyms."""
    expanded = set(t.lower() for t in titles)
    for term in list(expanded):
        for syn_group in _TITLE_SYNONYMS:
            if term in syn_group:
                expanded.update(syn_group)
    return list(expanded)


def _extract_description_terms(description: str | None) -> list[str]:
    """Extract meaningful terms from the search description."""
    if not description:
        return []
    stop_words = {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "shall", "can", "need", "must",
        "that", "this", "these", "those", "i", "we", "you", "they", "it",
        "who", "what", "which", "where", "when", "how", "not", "no", "nor",
        "as", "if", "then", "than", "too", "very", "just", "about", "above",
        "after", "before", "between", "into", "through", "during", "each",
        "level", "looking", "find", "search", "want", "like",
    }
    words = description.lower().split()
    return [w.strip(".,;:!?()\"'") for w in words if len(w) > 2 and w.lower().strip(".,;:!?()\"'") not in stop_words]


def _pre_filter_contacts(
    search: SearchRequest,
    contacts: list[Contact],
) -> list[Contact]:
    """Filter contacts locally before sending to the Claude API."""
    total = len(contacts)

    # Build search terms from all criteria
    title_terms = _expand_title_synonyms(_ensure_list(search.target_titles))
    company_terms = [t.lower() for t in _ensure_list(search.target_companies)]
    industry_terms = [t.lower() for t in _ensure_list(search.target_industries)]
    keyword_terms = [t.lower() for t in _ensure_list(search.target_keywords)]
    desc_terms = _extract_description_terms(search.description)

    all_terms = title_terms + company_terms + industry_terms + keyword_terms + desc_terms
    if not all_terms:
        logger.info("Pre-filter: no search terms to filter on, sending all %d contacts", total)
        return contacts

    filtered = []
    for c in contacts:
        ct = (c.current_title or "").lower()
        cc = (c.current_company or "").lower()
        # Industry from linked company record
        ci = ""
        if c.company and c.company.industry:
            ci = c.company.industry.lower()

        searchable = f"{ct} {cc} {ci}"

        if any(term in searchable for term in all_terms):
            filtered.append(c)

    logger.info(
        "Pre-filter: %d total contacts, %d passed filter, %d skipped, sending %d to API",
        total,
        len(filtered),
        total - len(filtered),
        len(filtered) if filtered else total,
    )
    return filtered if filtered else contacts  # fallback to all if none match


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def score_contacts(
    search: SearchRequest,
    contacts: list[Contact],
    user_id: uuid.UUID | None = None,
    db: AsyncSession | None = None,
) -> list[ContactMatch]:
    """Score contacts against search criteria.

    Uses mock mode when AI_MOCK_MODE=true, real Claude API otherwise.
    Handles batching internally with concurrent API calls.
    Logs token usage when db is provided.
    """
    if settings.AI_MOCK_MODE:
        return _mock_score_contacts(search, contacts)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_BATCHES)
    batches = [
        contacts[i : i + BATCH_SIZE]
        for i in range(0, len(contacts), BATCH_SIZE)
    ]
    num_batches = len(batches)
    logger.info("Scoring %d contacts in %d batches (concurrency: %d)", len(contacts), num_batches, MAX_CONCURRENT_BATCHES)

    async def _process_batch(
        batch_num: int, batch: list[Contact]
    ) -> tuple[list[ContactMatch], int, int]:
        async with semaphore:
            try:
                batch_results, usage = await _call_claude_api(search, batch)
                logger.info(
                    "Batch %d/%d: scored %d contacts, %d matches (tokens: %d in / %d out)",
                    batch_num,
                    num_batches,
                    len(batch),
                    len(batch_results),
                    usage.input_tokens,
                    usage.output_tokens,
                )
                return batch_results, usage.input_tokens, usage.output_tokens
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
            return [], 0, 0

    results = await asyncio.gather(
        *(_process_batch(i + 1, batch) for i, batch in enumerate(batches))
    )

    all_results: list[ContactMatch] = []
    total_input_tokens = 0
    total_output_tokens = 0
    for batch_results, in_tokens, out_tokens in results:
        all_results.extend(batch_results)
        total_input_tokens += in_tokens
        total_output_tokens += out_tokens

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
                "batches": num_batches,
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
    t0 = time.monotonic()
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

    # Load user's active contacts (eagerly load company for industry filtering)
    result = await db.execute(
        select(Contact)
        .options(selectinload(Contact.company))
        .where(
            Contact.user_id == user_id,
            Contact.deleted_at.is_(None),
        )
    )
    contacts = list(result.scalars().all())

    if not contacts:
        search.last_run_at = datetime.now(timezone.utc)
        await db.flush()
        return []

    # Pre-filter: only send contacts with title/company/industry overlap to the API
    total_contacts = len(contacts)
    if not settings.AI_MOCK_MODE:
        contacts = _pre_filter_contacts(search, contacts)

    # Score contacts via AI (mock or real)
    matches = await score_contacts(search, contacts, user_id=user_id, db=db)

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

    elapsed = time.monotonic() - t0
    logger.info(
        "Search complete in %.1fs: %d total contacts, %d sent to API, %d returned score >= 20, %d persisted",
        elapsed,
        total_contacts,
        len(contacts),
        len(matches),
        len(match_results),
    )

    await db.flush()
    return match_results
