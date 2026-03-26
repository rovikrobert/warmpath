import csv
import hashlib
import io
import re
from datetime import date, datetime

from app.utils.performance import timed


# LinkedIn changes column names across export versions. Map known variants
# to our internal field names.
COLUMN_ALIASES: dict[str, str] = {
    # first_name
    "first name": "first_name",
    "first_name": "first_name",
    "firstname": "first_name",
    # last_name
    "last name": "last_name",
    "last_name": "last_name",
    "lastname": "last_name",
    # email
    "email address": "email",
    "email_address": "email",
    "email": "email",
    "e-mail address": "email",
    # company
    "company": "company",
    "company name": "company",
    # position / title
    "position": "title",
    "title": "title",
    "job title": "title",
    # connected_on
    "connected on": "connected_on",
    "connected_on": "connected_on",
    "date connected": "connected_on",
    # linkedin url
    "url": "linkedin_url",
    "profile url": "linkedin_url",
    "linkedin url": "linkedin_url",
    # phone
    "phone": "phone",
    "phone number": "phone",
    "mobile": "phone",
    "mobile phone": "phone",
}

# Simplified manual CSV format aliases
MANUAL_CSV_ALIASES: dict[str, str] = {
    "name": "name",
    "full name": "name",
    "full_name": "name",
    "first name": "first_name",
    "first_name": "first_name",
    "last name": "last_name",
    "last_name": "last_name",
    "company": "company",
    "title": "title",
    "position": "title",
    "relationship": "relationship_type",
    "relationship_type": "relationship_type",
    "how you know": "how_you_know",
    "how_you_know": "how_you_know",
    "last contact date": "last_contact_date",
    "last_contact_date": "last_contact_date",
    "last interaction": "last_contact_date",
    "email": "email",
    "email address": "email",
    "location": "location",
    "phone": "phone",
    "phone number": "phone",
    "mobile": "phone",
    "mobile phone": "phone",
}

_RECRUITER_PATTERN = re.compile(
    r"\b(recruiter|recruiting|talent\s+acquisition|talent\s+partner|sourcer)\b",
    re.IGNORECASE,
)

# Characters that trigger formula injection in spreadsheets
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

MAX_CSV_ROWS = 50_000


def sanitize_cell(value: str | None) -> str | None:
    """Sanitize a CSV cell value to prevent formula injection.

    Any cell starting with =, +, -, @, \\t, or \\r is prefixed with a
    single quote so spreadsheet applications don't execute it as a formula.
    """
    if not value:
        return value
    if value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def _normalize_header(header: str) -> str | None:
    """Map a raw CSV header to our internal field name, or None if unknown."""
    return COLUMN_ALIASES.get(header.strip().lower())


def _normalize_manual_header(header: str) -> str | None:
    """Map a manual CSV header to our internal field name, or None if unknown."""
    return MANUAL_CSV_ALIASES.get(header.strip().lower())


def _title_case(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    return sanitize_cell(value.strip().title())


def _clean(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    return sanitize_cell(value.strip())


def _clean_phone(value: str | None) -> str | None:
    """Clean a phone number value without formula sanitization.

    Phone numbers legitimately start with '+' (international prefix),
    so we skip the sanitize_cell step that would escape it.
    """
    if not value or not value.strip():
        return None
    return value.strip()


def _parse_connected_on(value: str | None) -> date | None:
    """Parse LinkedIn's connected-on date. Common formats: '01 Jan 2024', '2024-01-15'."""
    if not value or not value.strip():
        return None
    value = value.strip()
    for fmt in ("%d %b %Y", "%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def generate_fingerprint(
    full_name: str | None, company: str | None, linkedin_url: str | None
) -> str | None:
    """Create a stable dedup hash from (full_name + company + linkedin_url).

    Returns None if all inputs are empty (cannot fingerprint).
    """
    parts = [
        (full_name or "").strip().lower(),
        (company or "").strip().lower(),
        (linkedin_url or "").strip().lower(),
    ]
    combined = "|".join(parts)
    if combined == "||":
        return None
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:40]


def _decode_csv_bytes(raw: bytes) -> str:
    """Decode CSV bytes as UTF-8. Raises ValueError on non-UTF-8 input."""
    # Strip BOM if present
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "CSV file is not valid UTF-8. Please re-export your file with UTF-8 encoding."
        ) from exc


