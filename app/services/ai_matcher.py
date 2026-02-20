"""AI-powered referral matching service.

Uses the Anthropic Claude API to assess referral paths between a user's
contacts and target companies.  When AI_MOCK_MODE=true (default), returns
deterministic scores based on company match, department alignment, and
seniority heuristics — no API key required.
"""

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field

from app.utils.performance import timed
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
from app.models.user import ConnectorProfile, User

logger = logging.getLogger(__name__)

BATCH_SIZE = (
    25  # contacts per Claude API call (keep small to avoid response truncation)
)
MAX_CONCURRENT_BATCHES = 10
CLAUDE_MODEL = settings.CLAUDE_MODEL
CLAUDE_SCORER_MODEL = settings.CLAUDE_SCORER_MODEL


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ContactMatch:
    contact_id: uuid.UUID
    relevance_score: float
    reasoning: str
    match_type: str  # "direct", "adjacent", "senior_advocate", "alumni"
    referral_likelihood: str  # "high", "medium", "low"
    cultural_context: dict = field(default_factory=dict)
    recommended_channel: str = "linkedin_message"
    message_sequence: list[str] = field(default_factory=lambda: ["reconnect", "ask"])


@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int


# ---------------------------------------------------------------------------
# Department / seniority detection (shared patterns)
# ---------------------------------------------------------------------------

_DEPT_KEYWORDS: dict[str, list[str]] = {
    "engineering": [
        "engineer",
        "developer",
        "software",
        "sre",
        "devops",
        "platform",
        "backend",
        "frontend",
        "fullstack",
        "infrastructure",
    ],
    "product": ["product manager", "product lead", "product owner", "pm"],
    "design": ["designer", "ux", "ui", "design lead"],
    "data": [
        "data scientist",
        "data engineer",
        "data analyst",
        "machine learning",
        "ml",
        "analytics",
    ],
    "marketing": ["marketing", "growth", "brand", "content", "communications"],
    "sales": ["sales", "account executive", "ae", "business development", "bdr", "sdr"],
    "finance": ["finance", "accounting", "controller", "treasury", "fp&a"],
    "hr": ["hr", "human resources", "people", "talent", "recruiting", "recruiter"],
    "operations": ["operations", "ops", "logistics", "supply chain"],
    "legal": ["legal", "counsel", "compliance", "attorney"],
}

_ADJACENT_DEPTS: set[tuple[str, str]] = {
    ("engineering", "product"),
    ("product", "engineering"),
    ("engineering", "data"),
    ("data", "engineering"),
    ("product", "design"),
    ("design", "product"),
    ("marketing", "product"),
    ("product", "marketing"),
    ("sales", "marketing"),
    ("marketing", "sales"),
}

_CSUITE_PATTERN = re.compile(
    r"\b(c[eotifsm]o|chief|founder|co-founder|cofounder|president|owner|partner)\b",
    re.IGNORECASE,
)
_VP_PATTERN = re.compile(r"\b(vp|vice\s*president|svp|evp|avp)\b", re.IGNORECASE)
_DIRECTOR_PATTERN = re.compile(r"\b(director)\b", re.IGNORECASE)
_MANAGER_PATTERN = re.compile(
    r"\b(manager|head\s+of|lead|team\s+lead|principal)\b", re.IGNORECASE
)
_SENIOR_PATTERN = re.compile(r"\b(senior|sr\.?|staff)\b", re.IGNORECASE)

# Location keywords for cultural context detection
_ASIA_KEYWORDS = [
    "japan",
    "tokyo",
    "osaka",
    "korea",
    "seoul",
    "china",
    "beijing",
    "shanghai",
    "shenzhen",
    "singapore",
    "hong kong",
    "taipei",
    "taiwan",
    "bangkok",
    "thailand",
    "vietnam",
    "indonesia",
    "jakarta",
    "manila",
    "philippines",
    "malaysia",
    "kuala lumpur",
]
_US_UK_KEYWORDS = [
    "united states",
    "new york",
    "san francisco",
    "los angeles",
    "seattle",
    "austin",
    "boston",
    "chicago",
    "denver",
    "portland",
    "atlanta",
    "united kingdom",
    "london",
    "manchester",
    "edinburgh",
    "toronto",
    "vancouver",
    "canada",
    ", ca",
    ", ny",
    ", wa",
    ", tx",
    ", ma",
    ", il",
    ", co",
]


