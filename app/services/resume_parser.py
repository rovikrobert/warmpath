"""Resume PDF parser — extracts structured profile data using AI.

When AI_MOCK_MODE=true (default), returns deterministic fake profile data
without requiring pdfplumber or an Anthropic API key.
"""

import io
import json
import logging

from app.config import settings

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_PAGES = 20


class ResumeParseError(Exception):
    """Raised when resume parsing fails."""


def _validate_pdf(pdf_bytes: bytes) -> None:
    """Validate file is a real PDF within size/page limits."""
    if len(pdf_bytes) > MAX_FILE_SIZE:
        raise ResumeParseError("File exceeds 5 MB limit")
    if not pdf_bytes[:5] == b"%PDF-":
        raise ResumeParseError("File is not a valid PDF")


def _extract_text(pdf_bytes: bytes) -> str:
    """Use pdfplumber to extract text from all pages (up to MAX_PAGES)."""
    import pdfplumber

    text_parts: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        if len(pdf.pages) > MAX_PAGES:
            raise ResumeParseError(f"PDF has too many pages (max {MAX_PAGES})")
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    full_text = "\n".join(text_parts)
    if not full_text.strip():
        raise ResumeParseError("Could not extract text from PDF (may be image-based)")
    return full_text


def _mock_parse() -> dict:
    """Return deterministic mock profile data for testing."""
    return {
        "headline": "Senior Software Engineer | Full-Stack Developer",
        "current_company": "TechCorp Inc.",
        "current_title": "Senior Software Engineer",
        "industry": "Technology",
        "location": "San Francisco, CA",
        "bio_summary": (
            "Experienced software engineer with 8+ years building scalable "
            "web applications. Specializing in Python, React, and cloud architecture."
        ),
        "work_history": [
            {
                "company": "TechCorp Inc.",
                "title": "Senior Software Engineer",
                "start_date": "2022-01",
                "end_date": None,
            },
            {
                "company": "StartupXYZ",
                "title": "Software Engineer",
                "start_date": "2019-06",
                "end_date": "2021-12",
            },
            {
                "company": "BigCo Ltd.",
                "title": "Junior Developer",
                "start_date": "2017-03",
                "end_date": "2019-05",
            },
        ],
    }


async def _ai_parse(text: str) -> dict:
    """Send extracted resume text to Claude for structured extraction."""
    import anthropic

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    prompt = f"""Extract structured profile information from this resume text.
Return a JSON object with these fields (use null for any field you cannot determine):
- headline: a brief professional headline (1 line)
- current_company: the most recent/current employer
- current_title: the most recent/current job title
- industry: the person's industry
- location: city/region/country
- bio_summary: a 2-3 sentence professional summary
- work_history: array of objects with company, title, start_date (YYYY-MM format), end_date (YYYY-MM format or null if current)

Return ONLY valid JSON, no markdown fences or extra text.

Resume text:
{text[:8000]}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw[:-3]
    return json.loads(raw)


async def parse_resume(pdf_bytes: bytes) -> dict:
    """Extract structured profile data from a resume PDF.

    Returns dict with: headline, current_company, current_title, industry,
    location, bio_summary, work_history.
    """
    _validate_pdf(pdf_bytes)

    if settings.AI_MOCK_MODE:
        return _mock_parse()

    text = _extract_text(pdf_bytes)
    return await _ai_parse(text)