def classify_relationship(
    contact_company: str | None,
    contact_title: str | None,
    user_current_company: str | None,
    user_work_history: list[dict] | None,
) -> str | None:
    """Auto-classify relationship type based on user profile context.

    Rules:
      - Contact at user's current company → 'current_colleague'
      - Contact at a company in user's work_history → 'former_colleague'
      - Contact title contains recruiter/talent keywords → 'recruiter'
      - Otherwise → None (unknown)
    """
    contact_co = (contact_company or "").strip().lower()
    if not contact_co:
        # Check recruiter by title only
        if contact_title and _RECRUITER_PATTERN.search(contact_title):
            return "recruiter"
        return None

    user_co = (user_current_company or "").strip().lower()
    if user_co and contact_co == user_co:
        return "current_colleague"

    if user_work_history:
        for entry in user_work_history:
            hist_company = (entry.get("company", "") or "").strip().lower()
            if hist_company and hist_company == contact_co:
                return "former_colleague"

    if contact_title and _RECRUITER_PATTERN.search(contact_title):
        return "recruiter"

    return None


def _detect_csv_format(fieldnames: list[str]) -> str:
    """Detect whether CSV is LinkedIn or manual format.

    Returns "linkedin", "manual", or "unknown".

    Prefers manual format when headers contain manual-only columns
    (name, relationship_type, how_you_know, last_contact_date) since
    "company" and "title" overlap between both formats.
    """
    linkedin_count = sum(1 for c in fieldnames if _normalize_header(c) is not None)
    manual_count = sum(1 for c in fieldnames if _normalize_manual_header(c) is not None)

    # Manual-only columns that don't appear in LinkedIn format
    _MANUAL_ONLY = {"name", "relationship_type", "how_you_know", "last_contact_date"}
    has_manual_only = any(
        _normalize_manual_header(c) in _MANUAL_ONLY for c in fieldnames
    )

    # If we have manual-only columns, this is a manual format
    if has_manual_only and manual_count >= 2:
        return "manual"

    # LinkedIn-specific columns (first_name, last_name, connected_on, linkedin_url)
    _LINKEDIN_ONLY = {"first_name", "last_name", "connected_on", "linkedin_url"}
    has_linkedin_only = any(_normalize_header(c) in _LINKEDIN_ONLY for c in fieldnames)

    if has_linkedin_only and linkedin_count >= 2:
        return "linkedin"

    # Fallback: whichever has more matches
    if linkedin_count >= 2:
        return "linkedin"
    if manual_count >= 2:
        return "manual"

    return "unknown"


def parse_manual_csv(raw_bytes: bytes) -> list[dict]:
    """Parse a simplified manual CSV format.

    Expected columns: name (or first_name+last_name), company, title,
    relationship, how_you_know, last_contact_date, email, location, phone
    """
    text = _decode_csv_bytes(raw_bytes)
    reader = csv.DictReader(io.StringIO(text))

    if reader.fieldnames is None:
        return []

    header_map: dict[str, str] = {}
    for raw_header in reader.fieldnames:
        internal = _normalize_manual_header(raw_header)
        if internal:
            header_map[raw_header] = internal

    contacts: list[dict] = []
    row_count = 0
    for row in reader:
        row_count += 1
        if row_count > MAX_CSV_ROWS:
            raise ValueError(
                f"CSV exceeds maximum of {MAX_CSV_ROWS:,} rows. "
                "Please split the file into smaller batches."
            )

        mapped: dict[str, str | None] = {}
        for raw_header, internal_name in header_map.items():
            mapped[internal_name] = row.get(raw_header)

        # Handle "name" field (split into first/last)
        if mapped.get("name") and not mapped.get("first_name"):
            parts = mapped["name"].strip().split(None, 1)
            mapped["first_name"] = parts[0] if parts else None
            mapped["last_name"] = parts[1] if len(parts) > 1 else None

        first_name = _title_case(mapped.get("first_name"))
        last_name = _title_case(mapped.get("last_name"))

        name_parts = [p for p in (first_name, last_name) if p]
        if not name_parts:
            continue
        full_name = " ".join(name_parts)

        company = _clean(mapped.get("company"))
        title = _clean(mapped.get("title"))
        email = _clean(mapped.get("email"))
        relationship_type = _clean(mapped.get("relationship_type"))
        how_you_know = _clean(mapped.get("how_you_know"))
        last_contact_date = _parse_connected_on(mapped.get("last_contact_date"))
        location = _clean(mapped.get("location"))
        phone = _clean_phone(mapped.get("phone"))
        fingerprint = generate_fingerprint(full_name, company, None)

        contacts.append(
            {
                "first_name": first_name,
                "last_name": last_name,
                "full_name": full_name,
                "email": email,
                "current_company": company,
                "current_title": title,
                "connected_on": last_contact_date,
                "last_interaction_date": last_contact_date,
                "linkedin_url": None,
                "fingerprint": fingerprint,
                "relationship_type": relationship_type,
                "how_you_know": how_you_know,
                "location": location,
                "phone": phone,
                "source": "manual",
                "raw_csv_row": dict(row),
            }
        )

    return contacts