def _detect_department(title: str) -> str | None:
    """Detect department from a job title."""
    title_lower = title.lower()
    for dept, keywords in _DEPT_KEYWORDS.items():
        if any(kw in title_lower for kw in keywords):
            return dept
    return None


def _ensu[RESEND_KEY_REDACTED](val: list | str | None) -> list:
    """Convert ARRAY column values that may come back as JSON strings from SQLite."""
    if val is None:
        return []
    if isinstance(val, str):
        return json.loads(val)
    return val


# ---------------------------------------------------------------------------
# Cultural context (mock)
# ---------------------------------------------------------------------------


def _mock_cultural_context(location: str, title: str) -> dict:
    """Generate plausible cultural context based on location."""
    loc_lower = (location or "").lower()

    is_asia = any(kw in loc_lower for kw in _ASIA_KEYWORDS)
    is_us_uk = any(kw in loc_lower for kw in _US_UK_KEYWORDS)

    if is_us_uk:
        return {
            "approach_style": "direct",
            "recommended_channel": "linkedin_message",
            "cultural_notes": (
                f"Based in {location}. Direct approach works well. "
                "Lead with your connection and be specific about what you're looking for."
            ),
            "warm_up_suggested": False,
            "message_sequence": ["direct_ask"],
        }
    elif is_asia:
        return {
            "approach_style": "relationship-first",
            "recommended_channel": "linkedin_message",
            "cultural_notes": (
                f"Based in {location}. Consider reconnecting first before making "
                "your ask. Build on shared experience and show genuine interest "
                "in their work."
            ),
            "warm_up_suggested": True,
            "message_sequence": ["reconnect", "explore", "ask"],
        }
    else:
        return {
            "approach_style": "formal-indirect",
            "recommended_channel": "linkedin_message",
            "cultural_notes": (
                f"Based in {location or 'unknown location'}. A professional, "
                "somewhat formal approach is recommended. Reference your shared "
                "connection or experience."
            ),
            "warm_up_suggested": False,
            "message_sequence": ["reconnect", "ask"],
        }


# ---------------------------------------------------------------------------
# Mock AI (deterministic scoring for dev/test)
# ---------------------------------------------------------------------------


