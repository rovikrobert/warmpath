"""AI-powered intro message drafting service.

Generates 3 message variants for reaching out to a contact.
Uses the Anthropic Claude API in production, deterministic mock in dev/test.
"""

import json
import logging
from dataclasses import dataclass

import anthropic

from app.config import settings
from app.models.contact import Contact
from app.models.match_result import MatchResult
from app.models.user import ConnectorProfile

logger = logging.getLogger(__name__)

LINKEDIN_CHAR_LIMIT = 300
CLAUDE_MODEL = "claude-sonnet-4-20250514"

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


@dataclass
class IntroTokenUsage:
    input_tokens: int
    output_tokens: int


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
    # --- Sender (connector) profile ---
    if profile:
        sender_parts = []
        if profile.current_title:
            sender_parts.append(f"Title: {profile.current_title}")
        if profile.current_company:
            sender_parts.append(f"Company: {profile.current_company}")
        if profile.industry:
            sender_parts.append(f"Industry: {profile.industry}")
        if profile.location:
            sender_parts.append(f"Location: {profile.location}")
        if profile.bio_summary:
            sender_parts.append(f"Bio: {profile.bio_summary}")
        sender_info = "\n".join(sender_parts) if sender_parts else "No profile details"
    else:
        sender_info = "No profile available — write as a generic professional"

    # --- Recipient (contact) ---
    contact_parts = [f"Name: {contact.full_name}"]
    if contact.current_title:
        contact_parts.append(f"Title: {contact.current_title}")
    if contact.current_company:
        contact_parts.append(f"Company: {contact.current_company}")
    if contact.location:
        contact_parts.append(f"Location: {contact.location}")
    contact_info = "\n".join(contact_parts)

    # --- Match context ---
    match_info = ""
    if match_result and match_result.match_reasoning:
        match_info = f"\nWhy this contact was matched: {match_result.match_reasoning}"

    # --- Channel-specific instructions ---
    if channel == "linkedin":
        channel_instruction = (
            f"\nCHANNEL: LinkedIn connection request"
            f"\n- Each message MUST be under {LINKEDIN_CHAR_LIMIT} characters"
            f"\n- Do NOT include a subject line (set subject_line to null)"
            f"\n- Keep it concise and personal — LinkedIn messages are short"
        )
    else:
        channel_instruction = (
            "\nCHANNEL: Email"
            "\n- Include a compelling subject line for each variant"
            "\n- Subject lines should be short (under 60 chars), not clickbaity"
            "\n- Body can be 3-5 sentences"
        )

    return f"""You are a networking and warm intro expert. Write 3 intro message variants that the sender can use to reach out to this contact.

SENDER (the person sending the message):
{sender_info}

RECIPIENT (the contact being reached out to):
{contact_info}
{match_info}

TONE: {tone}
{channel_instruction}

Write exactly 3 variants:
1. "direct" — Lead with a clear reason for reaching out. Reference the sender's role/company and why connecting makes sense. Be specific, not generic.
2. "mutual-interest" — Find a shared thread (industry, company type, location, mutual challenge). Make it feel like a natural connection, not a sales pitch.
3. "casual" — Conversational and low-pressure. Acknowledge their work genuinely. End with an easy ask.

Guidelines:
- Use the sender's profile to position them credibly (mention their company/role when relevant)
- Reference specific details about the recipient (their title, company) — never be generic
- Avoid cliches like "I'd love to pick your brain" or "synergies"
- Don't be sycophantic — be genuine and direct
- Each variant should feel distinct in approach, not just rewording

Return a JSON array with exactly 3 objects:
[{{"variant_label": "direct", "subject_line": "..." or null, "message_body": "..."}}]

Return ONLY the JSON array. No markdown fences, no explanation."""


async def _call_claude_api(
    contact: Contact,
    profile: ConnectorProfile | None,
    match_result: MatchResult | None,
    tone: str,
    channel: str,
) -> tuple[list[DraftedMessage], IntroTokenUsage]:
    """Call the real Claude API for intro message generation."""
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    prompt = _build_prompt(contact, profile, match_result, tone, channel)

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    usage = IntroTokenUsage(
        input_tokens=message.usage.input_tokens,
        output_tokens=message.usage.output_tokens,
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0].strip()

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

    return results, usage


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
    """Generate 3 intro message variants for a contact.

    Uses mock mode when AI_MOCK_MODE=true, real Claude API otherwise.
    """
    if settings.AI_MOCK_MODE:
        return _mock_drafts(contact, connector_profile, match_result, tone, channel)

    try:
        drafts, usage = await _call_claude_api(
            contact, connector_profile, match_result, tone, channel
        )
        logger.info(
            "Intro drafted for %s (tokens: %d in / %d out)",
            contact.full_name,
            usage.input_tokens,
            usage.output_tokens,
        )
        return drafts
    except anthropic.APIError as exc:
        logger.error(
            "Claude API error drafting intro for %s: %s", contact.full_name, exc
        )
        return _mock_drafts(contact, connector_profile, match_result, tone, channel)
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.error("Failed to parse Claude intro response: %s", exc)
        return _mock_drafts(contact, connector_profile, match_result, tone, channel)