@timed("csv_parse")
def parse_linkedin_csv(raw_bytes: bytes) -> list[dict]:
    """Parse a LinkedIn connections CSV export and return normalized contact dicts.

    Also auto-detects simplified manual CSV format. If headers don't match
    LinkedIn format but match manual format, delegates to parse_manual_csv.

    Each dict contains:
        first_name, last_name, full_name, email, company, title,
        connected_on (date|None), linkedin_url, fingerprint, raw_row (original dict)
    """
    text = _decode_csv_bytes(raw_bytes)

    # LinkedIn CSV exports may include a "Notes:" preamble section before the
    # actual header row.  Detect this and skip to the real header.
    lines = text.splitlines(keepends=True)
    skip = 0
    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        # Look for the first line that contains at least two known column names
        if stripped:
            test_reader = csv.reader(io.StringIO(line))
            try:
                cells = next(test_reader)
            except StopIteration:
                continue
            matched = sum(1 for c in cells if _normalize_header(c) is not None)
            if matched >= 2:
                skip = i
                break

    csv_text = "".join(lines[skip:])
    reader = csv.DictReader(io.StringIO(csv_text))

    # Build mapping from raw header -> internal name
    if reader.fieldnames is None:
        return []

    # Auto-detect format
    fmt = _detect_csv_format(list(reader.fieldnames))
    if fmt == "manual":
        return parse_manual_csv(raw_bytes)
    if fmt == "unknown":
        raise ValueError(
            "This file doesn't contain recognizable LinkedIn connections. "
            "To export your connections: go to linkedin.com/mypreferences/d/download-my-data, "
            "select 'Connections', and upload the downloaded CSV."
        )

    header_map: dict[str, str] = {}
    for raw_header in reader.fieldnames:
        internal = _normalize_header(raw_header)
        if internal:
            header_map[raw_header] = internal

    contacts: list[dict] = []
    row_count = 0
    for row in reader:
        row_count += 1
        if row_count > MAX_CSV_ROWS:
            raise ValueError(
                f"CSV exceeds maximum of {MAX_CSV_ROWS:,} rows. "
                "Please split the file into smaller batches."
            )

        # Remap to internal names
        mapped: dict[str, str | None] = {}
        for raw_header, internal_name in header_map.items():
            mapped[internal_name] = row.get(raw_header)

        first_name = _title_case(mapped.get("first_name"))
        last_name = _title_case(mapped.get("last_name"))

        # Build full name; skip rows with no name at all
        name_parts = [p for p in (first_name, last_name) if p]
        if not name_parts:
            continue
        full_name = " ".join(name_parts)

        company = _clean(mapped.get("company"))
        title = _clean(mapped.get("title"))
        email = _clean(mapped.get("email"))
        linkedin_url = _clean(mapped.get("linkedin_url"))
        connected_on = _parse_connected_on(mapped.get("connected_on"))
        phone = _clean_phone(mapped.get("phone"))
        fingerprint = generate_fingerprint(full_name, company, linkedin_url)

        contacts.append(
            {
                "first_name": first_name,
                "last_name": last_name,
                "full_name": full_name,
                "email": email,
                "current_company": company,
                "current_title": title,
                "connected_on": connected_on,
                "linkedin_url": linkedin_url,
                "fingerprint": fingerprint,
                "phone": phone,
                "raw_csv_row": dict(row),
            }
        )

    if not contacts and row_count == 0:
        raise ValueError(
            "This file doesn't contain recognizable LinkedIn connections. "
            "To export your connections: go to linkedin.com/mypreferences/d/download-my-data, "
            "select 'Connections', and upload the downloaded CSV."
        )

    return contacts