@timed("ai_mock_score")
def _mock_sco[RESEND_KEY_REDACTED](
    search: SearchRequest,
    contacts: list[Contact],
    profile: ConnectorProfile | None = None,
) -> list[ContactMatch]:
    """Return deterministic mock scores based on referral heuristics.

    Scoring logic:
    - With target_companies: company match is the primary signal (+50)
      plus department alignment, seniority, and title keyword bonuses.
    - Without target_companies: falls back to title + keyword matching
      (backward-compatible with generic searches).
    """
    results: list[ContactMatch] = []

    target_companies = [c.lower() for c in _ensu[RESEND_KEY_REDACTED](search.target_companies)]
    target_titles = [t.lower() for t in _ensu[RESEND_KEY_REDACTED](search.target_titles)]
    target_keywords = [k.lower() for k in _ensu[RESEND_KEY_REDACTED](search.target_keywords)]
    target_locations = [loc.lower() for loc in _ensu[RESEND_KEY_REDACTED](search.target_locations)]
    target_role = getattr(search, "target_role", None) or ""
    target_dept = _detect_department(target_role) if target_role else None
    has_company_targets = bool(target_companies)

    for contact in contacts:
        score = 0.0
        reasons: list[str] = []
        ct = (contact.current_title or "").lower()
        cc = (contact.current_company or "").lower()
        cl = (contact.location or "").lower()
        contact_dept = _detect_department(ct) if ct else None
        profile_text = f"{ct} {cc} {cl}"

        # Seniority detection
        is_csuite = bool(_CSUITE_PATTERN.search(ct))
        is_vp_dir = bool(_VP_PATTERN.search(ct) or _DIRECTOR_PATTERN.search(ct))
        is_manager = bool(_MANAGER_PATTERN.search(ct)) and not is_vp_dir
        is_senior_ic = bool(_SENIOR_PATTERN.search(ct))

        company_match = False
        same_dept = False
        adjacent_dept = False

        if has_company_targets:
            # --- Referral-focused scoring ---
            company_match = any(tc in cc for tc in target_companies)

            if target_dept and contact_dept:
                same_dept = contact_dept == target_dept
                adjacent_dept = not same_dept and (
                    (contact_dept, target_dept) in _ADJACENT_DEPTS
                )

            if company_match:
                score += 50
                reasons.append("Works at target company")

                if same_dept:
                    score += 25
                    reasons.append(f"Same department ({contact_dept})")
                elif adjacent_dept:
                    score += 15
                    reasons.append(f"Adjacent department ({contact_dept})")
                elif target_dept and contact_dept:
                    # Cross-functional: unrelated department.
                    # C-suite/VP can still refer across depts; others get penalised.
                    if is_csuite or is_vp_dir:
                        reasons.append(
                            f"Different department ({contact_dept}) — senior cross-dept advocate"
                        )
                    else:
                        score -= 20
                        reasons.append(
                            f"Different department ({contact_dept}) — weak referral path"
                        )

                # Seniority bonus
                if is_csuite:
                    score += 5
                    reasons.append("C-suite — senior advocate")
                elif is_vp_dir or is_manager:
                    score += 10
                    reasons.append("Senior enough to personally refer")
                elif is_senior_ic:
                    score += 5
                    reasons.append("Experienced IC")

                # Title keyword match
                for title in target_titles:
                    if title in ct:
                        score += 10
                        reasons.append(f"Title matches '{title}'")
                        break
            else:
                # No company match — very limited score
                for title in target_titles:
                    if title in ct:
                        score += 10
                        reasons.append(
                            f"Title matches '{title}' (not at target company)"
                        )
                        break

                for kw in target_keywords:
                    if kw in profile_text:
                        score += 5
                        reasons.append(f"Profile keyword '{kw}'")
                        break
        else:
            # --- No company filter — legacy/generic mode ---
            for title in target_titles:
                if title in ct:
                    score += 40
                    reasons.append(f"Title matches '{title}'")
                    break

            for kw in target_keywords:
                if kw in profile_text:
                    score += 15
                    reasons.append(f"Keyword '{kw}'")
                    break

            for loc in target_locations:
                if loc in cl:
                    score += 10
                    reasons.append(f"Location '{loc}'")
                    break

        score = min(score, 100.0)
        if score == 0:
            score = 5.0
            reasons.append("No direct referral path found")

        # Match type
        if company_match and same_dept:
            match_type = "direct"
        elif company_match and adjacent_dept:
            match_type = "adjacent"
        elif company_match and (is_vp_dir or is_manager or is_csuite):
            match_type = "senior_advocate"
        elif company_match:
            match_type = "direct"  # at target company, no dept detection
        elif score >= 50:
            match_type = "direct"
        elif score >= 30:
            match_type = "adjacent"
        else:
            match_type = "alumni"

        # Referral likelihood
        if score >= 70:
            referral_likelihood = "high"
        elif score >= 45:
            referral_likelihood = "medium"
        else:
            referral_likelihood = "low"

        # Cultural context
        cultural_ctx = _mock_cultural_context(cl, ct)

        results.append(
            ContactMatch(
                contact_id=contact.id,
                relevance_score=round(score, 2),
                reasoning="; ".join(reasons) if reasons else "No matching criteria",
                match_type=match_type,
                referral_likelihood=referral_likelihood,
                cultural_context=cultural_ctx,
                recommended_channel=cultural_ctx["recommended_channel"],
                message_sequence=cultural_ctx["message_sequence"],
            )
        )

    return results


