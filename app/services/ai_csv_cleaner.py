"""AI-powered CSV data cleanup service.

Runs AFTER csv_parser to clean messy data from LinkedIn CSV exports.

Mock mode: deterministic heuristics, no API calls.
Real mode: Claude API for fuzzy name/company resolution.

Follows the same mock/real pattern as ai_matcher.py.
"""

import asyncio
import json
import logging
import re

import anthropic

from app.config import settings
from app.services.csv_parser import generate_fingerprint
from app.utils.performance import timed

logger = logging.getLogger(__name__)

CLEANUP_MODEL = getattr(settings, "CLEANUP_MODEL", "claude-haiku-4-5-20251001")
CLEANUP_BATCH_SIZE = 200

# ---------------------------------------------------------------------------
# System prompt for Claude cleanup
# ---------------------------------------------------------------------------

_CLEANUP_SYSTEM_PROMPT = """You are a data-cleaning assistant for LinkedIn contact records.

For each contact in the input JSON array, clean and normalize these fields:
- first_name: Fix capitalization (title case). If it contains a full name and last_name is empty, split it.
- last_name: Fix capitalization (title case).
- current_company: Normalize to the well-known canonical form (e.g. "GOOGLE LLC" -> "Google", "Meta Platforms, Inc." -> "Meta", "microsoft corp" -> "Microsoft"). For lesser-known companies, just fix capitalization and remove redundant suffixes like "Inc", "LLC", "Ltd", "Corp".
- current_title: Clean up abbreviations and fix capitalization. E.g. "sr. swe" -> "Senior Software Engineer", "PM" -> "Product Manager", "eng" -> "Engineer". Keep it professional and standardized.

Return a JSON array with one object per input contact. Each object must have exactly these keys:
- "first_name"
- "last_name"
- "current_company"
- "current_title"

Preserve the input array order (index 0 in input corresponds to index 0 in output).

Return ONLY the JSON array. No markdown fences, no explanation."""

# ---------------------------------------------------------------------------
# Well-known company normalization
# ---------------------------------------------------------------------------

# Maps lowercase canonical form -> display name.
# Input is matched after lowercasing and stripping common suffixes.
_COMPANY_CANONICAL: dict[str, str] = {
    "google": "Google",
    "meta": "Meta",
    "facebook": "Meta",
    "apple": "Apple",
    "amazon": "Amazon",
    "microsoft": "Microsoft",
    "netflix": "Netflix",
    "stripe": "Stripe",
    "shopify": "Shopify",
    "salesforce": "Salesforce",
    "uber": "Uber",
    "lyft": "Lyft",
    "airbnb": "Airbnb",
    "twitter": "Twitter",
    "x": "X",
    "snap": "Snap",
    "snapchat": "Snap",
    "linkedin": "LinkedIn",
    "oracle": "Oracle",
    "ibm": "IBM",
    "intel": "Intel",
    "nvidia": "NVIDIA",
    "tesla": "Tesla",
    "spotify": "Spotify",
    "tiktok": "TikTok",
    "bytedance": "ByteDance",
    "palantir": "Palantir",
    "databricks": "Databricks",
    "snowflake": "Snowflake",
    "coinbase": "Coinbase",
    "robinhood": "Robinhood",
    "figma": "Figma",
    "notion": "Notion",
    "slack": "Slack",
    "zoom": "Zoom",
    "dropbox": "Dropbox",
    "twilio": "Twilio",
    "datadog": "Datadog",
    "cloudflare": "Cloudflare",
    "mongodb": "MongoDB",
    "elastic": "Elastic",
    "github": "GitHub",
    "gitlab": "GitLab",
    "atlassian": "Atlassian",
    "adobe": "Adobe",
    "vmware": "VMware",
    "dell": "Dell",
    "cisco": "Cisco",
    "samsung": "Samsung",
    "sony": "Sony",
    "grab": "Grab",
    "sea": "Sea",
    "gojek": "Gojek",
    "lazada": "Lazada",
    "dbs": "DBS",
    "ocbc": "OCBC",
    "uob": "UOB",
}

