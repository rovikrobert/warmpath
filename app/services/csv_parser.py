import csv
import hashlib
import io
from datetime import date, datetime


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
}


def _normalize_header(header: str) -> str | None:
    """Map a raw CSV header to our internal field name, or None if unknown."""
    return COLUMN_ALIASES.get(header.strip().lower())


def _title_case(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    return value.strip().title()


def _clean(value: str | None) -> str | None:
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
    """Decode CSV bytes, trying UTF-8 first then Latin-1 as fallback."""
    # Strip BOM if present
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def parse_linkedin_csv(raw_bytes: bytes) -> list[dict]:
    """Parse a LinkedIn connections CSV export and return normalized contact dicts.

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

    header_map: dict[str, str] = {}
    for raw_header in reader.fieldnames:
        internal = _normalize_header(raw_header)
        if internal:
            header_map[raw_header] = internal

    contacts: list[dict] = []
    for row in reader:
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
                "raw_csv_row": dict(row),
            }
        )

    return contacts