# ---------------------------------------------------------------------------
# Real Claude API
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """Score each contact's referral potential for the user's target role. Return a JSON array. Only include contacts scoring 20+.

Each object: {"contact_id":"<exact id>","relevance_score":<0-100>,"referral_likelihood":"high|medium|low","match_type":"direct|adjacent|senior_advocate|alumni","recommended_channel":"linkedin_message|email|whatsapp"}

Scoring: 90-100=same company+dept, 70-89=same company adjacent dept, 50-69=same company weak path, 20-49=former employee or industry peer, <20=omit.
Match types: direct=same dept, adjacent=related dept, senior_advocate=senior enough to refer anywhere, alumni=former employee.

Return ONLY the JSON array."""


def _build_user_prompt(
    search: SearchRequest,
    contacts: list[Contact],
    profile: ConnectorProfile | None,
    user_name: str | None = None,
) -> str:
    """Build the user prompt with profile, target, and contact data."""
    # User profile section
    profile_parts: list[str] = []
    if user_name:
        profile_parts.append(f"Name: {user_name}")
    if profile:
        if profile.current_title:
            profile_parts.append(f"Title: {profile.current_title}")
        if profile.current_company:
            profile_parts.append(f"Company: {profile.current_company}")
        if profile.industry:
            profile_parts.append(f"Industry: {profile.industry}")
        if profile.location:
            profile_parts.append(f"Location: {profile.location}")
        if profile.bio_summary:
            profile_parts.append(f"Bio: {profile.bio_summary}")
    profile_info = "\n".join(profile_parts) if profile_parts else "No profile set"

    # Target section
    target_companies = _ensu[RESEND_KEY_REDACTED](search.target_companies)
    target_role = getattr(search, "target_role", None) or "General"
    target_seniority = getattr(search, "target_seniority", None) or "Any"

    # Contact data — keep lean for fast scoring
    contacts_data = []
    for c in contacts:
        entry: dict = {
            "contact_id": str(c.id),
            "name": c.full_name,
            "title": c.current_title,
            "company": c.current_company,
        }
        contacts_data.append(entry)

    return f"""USER PROFILE:
{profile_info}

TARGET:
Company: {", ".join(target_companies) if target_companies else "Any"}
Role: {target_role}
Seniority: {target_seniority}

CONTACTS:
{json.dumps(contacts_data, indent=2)}"""


def _repair_truncated_json(raw: str) -> list[dict] | None:
    """Attempt to recover a valid JSON array from a truncated Claude response.

    Strategy: find the last complete object in the array by progressively
    trimming from the end until json.loads succeeds.
    """
    # Only attempt repair on array-like responses
    if not raw.lstrip().startswith("["):
        return None

    # Find the last complete }, then close the array
    for i in range(len(raw) - 1, 0, -1):
        if raw[i] == "}":
            candidate = raw[: i + 1] + "]"
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, list) and parsed:
                    logger.warning(
                        "Repaired truncated JSON: recovered %d items", len(parsed)
                    )
                    return parsed
            except json.JSONDecodeError:
                continue
    return None


@timed("ai_call_claude")
async def _call_claude_api(
    search: SearchRequest,
    contacts: list[Contact],
    profile: ConnectorProfile | None = None,
    user_name: str | None = None,
) -> tuple[list[ContactMatch], TokenUsage]:
    """Call the real Claude API with the referral-focused prompt.

    Retries once on rate limit (429) with exponential backoff.
    Falls back to mock scoring on persistent API failures.
    """
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    user_prompt = _build_user_prompt(search, contacts, profile, user_name)

    max_retries = 2
    for attempt in range(max_retries):
        try:
            message = await client.messages.create(
                model=CLAUDE_SCORER_MODEL,
                max_tokens=8192,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            break
        except anthropic.RateLimitError:
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                logger.warning("Claude rate limit hit, retrying in %ds...", wait)
                await asyncio.sleep(wait)
            else:
                logger.error(
                    "Claude rate limit persists after retries, falling back to mock"
                )
                return _mock_sco[RESEND_KEY_REDACTED](search, contacts), TokenUsage(0, 0)
        except anthropic.APIError as exc:
            logger.error("Claude API error: %s — falling back to mock scoring", exc)
            return _mock_sco[RESEND_KEY_REDACTED](search, contacts), TokenUsage(0, 0)

    usage = TokenUsage(
        input_tokens=message.usage.input_tokens,
        output_tokens=message.usage.output_tokens,
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0].strip()

    # Try parsing JSON, repairing truncated responses if needed
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = _repair_truncated_json(raw)
        if parsed is None:
            logger.error(
                "Claude response not valid JSON even after repair (len=%d, tail=%r)",
                len(raw),
                raw[-100:] if raw else "",
            )
            return _mock_sco[RESEND_KEY_REDACTED](search, contacts), TokenUsage(
                message.usage.input_tokens, message.usage.output_tokens
            )
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
                match_type=item.get("match_type", "alumni"),
                referral_likelihood=item.get("referral_likelihood", "low"),
                cultural_context={},
                recommended_channel=item.get("recommended_channel", "linkedin_message"),
                message_sequence=["reconnect", "ask"],
            )
        )

    return results, usage


