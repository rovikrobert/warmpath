"""Resume PDF parser — extracts structured profile data using AI.

When AI_MOCK_MODE=true (default), returns deterministic fake profile data
without requiring pdfplumber or a Gemini API key.
"""

import asyncio
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


_RESUME_SYSTEM_PROMPT = """\
You are a resume parser. Extract structured profile information from the resume text.

Return a JSON object with exactly these fields (use null for any field you cannot determine):

1. "headline" (string): A concise professional headline, e.g. "Senior Software Engineer | Full-Stack Developer". Derive from the resume's summary/objective or infer from the most recent role.

2. "current_company" (string): The most recent or current employer name exactly as written on the resume.

3. "current_title" (string): The most recent or current job title exactly as written.

4. "industry" (string): The person's primary industry, e.g. "Technology", "Finance", "Healthcare".

5. "location" (string): City, state/region, and/or country as listed on the resume.

6. "bio_summary" (string): A 2-3 sentence professional summary. If the resume has a Summary/Objective section, paraphrase it. Otherwise, synthesize from work experience.

7. "work_history" (array): Each entry has:
   - "company" (string): employer name
   - "title" (string): job title
   - "start_date" (string): format YYYY-MM, e.g. "2019-06". If only a year is given, use YYYY-01.
   - "end_date" (string or null): format YYYY-MM, or null if this is the current role (indicated by "Present", "Current", "Now", or no end date listed).

   Order work_history by most recent first (descending by start_date).
   Include ALL roles listed in the Experience/Employment section.

IMPORTANT:
- Return ONLY valid JSON. No markdown fences, no extra text.
- Look for sections titled Experience, Employment, Work History, Education, Summary, Objective, Skills.
- For date parsing: "Jan 2020" = "2020-01", "March 2019" = "2019-03", "2021" = "2021-01", "Present" = null end_date."""


async def _ai_parse(text: str) -> dict:
    """Send extracted resume text to Gemini Flash for structured extraction."""
    from google import genai

    from app.utils.gemini_client import get_gemini_client
    from app.utils.rate_limiter import acquire_slot, release_slot

    client = get_gemini_client()

    used_redis = await acquire_slot(
        "google", max_concurrent=settings.GOOGLE_MAX_CONCURRENT
    )
    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=text[:8000],
            config=genai.types.GenerateContentConfig(
                system_instruction=_RESUME_SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0,
            ),
        )
    finally:
        await release_slot("google", used_redis)

    return json.loads(response.text)


async def parse_resume(pdf_bytes: bytes) -> dict:
    """Extract structured profile data from a resume PDF.

    Returns dict with: headline, current_company, current_title, industry,
    location, bio_summary, work_history.
    """
    _validate_pdf(pdf_bytes)

    if settings.AI_MOCK_MODE:
        return _mock_parse()

    text = await asyncio.to_thread(_extract_text, pdf_bytes)
    return await _ai_parse(text)
