"""AI-powered CSV data cleanup service.

Runs AFTER csv_parser to clean messy data from LinkedIn CSV exports.

Mock mode (this module): deterministic heuristics, no API calls.
Real mode (future): Claude API for fuzzy name/company resolution.

Follows the same mock/real pattern as ai_matcher.py.
"""

import logging
import re

from app.services.csv_parser import generate_fingerprint
from app.utils.performance import timed

logger = logging.getLogger(__name__)

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
# Public API
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