# ---------------------------------------------------------------------------
# Pre-filter (cheap local filter before sending to the API)
# ---------------------------------------------------------------------------

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
    """Extract meaningful terms from a description string."""
    if not description:
        return []
    stop_words = {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "need",
        "must",
        "that",
        "this",
        "these",
        "those",
        "i",
        "we",
        "you",
        "they",
        "it",
        "who",
        "what",
        "which",
        "where",
        "when",
        "how",
        "not",
        "no",
        "nor",
        "as",
        "if",
        "then",
        "than",
        "too",
        "very",
        "just",
        "about",
        "above",
        "after",
        "before",
        "between",
        "into",
        "through",
        "during",
        "each",
        "level",
        "looking",
        "find",
        "search",
        "want",
        "like",
    }
    words = description.lower().split()
    return [
        w.strip(".,;:!?()\"'")
        for w in words
        if len(w) > 2 and w.lower().strip(".,;:!?()\"'") not in stop_words
    ]


def _p[RESEND_KEY_REDACTED](
    search: SearchRequest,
    contacts: list[Contact],
) -> list[Contact]:
    """Filter contacts locally before sending to the Claude API."""
    total = len(contacts)

    title_terms = _expand_title_synonyms(_ensu[RESEND_KEY_REDACTED](search.target_titles))
    company_terms = [t.lower() for t in _ensu[RESEND_KEY_REDACTED](search.target_companies)]
    industry_terms = [t.lower() for t in _ensu[RESEND_KEY_REDACTED](search.target_industries)]
    keyword_terms = [t.lower() for t in _ensu[RESEND_KEY_REDACTED](search.target_keywords)]
    desc_terms = _extract_description_terms(search.description)

    # Include target_role terms for pre-filtering
    target_role = getattr(search, "target_role", None) or ""
    role_terms = [t.lower() for t in target_role.split() if len(t) > 2]

    all_terms = (
        title_terms
        + company_terms
        + industry_terms
        + keyword_terms
        + desc_terms
        + role_terms
    )
    if not all_terms:
        logger.info(
            "Pre-filter: no search terms to filter on, sending all %d contacts", total
        )
        return contacts

    filtered = []
    for c in contacts:
        ct = (c.current_title or "").lower()
        cc = (c.current_company or "").lower()
        ci = ""
        if c.company and c.company.industry:
            ci = c.company.industry.lower()

        searchable = f"{ct} {cc} {ci}"

        if any(term in searchable for term in all_terms):
            filtered.append(c)

    logger.info(
        "Pre-filter: %d total, %d passed, %d skipped",
        total,
        len(filtered),
        total - len(filtered),
    )
    return filtered if filtered else contacts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@timed("ai_sco[RESEND_KEY_REDACTED]")
