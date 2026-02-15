"""AI-powered intro message drafting service.

Generates 2-3 message variants for reaching out to a contact.
Uses the Anthropic Claude API in production, deterministic mock in dev/test.
"""

import json
from dataclasses import dataclass

from app.config import settings
from app.models.contact import Contact
from app.models.match_result import MatchResult
from app.models.user import ConnectorProfile


LINKEDIN_CHAR_LIMIT = 300

VARIANTS = [
    ("direct", "Straightforward professional ask"),
    ("mutual-interest", "Lead with shared context or mutual interest"),
    ("casual", "Lighter, conversational touch"),
]


@dataclass
class DraftedMessage:
    variant_label: str
    subject_line: str | None  # only for email
    message_body: str


# ---------------------------------------------------------------------------
# Mock drafts (deterministic, for dev/test)
# ---------------------------------------------------------------------------


def _mock_drafts(
    contact: Contact,
    profile: ConnectorProfile | None,
    match_result: MatchResult | None,
    tone: str,
    channel: str,
) -> list[DraftedMessage]:
    """Generate deterministic mock intro messages."""
    contact_first = contact.first_name or contact.full_name.split()[0]
    contact_title = contact.current_title or "professional"
    contact_company = contact.current_company or "your company"

    match_context = ""
    if match_result and match_result.match_reasoning:
        match_context = f" {match_result.match_reasoning}."

    is_linkedin = channel == "linkedin"
    drafts: list[DraftedMessage] = []

    # --- Direct variant ---
    if is_linkedin:
        body = (
            f"Hi {contact_first}, I came across your profile as {contact_title} "
            f"at {contact_company} and would love to connect. "
            f"I'm exploring opportunities in this space and think we could "
            f"have a valuable conversation."
        )
        if len(body) > LINKEDIN_CHAR_LIMIT:
            body = body[: LINKEDIN_CHAR_LIMIT - 3] + "..."
        drafts.append(
            DraftedMessage(
                variant_label="direct",
                subject_line=None,
                message_body=body,
            )
        )
    else:
        drafts.append(
            DraftedMessage(
                variant_label="direct",
                subject_line=f"Quick intro — connecting on {contact_company}",
                message_body=(
                    f"Hi {contact_first},\n\n"
                    f"I'm reaching out because I noticed you're {contact_title} "
                    f"at {contact_company}.{match_context}\n\n"
                    f"I'd love to set up a brief call to discuss how we might "
                    f"collaborate.\n\n"
                    f"Best regards"
                ),
            )
        )

    # --- Mutual-interest variant ---
    shared = ""
    industry = (profile.industry if profile else None) or "tech"
    if profile and profile.current_company and contact.current_company:
        shared = f"As someone also in the {industry} space, "
    if is_linkedin:
        body = (
            f"Hi {contact_first}, {shared}I've been following the work "
            f"at {contact_company}. Would love to exchange ideas on "
            f"what you're building."
        )
        if len(body) > LINKEDIN_CHAR_LIMIT:
            body = body[: LINKEDIN_CHAR_LIMIT - 3] + "..."
        drafts.append(
            DraftedMessage(
                variant_label="mutual-interest",
                subject_line=None,
                message_body=body,
            )
        )
    else:
        drafts.append(
            DraftedMessage(
                variant_label="mutual-interest",
                subject_line=f"Shared interest in {industry}",
                message_body=(
                    f"Hi {contact_first},\n\n"
                    f"{shared}I've been impressed by what {contact_company} is doing. "
                    f"{match_context}\n\n"
                    f"Would you be open to a 15-minute chat? I think we could "
                    f"find some interesting overlap.\n\n"
                    f"Cheers"
                ),
            )
        )

    # --- Casual variant ---
    if is_linkedin:
        body = (
            f"Hey {contact_first}! Saw your work at {contact_company} "
            f"and thought it'd be great to connect. Always keen to meet "
            f"folks doing interesting things in the space."
        )
        if len(body) > LINKEDIN_CHAR_LIMIT:
            body = body[: LINKEDIN_CHAR_LIMIT - 3] + "..."
        drafts.append(
            DraftedMessage(
                variant_label="casual",
                subject_line=None,
                message_body=body,
            )
        )
    else:
        drafts.append(
            DraftedMessage(
                variant_label="casual",
                subject_line=f"Hey from a fellow {industry} person",
                message_body=(
                    f"Hey {contact_first},\n\n"
                    f"Hope this isn't too random! I came across your profile and "
                    f"thought it'd be cool to connect. {match_context}\n\n"
                    f"No pressure — just thought a quick chat could be fun.\n\n"
                    f"Cheers"
                ),
            )
        )

    return drafts


