import re
import unicodedata

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.contact import Contact

# Suffixes to strip when normalizing company names.
# Order matters: longer suffixes first to avoid partial matches.
_SUFFIXES = [
    "incorporated",
    "corporation",
    "limited liability company",
    "technologies",
    "technology",
    "enterprises",
    "holdings",
    "platforms",
    "partners",
    "solutions",
    "consulting",
    "services",
    "group",
    "corp.",
    "corp",
    "inc.",
    "inc",
    "llc.",
    "llc",
    "ltd.",
    "ltd",
    "l.l.c.",
    "l.l.c",
    "l.p.",
    "lp",
    "p.l.c.",
    "plc",
    "co.",
    "co",
    "gmbh",
    "s.a.",
    "sa",
    "ag",
    "b.v.",
    "bv",
    "n.v.",
    "nv",
    "pty.",
    "pty",
    "pvt.",
    "pvt",
]

# Well-known company aliases: map alternate names to a single canonical form.
# Keys must be lowercase. The canonical value is what gets stored.
_ALIASES: dict[str, str] = {
    "facebook": "Meta",
    "meta platforms": "Meta",
    "meta": "Meta",
    "alphabet": "Google",
    "alphabet inc": "Google",
    "google llc": "Google",
    "google": "Google",
    "microsoft corporation": "Microsoft",
    "microsoft corp": "Microsoft",
    "microsoft": "Microsoft",
    "amazon.com": "Amazon",
    "amazon web services": "AWS",
    "aws": "AWS",
    "apple inc": "Apple",
    "apple": "Apple",
    "ibm corporation": "IBM",
    "ibm": "IBM",
    "international business machines": "IBM",
}


def normalize_company_name(name: str | None) -> str | None:
    """Normalize a company name for matching purposes.

    Steps:
      1. Strip whitespace, normalize unicode
      2. Check known aliases
      3. Strip legal suffixes (Inc., LLC, etc.)
      4. Title-case the result
    """
    if not name or not name.strip():
        return None

    # Normalize unicode (e.g. accented chars) and strip
    cleaned = unicodedata.normalize("NFC", name.strip())

    # Check aliases first (case-insensitive)
    alias_key = cleaned.lower()
    if alias_key in _ALIASES:
        return _ALIASES[alias_key]

    # Strip trailing legal suffixes
    lower = cleaned.lower()
    # Remove trailing comma before suffix (e.g. "Acme, Inc.")
    lower = re.sub(r",\s*$", "", lower)

    for suffix in _SUFFIXES:
        # Match suffix at end, optionally preceded by comma/space
        pattern = r"[,\s]+" + re.escape(suffix) + r"\.?\s*$"
        match = re.search(pattern, lower)
        if match:
            cleaned = cleaned[: match.start()].strip()
            lower = cleaned.lower()
            # Check alias again after stripping suffix
            if lower in _ALIASES:
                return _ALIASES[lower]
            break

    # Remove trailing punctuation
    cleaned = cleaned.rstrip(".,;")

    if not cleaned:
        return None

    # Title-case, but preserve existing all-caps short names (IBM, AWS, etc.)
    if cleaned.isupper() and len(cleaned) <= 5:
        return cleaned
    return cleaned.title() if cleaned.islower() else cleaned


async def find_or_create_company(
    name: str, db: AsyncSession
) -> Company | None:
    """Look up a company by normalized name. Create if not found.

    Uses case-insensitive exact match on the name column.
    Returns None if the name normalizes to nothing.
    """
    normalized = normalize_company_name(name)
    if not normalized:
        return None

    # Case-insensitive lookup
    result = await db.execute(
        select(Company).where(func.lower(Company.name) == normalized.lower())
    )
    company = result.scalar_one_or_none()

    if company is None:
        company = Company(name=normalized)
        db.add(company)
        await db.flush()

    return company


async def link_contact_to_company(
    contact: Contact, db: AsyncSession
) -> None:
    """Set contact.company_id based on its current_company field."""
    if not contact.current_company:
        return

    company = await find_or_create_company(contact.current_company, db)
    if company:
        contact.company_id = company.id
