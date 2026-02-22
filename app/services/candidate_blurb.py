"""Candidate blurb generation service.

Generates AI-powered 2-3 sentence candidate summaries that network holders
can copy-paste when forwarding a referral request to their contact/HR.

Uses the Anthropic Claude API in production, deterministic mock in dev/test.
"""

from __futu[RESEND_KEY_REDACTED] import annotations

import json
import logging
from typing import TYPE_CHECKING

import anthropic

from app.config import settings

if TYPE_CHECKING:
    from app.models.contact import Contact
    from app.models.job import UserJobPreferences
    from app.models.user import ConnectorProfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_work_history_overlap(
    profile: ConnectorProfile | None,
    contact: Contact,
) -> str | None:
    """Check if seeker's work history contains the contact's current company.

    Returns a human-readable overlap description, or None if no overlap found.
    """
    if not profile or not profile.work_history or not contact.current_company:
        return None

    contact_company_lower = contact.current_company.strip().lower()
    for entry in profile.work_history:
        company = (entry.get("company") or "").strip().lower()
        if company and company == contact_company_lower:
            title = entry.get("title", "")
            start = entry.get("start_date", "")
            end = entry.get("end_date", "")
            period = f" ({start}\u2013{end})" if start and end else ""
            role_part = f" as {title}" if title else ""
            return (
                f"Previously at {contact.current_company}{role_part}{period}"
                f" where they overlapped with {contact.full_name}."
            )
    return None