# ---------------------------------------------------------------------------
# Real Claude API
# ---------------------------------------------------------------------------


def _build_prompt(
    contact: Contact,
    profile: ConnectorProfile | None,
    match_result: MatchResult | None,
    tone: str,
    channel: str,
) -> str:
    """Build the Claude prompt for intro message generation."""
    user_info = "Unknown user"
    if profile:
        parts = []
        if profile.current_title:
            parts.append(f"Title: {profile.current_title}")
        if profile.current_company:
            parts.append(f"Company: {profile.current_company}")
        if profile.industry:
            parts.append(f"Industry: {profile.industry}")
        if profile.location:
            parts.append(f"Location: {profile.location}")
        if profile.bio_summary:
            parts.append(f"Bio: {profile.bio_summary}")
        user_info = "\n".join(parts) if parts else "No profile details"

    contact_info_parts = [f"Name: {contact.full_name}"]
    if contact.current_title:
        contact_info_parts.append(f"Title: {contact.current_title}")
    if contact.current_company:
        contact_info_parts.append(f"Company: {contact.current_company}")
    if contact.location:
        contact_info_parts.append(f"Location: {contact.location}")
    contact_info = "\n".join(contact_info_parts)

    match_info = ""
    if match_result:
        match_info = f"\nMatch context: {match_result.match_reasoning}"

    channel_instruction = ""
    if channel == "linkedin":
        channel_instruction = (
            f"\nIMPORTANT: LinkedIn connection request messages must be "
            f"under {LINKEDIN_CHAR_LIMIT} characters. Do NOT include a subject line."
        )
    else:
        channel_instruction = (
            "\nThis is for email. Include a subject line for each variant."
        )

    return f"""You are a networking and sales communication expert. Generate 3 intro message variants for the user to send to this contact.

SENDER (the user):
{user_info}

RECIPIENT (the contact):
{contact_info}
{match_info}

CHANNEL: {channel}
TONE: {tone}
{channel_instruction}

Generate exactly 3 variants:
1. "direct" — Straightforward professional ask
2. "mutual-interest" — Lead with shared context or mutual interest
3. "casual" — Lighter, conversational touch

Return a JSON array:
[{{"variant_label": "direct", "subject_line": "..." or null, "message_body": "..."}}]

Return ONLY the JSON array, no other text."""


async def _call_claude_api(
    contact: Contact,
    profile: ConnectorProfile | None,
    match_result: MatchResult | None,
    tone: str,
    channel: str,
) -> list[DraftedMessage]:
    """Call the real Claude API for intro message generation."""
    import anthropic

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    prompt = _build_prompt(contact, profile, match_result, tone, channel)

    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0]

    parsed = json.loads(raw)

    results: list[DraftedMessage] = []
    for item in parsed:
        body = item["message_body"]
        # Enforce LinkedIn char limit
        if channel == "linkedin" and len(body) > LINKEDIN_CHAR_LIMIT:
            body = body[: LINKEDIN_CHAR_LIMIT - 3] + "..."
        results.append(
            DraftedMessage(
                variant_label=item["variant_label"],
                subject_line=item.get("subject_line"),
                message_body=body,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def draft_intro(
    contact: Contact,
    connector_profile: ConnectorProfile | None,
    match_result: MatchResult | None,
    tone: str = "professional",
    channel: str = "linkedin",
) -> list[DraftedMessage]:
    """Generate 2-3 intro message variants for a contact.

    Uses mock mode when AI_MOCK_MODE=true, real Claude API otherwise.
    """
    if settings.AI_MOCK_MODE:
        return _mock_drafts(contact, connector_profile, match_result, tone, channel)

    return await _call_claude_api(
        contact, connector_profile, match_result, tone, channel
    )