# Maps email domain -> canonical company name (for inferring company from email).
_EMAIL_DOMAIN_TO_COMPANY: dict[str, str] = {
    "google.com": "Google",
    "meta.com": "Meta",
    "facebook.com": "Meta",
    "apple.com": "Apple",
    "amazon.com": "Amazon",
    "microsoft.com": "Microsoft",
    "netflix.com": "Netflix",
    "stripe.com": "Stripe",
    "shopify.com": "Shopify",
    "salesforce.com": "Salesforce",
    "uber.com": "Uber",
    "lyft.com": "Lyft",
    "airbnb.com": "Airbnb",
    "twitter.com": "Twitter",
    "x.com": "X",
    "linkedin.com": "LinkedIn",
    "oracle.com": "Oracle",
    "ibm.com": "IBM",
    "intel.com": "Intel",
    "nvidia.com": "NVIDIA",
    "tesla.com": "Tesla",
    "spotify.com": "Spotify",
    "tiktok.com": "TikTok",
    "bytedance.com": "ByteDance",
    "palantir.com": "Palantir",
    "databricks.com": "Databricks",
    "snowflake.com": "Snowflake",
    "coinbase.com": "Coinbase",
    "robinhood.com": "Robinhood",
    "figma.com": "Figma",
    "notion.so": "Notion",
    "slack.com": "Slack",
    "zoom.us": "Zoom",
    "dropbox.com": "Dropbox",
    "twilio.com": "Twilio",
    "datadoghq.com": "Datadog",
    "cloudflare.com": "Cloudflare",
    "mongodb.com": "MongoDB",
    "elastic.co": "Elastic",
    "github.com": "GitHub",
    "gitlab.com": "GitLab",
    "atlassian.com": "Atlassian",
    "adobe.com": "Adobe",
    "vmware.com": "VMware",
    "dell.com": "Dell",
    "cisco.com": "Cisco",
    "samsung.com": "Samsung",
    "sony.com": "Sony",
    "grab.com": "Grab",
    "sea.com": "Sea",
    "gojek.com": "Gojek",
    "lazada.com": "Lazada",
    "dbs.com": "DBS",
    "ocbc.com": "OCBC",
    "uob.com": "UOB",
}