def _build_links_line(profile: ConnectorProfile | None) -> str:
    """Build an inline links string from profile URLs."""
    if not profile:
        return ""
    parts: list[str] = []
    if profile.github_url:
        parts.append(f"GitHub: {profile.github_url}")
    if profile.portfolio_url:
        parts.append(f"Portfolio: {profile.portfolio_url}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Mock blurb — deterministic, for dev/test (AI_MOCK_MODE=true)
# ---------------------------------------------------------------------------


def _mock_specific_role_blurb(
    profile: ConnectorProfile | None,
    contact: Contact,
    prefs: UserJobPreferences | None,
    job_title: str | None,
) -> str:
    """Generate a deterministic blurb for a specific role request."""
    if not profile:
        target = job_title or (prefs.target_role if prefs else "a role")
        return (
            f"A candidate interested in {target} at "
            f"{contact.current_company or 'the company'}. "
            f"Motivated to contribute and looking for a referral opportunity."
        )

    title = profile.current_title or "professional"
    company = profile.current_company or "their current company"
    bio = profile.bio_summary or ""
    bio_part = f" with experience in {bio}" if bio else ""

    overlap = _detect_work_history_overlap(profile, contact)
    overlap_part = f" {overlap}" if overlap else ""

    target = job_title or (prefs.target_role if prefs else None)
    target_company = contact.current_company or "the company"
    target_part = f" Targeting {target} at {target_company}." if target else ""

    links = _build_links_line(profile)
    links_part = f" {links}" if links else ""

    return f"A {title} at {company}{bio_part}.{overlap_part}{target_part}{links_part}"


def _mock_networking_blurb(
    profile: ConnectorProfile | None,
    contact: Contact,
    prefs: UserJobPreferences | None,
    exploration_context: str | None,
) -> str:
    """Generate a deterministic blurb for a general networking request."""
    if not profile:
        context = exploration_context or "exploring opportunities"
        return (
            f"A professional {context} at {contact.current_company or 'the company'}."
        )

    title = profile.current_title or "professional"
    company = profile.current_company or "their current company"
    bio = profile.bio_summary or ""
    bio_part = f" with experience in {bio}" if bio else ""

    overlap = _detect_work_history_overlap(profile, contact)
    overlap_part = f" {overlap}" if overlap else ""

    context = exploration_context or "exploring opportunities"
    context_part = f" Currently {context.lower()}." if context else ""

    links = _build_links_line(profile)
    links_part = f" {links}" if links else ""

    return f"A {title} at {company}{bio_part}.{overlap_part}{context_part}{links_part}"


def _generate_mock_blurb(
    profile: ConnectorProfile | None,
    contact: Contact,
    prefs: UserJobPreferences | None,
    request_type: str,
    job_title: str | None,
    exploration_context: str | None,
) -> str:
    """Route to the correct mock blurb builder based on request type."""
    if request_type == "general_networking":
        return _mock_networking_blurb(profile, contact, prefs, exploration_context)
    return _mock_specific_role_blurb(profile, contact, prefs, job_title)


# ---------------------------------------------------------------------------
# Real Claude API blurb
# ---------------------------------------------------------------------------


def _format_candidate_info(profile: ConnectorProfile | None) -> str:
    """Format candidate profile fields into a prompt-friendly string."""
    if not profile:
        return "No detailed profile available."

    field_map = [
        ("current_title", "Current title"),
        ("current_company", "Current company"),
        ("bio_summary", "Background"),
        ("industry", "Industry"),
        ("location", "Location"),
        ("github_url", "GitHub"),
        ("portfolio_url", "Portfolio"),
    ]
    parts: list[str] = []
    for attr, label in field_map:
        value = getattr(profile, attr, None)
        if value:
            parts.append(f"{label}: {value}")

    if profile.work_history:
        history_lines = []
        for entry in profile.work_history:
            co = entry.get("company", "")
            ti = entry.get("title", "")
            sd = entry.get("start_date", "")
            ed = entry.get("end_date", "")
            period = f" ({sd}\u2013{ed})" if sd and ed else ""
            history_lines.append(f"  - {ti} at {co}{period}")
        parts.append("Work history:\n" + "\n".join(history_lines))

    return "\n".join(parts) if parts else "No detailed profile available."


def _format_contact_info(contact: Contact) -> str:
    """Format contact fields into a prompt-friendly string (no email -- privacy)."""
    parts = [f"Name: {contact.full_name}"]
    if contact.current_title:
        parts.append(f"Title: {contact.current_title}")
    if contact.current_company:
        parts.append(f"Company: {contact.current_company}")
    if contact.relationship_type:
        parts.append(f"Relationship: {contact.relationship_type}")
    if contact.how_you_know:
        parts.append(f"How they know each other: {contact.how_you_know}")
    return "\n".join(parts)


def _format_target_section(
    request_type: str,
    prefs: UserJobPreferences | None,
    job_title: str | None,
    job_description: str | None,
    exploration_context: str | None,
) -> tuple[str, str]:
    """Build the target/context section and framing instruction.

    Returns:
        A tuple of (target_section, framing).
    """
    if request_type == "specific_role":
        target_section = f"Target role: {job_title or (prefs.target_role if prefs else 'unspecified')}"
        if job_description:
            target_section += f"\nJob description: {job_description}"
        if prefs and prefs.target_seniority:
            target_section += f"\nTarget seniority: {prefs.target_seniority}"
        framing = (
            "This is for a specific role application. Emphasize the candidate's "
            "fit for the role and relevant experience."
        )
        return target_section, framing

    target_section = f"Context: {exploration_context}" if exploration_context else ""
    framing = (
        "This is for general networking/exploration. Use softer framing \u2014 "
        "emphasize curiosity and learning rather than a specific job ask."
    )
    return target_section, framing


def _build_blurb_prompt(
    profile: ConnectorProfile | None,
    contact: Contact,
    prefs: UserJobPreferences | None,
    request_type: str,
    job_title: str | None,
    job_description: str | None,
    exploration_context: str | None,
) -> str:
    """Build the Claude prompt for candidate blurb generation.

    Privacy boundary: contact name IS sent, contact email is NOT sent.
    """
    candidate_info = _format_candidate_info(profile)
    contact_info = _format_contact_info(contact)

    overlap = _detect_work_history_overlap(profile, contact)
    overlap_section = (
        f"\nIMPORTANT OVERLAP: {overlap} Mention this prominently.\n" if overlap else ""
    )

    target_section, framing = _format_target_section(
        request_type,
        prefs,
        job_title,
        job_description,
        exploration_context,
    )

    return f"""Write a 2-3 sentence candidate summary that a network holder can copy-paste when forwarding this person to their contact or HR team.

CANDIDATE:
{candidate_info}

CONTACT (the person who would forward this blurb):
{contact_info}
{overlap_section}
{target_section}

FRAMING: {framing}

Rules:
- Write in third person about the candidate
- Professional but warm tone
- 2-3 sentences maximum
- Do NOT start with "I'd like to introduce..." or similar first-person framing
- If GitHub or portfolio URLs are available, include them as inline text
- If there is work history overlap with the contact's company, mention it prominently
- Include the candidate's name only if available from the profile, otherwise use their title/role
- Keep it concise and easy to forward

Return ONLY the blurb text. No quotes, no explanation, no markdown."""


async def _call_claude_for_blurb(
    profile: ConnectorProfile | None,
    contact: Contact,
    prefs: UserJobPreferences | None,
    request_type: str,
    job_title: str | None,
    job_description: str | None,
    exploration_context: str | None,
) -> str:
    """Call the real Claude API to generate a candidate blurb."""
    from app.utils.anthropic_client import get_async_client
    from app.utils.rate_limiter import acqui[RESEND_KEY_REDACTED], release_slot

    client = get_async_client()
    prompt = _build_blurb_prompt(
        profile,
        contact,
        prefs,
        request_type,
        job_title,
        job_description,
        exploration_context,
    )

    used_redis = await acqui[RESEND_KEY_REDACTED](
        "anthropic", max_concurrent=settings.ANTHROPIC_MAX_CONCURRENT
    )
    try:
        message = await client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
    finally:
        await release_slot("anthropic", used_redis)

    logger.info(
        "Candidate blurb generated (tokens: %d in / %d out)",
        message.usage.input_tokens,
        message.usage.output_tokens,
    )

    raw = message.content[0].text.strip()
    # Strip markdown fences if the model wraps the output
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0].strip()
    # Strip surrounding quotes if present
    if (raw.startswith('"') and raw.endswith('"')) or (
        raw.startswith("'") and raw.endswith("'")
    ):
        raw = raw[1:-1].strip()

    return raw


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def generate_candidate_blurb(
    profile: ConnectorProfile | None,
    contact: Contact,
    prefs: UserJobPreferences | None = None,
    request_type: str = "specific_role",
    job_title: str | None = None,
    job_description: str | None = None,
    exploration_context: str | None = None,
) -> str:
    """Generate a 2-3 sentence candidate blurb for network holder forwarding.

    Switches between mock (deterministic template) and AI (Claude API) based
    on ``settings.AI_MOCK_MODE``.

    Args:
        profile: The job seeker's connector profile (may be None).
        contact: The contact the NH would forward the blurb about.
        prefs: The job seeker's job preferences (optional).
        request_type: ``"specific_role"`` or ``"general_networking"``.
        job_title: Target job title (used when request_type is specific_role).
        job_description: Target job description for AI context.
        exploration_context: Free text context for general networking requests.

    Returns:
        A 2-3 sentence blurb string.
    """
    if settings.AI_MOCK_MODE:
        return _generate_mock_blurb(
            profile,
            contact,
            prefs,
            request_type,
            job_title,
            exploration_context,
        )

    import asyncio

    max_retries = 2
    for attempt in range(max_retries):
        try:
            return await _call_claude_for_blurb(
                profile,
                contact,
                prefs,
                request_type,
                job_title,
                job_description,
                exploration_context,
            )
        except anthropic.RateLimitError:
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                logger.warning(
                    "Claude rate limit hit (candidate blurb), retrying in %ds...", wait
                )
                await asyncio.sleep(wait)
            else:
                logger.error("Claude rate limit persists, falling back to mock blurb")
                return _generate_mock_blurb(
                    profile,
                    contact,
                    prefs,
                    request_type,
                    job_title,
                    exploration_context,
                )
        except anthropic.APIError as exc:
            logger.error("Claude API error generating candidate blurb: %s", exc)
            return _generate_mock_blurb(
                profile,
                contact,
                prefs,
                request_type,
                job_title,
                exploration_context,
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.error("Failed to parse Claude blurb response: %s", exc)
            return _generate_mock_blurb(
                profile,
                contact,
                prefs,
                request_type,
                job_title,
                exploration_context,
            )

    # Unreachable, but satisfies type checker
    return _generate_mock_blurb(
        profile,
        contact,
        prefs,
        request_type,
        job_title,
        exploration_context,
    )