async def sco[RESEND_KEY_REDACTED](
    search: SearchRequest,
    contacts: list[Contact],
    profile: ConnectorProfile | None = None,
    user_name: str | None = None,
    user_id: uuid.UUID | None = None,
    db: AsyncSession | None = None,
) -> list[ContactMatch]:
    """Score contacts against search criteria for referral potential.

    Uses mock mode when AI_MOCK_MODE=true, real Claude API otherwise.
    """
    if settings.AI_MOCK_MODE:
        return _mock_sco[RESEND_KEY_REDACTED](search, contacts, profile)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_BATCHES)
    batches = [
        contacts[i : i + BATCH_SIZE] for i in range(0, len(contacts), BATCH_SIZE)
    ]
    num_batches = len(batches)
    logger.info(
        "Scoring %d contacts in %d batches (concurrency: %d)",
        len(contacts),
        num_batches,
        MAX_CONCURRENT_BATCHES,
    )

    async def _process_batch(
        batch_num: int, batch: list[Contact]
    ) -> tuple[list[ContactMatch], int, int]:
        async with semaphore:
            try:
                batch_results, usage = await _call_claude_api(
                    search, batch, profile, user_name
                )
                logger.info(
                    "Batch %d/%d: scored %d contacts, %d matches "
                    "(tokens: %d in / %d out)",
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
                    "Claude API error on batch %d (%d contacts): %s — skipping",
                    batch_num,
                    len(batch),
                    exc,
                )
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.error(
                    "Failed to parse Claude response for batch %d: %s — skipping",
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
                "model": CLAUDE_SCORER_MODEL,
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


async def _upsert_match_results(
    search_id: uuid.UUID,
    user_id: uuid.UUID,
    matches: list[ContactMatch],
    model_version: str,
    db: AsyncSession,
) -> list[MatchResult]:
    """Persist or update MatchResult rows for scored contacts (score >= 20)."""
    MIN_PERSIST_SCORE = 20.0
    filtered_matches = [m for m in matches if m.relevance_score >= MIN_PERSIST_SCORE]

    # Batch-load existing match results for upsert (avoids N+1)
    existing_map: dict = {}
    if filtered_matches:
        contact_ids = [m.contact_id for m in filtered_matches]
        er = await db.execute(
            select(MatchResult).where(
                MatchResult.search_request_id == search_id,
                MatchResult.contact_id.in_(contact_ids),
            )
        )
        existing_map = {mr.contact_id: mr for mr in er.scalars()}

    match_results: list[MatchResult] = []
    for m in filtered_matches:
        ctx_blob = {
            **m.cultural_context,
            "referral_likelihood": m.referral_likelihood,
            "recommended_channel": m.recommended_channel,
            "message_sequence": m.message_sequence,
        }

        existing = existing_map.get(m.contact_id)
        if existing:
            existing.relevance_score = Decimal(str(m.relevance_score))
            existing.match_reasoning = m.reasoning
            existing.match_type = m.match_type
            existing.ai_model_version = model_version
            existing.cultural_context = ctx_blob
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
                cultural_context=ctx_blob,
            )
            db.add(mr)
            match_results.append(mr)

    return match_results


@timed("ai_match")
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

    # Load user and connector profile for the referral prompt
    user = await db.get(User, user_id)
    profile_result = await db.execute(
        select(ConnectorProfile).where(ConnectorProfile.user_id == user_id)
    )
    profile = profile_result.scalar_one_or_none()
    user_name = user.full_name if user else None

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

    # Pre-filter: only send contacts with relevant overlap to the API
    total_contacts = len(contacts)
    if not settings.AI_MOCK_MODE:
        contacts = _p[RESEND_KEY_REDACTED](search, contacts)

    # Score contacts via AI (mock or real)
    matches = await sco[RESEND_KEY_REDACTED](
        search,
        contacts,
        profile=profile,
        user_name=user_name,
        user_id=user_id,
        db=db,
    )

    # Upsert match results (skip scores below 20)
    model_version = "mock-v2-referral" if settings.AI_MOCK_MODE else CLAUDE_MODEL
    match_results = await _upsert_match_results(
        search_id, user_id, matches, model_version, db
    )

    search.last_run_at = datetime.now(timezone.utc)
    search.status = "completed"

    elapsed = time.monotonic() - t0
    logger.info(
        "Search complete in %.1fs: %d total contacts, %d sent to scorer, "
        "%d returned score >= 20, %d persisted",
        elapsed,
        total_contacts,
        len(contacts),
        len(matches),
        len(match_results),
    )

    await db.flush()
    return match_results