# Regex to strip common corporate suffixes for lookup matching.
_SUFFIX_PATTERN = re.compile(
    r",?\s*\b(inc\.?|llc\.?|ltd\.?|corp\.?|corporation|incorporated|"
    r"limited|co\.?|plc\.?|pte\.?\s*ltd\.?|gmbh|ag|s\.?a\.?|"
    r"n\.?v\.?|b\.?v\.?|pty\.?\s*ltd\.?)\s*$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _strip_and_title(value: str | None) -> str | None:
    """Strip whitespace and apply title case. Returns None for empty."""
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped.title()


def _strip(value: str | None) -> str | None:
    """Strip whitespace. Returns None for empty."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _normalize_company(company: str | None) -> str | None:
    """Normalize company name using well-known lookup.

    Steps:
    1. Strip whitespace
    2. Strip common suffixes (Inc, LLC, Ltd, Corp, etc.)
    3. Look up in canonical dict
    4. If no match, return the stripped (but suffix-preserved) original
    """
    if company is None:
        return None
    stripped = company.strip()
    if not stripped:
        return None

    # Try matching after removing suffixes
    without_suffix = _SUFFIX_PATTERN.sub("", stripped).strip()
    lookup_key = without_suffix.lower()

    if lookup_key in _COMPANY_CANONICAL:
        return _COMPANY_CANONICAL[lookup_key]

    # No match — return original with whitespace stripped only
    return stripped


def _infer_company_from_email(email: str | None) -> str | None:
    """Extract company name from well-known email domains."""
    if not email:
        return None
    email = email.strip()
    if "@" not in email:
        return None
    domain = email.rsplit("@", 1)[1].lower()
    return _EMAIL_DOMAIN_TO_COMPANY.get(domain)


def _clean_contact(contact: dict) -> dict:
    """Clean a single contact dict. Returns a new dict (no mutation)."""
    cleaned = dict(contact)

    # --- Names ---
    first_name = _strip_and_title(cleaned.get("first_name"))
    last_name = _strip_and_title(cleaned.get("last_name"))

    # Split combined name in first_name when last_name is empty
    if first_name and not last_name and " " in first_name:
        parts = first_name.split(None, 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else None

    cleaned["first_name"] = first_name
    cleaned["last_name"] = last_name

    # Rebuild full_name from cleaned parts
    name_parts = [p for p in (first_name, last_name) if p]
    cleaned["full_name"] = " ".join(name_parts) if name_parts else None

    # --- Email ---
    cleaned["email"] = _strip(cleaned.get("email"))

    # --- Company ---
    company = _normalize_company(cleaned.get("current_company"))

    # Infer from email domain if company is empty
    if not company:
        company = _infer_company_from_email(cleaned.get("email"))

    cleaned["current_company"] = company

    # --- Title ---
    cleaned["current_title"] = _strip(cleaned.get("current_title"))

    # --- Regenerate fingerprint ---
    cleaned["fingerprint"] = generate_fingerprint(
        cleaned.get("full_name"),
        cleaned.get("current_company"),
        cleaned.get("linkedin_url"),
    )

    return cleaned


# ---------------------------------------------------------------------------
# Mock cleaner
# ---------------------------------------------------------------------------


@timed("csv_clean_mock")
def clean_contacts_mock(contacts: list[dict]) -> list[dict]:
    """Clean a list of parsed contact dicts using deterministic heuristics.

    Operates on the output of csv_parser (list of dicts with first_name,
    last_name, full_name, email, current_company, current_title, etc.).

    Cleaning steps:
    - Title-case names, strip whitespace from all string fields
    - Split combined first_name into first/last when last_name is empty
    - Normalize well-known company names (e.g. "GOOGLE LLC" -> "Google")
    - Infer company from email domain when company is empty
    - Regenerate fingerprint after cleanup

    Returns a new list of cleaned dicts (does not mutate input).
    """
    if not contacts:
        return []

    result = [_clean_contact(c) for c in contacts]
    logger.info("Cleaned %d contacts (mock mode)", len(result))
    return result


# ---------------------------------------------------------------------------
# Real Claude API cleaner
# ---------------------------------------------------------------------------


def _build_cleanup_payload(contacts: list[dict]) -> list[dict]:
    """Extract minimal fields to send to Claude for cleanup."""
    return [
        {
            "first_name": c.get("first_name") or "",
            "last_name": c.get("last_name") or "",
            "current_company": c.get("current_company") or "",
            "current_title": c.get("current_title") or "",
        }
        for c in contacts
    ]


def _merge_cleaned_fields(original: dict, cleaned_fields: dict) -> dict:
    """Merge Claude's cleaned fields back into the original contact dict.

    Preserves all fields not returned by Claude (email, connected_on,
    linkedin_url, etc.). Rebuilds full_name and regenerates fingerprint.
    """
    merged = dict(original)

    # Apply Claude's cleaned fields
    first_name = (cleaned_fields.get("first_name") or "").strip() or None
    last_name = (cleaned_fields.get("last_name") or "").strip() or None
    merged["first_name"] = first_name
    merged["last_name"] = last_name

    # Rebuild full_name from cleaned parts
    name_parts = [p for p in (first_name, last_name) if p]
    merged["full_name"] = " ".join(name_parts) if name_parts else None

    # Apply cleaned company and title
    company = (cleaned_fields.get("current_company") or "").strip() or None
    merged["current_company"] = company
    merged["current_title"] = (
        cleaned_fields.get("current_title") or ""
    ).strip() or None

    # Clean email (strip whitespace)
    email = merged.get("email")
    if email and isinstance(email, str):
        merged["email"] = email.strip() or None
    else:
        merged["email"] = None

    # Infer company from email if still empty
    if not merged["current_company"]:
        merged["current_company"] = _infer_company_from_email(merged.get("email"))

    # Regenerate fingerprint
    merged["fingerprint"] = generate_fingerprint(
        merged.get("full_name"),
        merged.get("current_company"),
        merged.get("linkedin_url"),
    )

    return merged


def _get_anthropic_client() -> anthropic.AsyncAnthropic:
    """Shared singleton Anthropic client."""
    from app.utils.anthropic_client import get_async_client

    return get_async_client()


async def _clean_batch(
    client: anthropic.AsyncAnthropic,
    batch: list[dict],
) -> list[dict]:
    """Clean a single batch via Claude API, guarded by global rate limiter."""
    from app.utils.rate_limiter import acqui[RESEND_KEY_REDACTED], release_slot

    used_redis = await acqui[RESEND_KEY_REDACTED](
        "anthropic", max_concurrent=settings.ANTHROPIC_MAX_CONCURRENT
    )
    try:
        payload = _build_cleanup_payload(batch)
        message = await client.messages.create(
            model=CLEANUP_MODEL,
            max_tokens=16384,
            system=_CLEANUP_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(payload)}],
        )

        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            raw = raw.rsplit("```", 1)[0].strip()

        parsed = json.loads(raw)
        cleaned = []
        for i, cleaned_fields in enumerate(parsed):
            if i < len(batch):
                cleaned.append(_merge_cleaned_fields(batch[i], cleaned_fields))

        logger.info(
            "Cleaned batch of %d contacts via Claude API (tokens: %d in / %d out)",
            len(batch),
            message.usage.input_tokens,
            message.usage.output_tokens,
        )
        return cleaned
    except anthropic.RateLimitError as exc:
        hdrs = getattr(getattr(exc, "response", None), "headers", {})
        logger.warning(
            "Claude rate limit during CSV clean (batch=%d): "
            "requests=%s/%s, tokens=%s/%s, retry-after=%s",
            len(batch),
            hdrs.get("x-ratelimit-remaining-requests", "?"),
            hdrs.get("x-ratelimit-limit-requests", "?"),
            hdrs.get("x-ratelimit-remaining-tokens", "?"),
            hdrs.get("x-ratelimit-limit-tokens", "?"),
            hdrs.get("retry-after", "?"),
        )
        raise
    finally:
        await release_slot("anthropic", used_redis)


@timed("csv_clean_real")
async def clean_contacts_real(contacts: list[dict]) -> list[dict]:
    """Clean contacts using the Claude API for fuzzy name/company resolution.

    Batches contacts (CLEANUP_BATCH_SIZE per API call) with global rate
    limiting across all workers. Falls back to mock cleaner on any error.
    """
    if not contacts:
        return []

    try:
        client = _get_anthropic_client()

        batches = [
            contacts[i : i + CLEANUP_BATCH_SIZE]
            for i in range(0, len(contacts), CLEANUP_BATCH_SIZE)
        ]

        results = await asyncio.gather(
            *[_clean_batch(client, batch) for batch in batches],
            return_exceptions=True,
        )

        all_cleaned: list[dict] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(
                    "Batch %d failed (%s), using mock for %d contacts",
                    i,
                    result,
                    len(batches[i]),
                )
                all_cleaned.extend(clean_contacts_mock(batches[i]))
            else:
                all_cleaned.extend(result)

        logger.info(
            "Cleaned %d contacts total (real mode, %d parallel batches)",
            len(all_cleaned),
            len(batches),
        )
        return all_cleaned

    except Exception:
        logger.exception("Claude API cleanup failed, falling back to mock cleaner")
        return clean_contacts_mock(contacts)


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------


async def clean_contacts(contacts: list[dict]) -> list[dict]:
    """Clean parsed contact dicts — dispatches to mock or real based on config.

    When AI_MOCK_MODE is true, uses deterministic heuristics (no API calls).
    When false, uses the Claude API for fuzzy name/company resolution.
    Degrades to mock when task queue depth exceeds threshold.
    """
    if settings.AI_MOCK_MODE:
        return clean_contacts_mock(contacts)

    # Degrade to mock under heavy load to prevent queue buildup
    from app.utils.rate_limiter import get_queue_depth

    depth = await get_queue_depth()
    if depth > settings.QUEUE_DEPTH_THRESHOLD:
        logger.warning(
            "Queue depth %d exceeds threshold %d — using mock cleaner",
            depth,
            settings.QUEUE_DEPTH_THRESHOLD,
        )
        return clean_contacts_mock(contacts)

    return await clean_contacts_real(contacts)
