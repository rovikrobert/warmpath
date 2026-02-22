"""Culturally-aware referral request drafting service.

Generates multi-step message sequences for requesting employee referrals.
The message structure is driven by cultural context from the AI matcher:
- direct_ask  → 3 variant choices (user picks one)
- reconnect + ask → 2 sequential messages (sent days apart)
- reconnect + explore + ask → 3 sequential messages

Uses the Anthropic Claude API in production, deterministic mock in dev/test.
"""

import json
import logging
from dataclasses import dataclass

from app.utils.performance import timed

import anthropic

from app.config import settings
from app.models.contact import Contact
from app.models.job import JobOpening
from app.models.match_result import MatchResult
from app.models.user import ConnectorProfile

logger = logging.getLogger(__name__)

LINKEDIN_CHAR_LIMIT = 300
CLAUDE_MODEL = settings.CLAUDE_MODEL


@dataclass
class DraftedMessage:
    variant_label: str  # "confident", "value-led", "casual" OR "only"
    subject_line: str | None  # only for email
    message_body: str
    sequence_step: int  # 1, 2, 3
    step_label: str  # "referral_ask", "reconnect", "explore"
    send_after_days: int  # 0, 3, 5, 10
    coaching_notes: str  # advice for the user


@dataclass
class IntroTokenUsage:
    input_tokens: int
    output_tokens: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_cultural_context(match_result: MatchResult | None) -> dict:
    """Extract cultural context from match result, with safe defaults."""
    if match_result and match_result.cultural_context:
        ctx = match_result.cultural_context
        return {
            "message_sequence": ctx.get("message_sequence", ["direct_ask"]),
            "approach_style": ctx.get("approach_style", "direct"),
            "cultural_notes": ctx.get("cultural_notes", ""),
            "warm_up_suggested": ctx.get("warm_up_suggested", False),
        }
    return {
        "message_sequence": ["direct_ask"],
        "approach_style": "direct",
        "cultural_notes": "",
        "warm_up_suggested": False,
    }


def _job_label(job_opening: JobOpening | None, contact_company: str) -> str:
    """Build a human-readable job label like 'Senior Engineer at Acme Corp'."""
    if job_opening and job_opening.title:
        company = contact_company or "their company"
        return f"{job_opening.title} at {company}"
    return f"a role at {contact_company}" if contact_company else "an open role"


def _truncate_linkedin(body: str) -> str:
    if len(body) > LINKEDIN_CHAR_LIMIT:
        return body[: LINKEDIN_CHAR_LIMIT - 3] + "..."
    return body


def _build_reconnect_body(
    contact_first: str,
    contact_title: str,
    contact_company: str,
    rel_type: str | None,
    how_know: str | None,
    is_linkedin: bool,
) -> str:
    """Build a reconnect message body, personalized with relationship context."""
    if how_know:
        # Use the specific shared history from how_you_know
        if is_linkedin:
            return _truncate_linkedin(
                f"Hi {contact_first}, it's been a while! I fondly remember "
                f"our time — {how_know}. I see you're now {contact_title} at "
                f"{contact_company}. Would love to reconnect."
            )
        return (
            f"Hi {contact_first},\n\n"
            f"It's been a while since we connected. I was thinking back to "
            f"our shared history — {how_know}. I see you're now {contact_title} "
            f"at {contact_company} — congratulations on the role.\n\n"
            f"I'd love to catch up and hear how things are going for you.\n\n"
            f"Best regards"
        )

    if rel_type == "former_colleague":
        if is_linkedin:
            return _truncate_linkedin(
                f"Hi {contact_first}, it's been a while since we worked together! "
                f"I see you're now {contact_title} at {contact_company}. "
                f"Would love to reconnect and hear how things are going."
            )
        return (
            f"Hi {contact_first},\n\n"
            f"It's been a while since we were colleagues. I see you're now "
            f"{contact_title} at {contact_company} — congratulations on the role.\n\n"
            f"I'd love to catch up and hear how things are going for you.\n\n"
            f"Best regards"
        )

    if rel_type == "former_manager":
        if is_linkedin:
            return _truncate_linkedin(
                f"Hi {contact_first}, it's been a while! I learned so much "
                f"working with you. I see you're now {contact_title} at "
                f"{contact_company}. Would love to reconnect."
            )
        return (
            f"Hi {contact_first},\n\n"
            f"It's been a while since we worked together. I learned a great deal "
            f"under your leadership and I see you're now {contact_title} at "
            f"{contact_company} — congratulations.\n\n"
            f"I'd love to catch up and hear how things are going for you.\n\n"
            f"Best regards"
        )

    # Generic reconnect (no relationship context)
    if is_linkedin:
        return _truncate_linkedin(
            f"Hi {contact_first}, it's been a while! I see you're doing great "
            f"as {contact_title} at {contact_company}. I'd love to reconnect "
            f"and hear how things are going."
        )
    return (
        f"Hi {contact_first},\n\n"
        f"It's been a while since we connected. I see you're now "
        f"{contact_title} at {contact_company} — congratulations on the role.\n\n"
        f"I'd love to catch up and hear how things are going for you.\n\n"
        f"Best regards"
    )


# ---------------------------------------------------------------------------
# Mock drafts — deterministic, for dev/test
# ---------------------------------------------------------------------------


def _mock_referral_drafts(
    contact: Contact,
    profile: ConnectorProfile | None,
    match_result: MatchResult | None,
    job_opening: JobOpening | None,
    channel: str,
) -> list[DraftedMessage]:
    """Generate deterministic mock referral request messages."""
    contact_first = contact.first_name or contact.full_name.split()[0]
    contact_company = contact.current_company or "your company"
    contact_title = contact.current_title or "professional"

    ctx = _extract_cultural_context(match_result)
    sequence = ctx["message_sequence"]
    cultural_notes = ctx["cultural_notes"]

    job = _job_label(job_opening, contact_company)
    is_linkedin = channel == "linkedin"

    sender_title = (profile.current_title if profile else None) or "a professional"
    # Use headline as a richer sender description when available
    sender_headline = getattr(profile, "headline", None) if profile else None
    sender_desc = sender_headline or sender_title

    # Relationship context for reconnect messages
    rel_type = getattr(contact, "relationship_type", None)
    how_know = getattr(contact, "how_you_know", None)

    drafts: list[DraftedMessage] = []

    if sequence == ["direct_ask"]:
        # 3 variants of a single referral ask — user picks one
        coaching = (
            f"Direct approach recommended. {cultural_notes}"
            if cultural_notes
            else "Direct approach works well here. Be specific about the role and why you're a fit."
        )

        # --- Confident variant ---
        if is_linkedin:
            body = _truncate_linkedin(
                f"Hi {contact_first}, I see you're {contact_title} at {contact_company}. "
                f"I'm interested in {job} and think my background as {sender_desc} "
                f"would be a great fit. Would you be open to referring me?"
            )
        else:
            body = (
                f"Hi {contact_first},\n\n"
                f"I noticed you're {contact_title} at {contact_company}. "
                f"I'm actively looking at {job} and believe my experience as "
                f"{sender_desc} makes me a strong candidate.\n\n"
                f"Would you be open to putting in a referral? I'd be happy to "
                f"share my resume and chat about the role.\n\n"
                f"Best regards"
            )
        drafts.append(
            DraftedMessage(
                variant_label="confident",
                subject_line=None if is_linkedin else f"Referral request — {job}",
                message_body=body,
                sequence_step=1,
                step_label="referral_ask",
                send_after_days=0,
                coaching_notes=coaching,
            )
        )

        # --- Value-led variant ---
        if is_linkedin:
            body = _truncate_linkedin(
                f"Hi {contact_first}, I've been following {contact_company}'s work "
                f"and I'm excited about {job}. As {sender_desc}, I think I could "
                f"add real value. Any chance you'd refer me?"
            )
        else:
            body = (
                f"Hi {contact_first},\n\n"
                f"I've been following what {contact_company} is building and I'm "
                f"genuinely excited about {job}. With my background as {sender_desc}, "
                f"I believe I could contribute meaningfully to the team.\n\n"
                f"Would you feel comfortable referring me? Happy to send over my "
                f"resume for context.\n\n"
                f"Thanks"
            )
        drafts.append(
            DraftedMessage(
                variant_label="value-led",
                subject_line=None
                if is_linkedin
                else f"Interested in {job} — referral?",
                message_body=body,
                sequence_step=1,
                step_label="referral_ask",
                send_after_days=0,
                coaching_notes=coaching,
            )
        )

        # --- Casual variant ---
        if is_linkedin:
            body = _truncate_linkedin(
                f"Hey {contact_first}! I'm looking at {job} and saw you're at "
                f"{contact_company}. Would you be up for putting in a referral? "
                f"Happy to share more context."
            )
        else:
            body = (
                f"Hey {contact_first},\n\n"
                f"Hope you're doing well! I'm exploring new opportunities and "
                f"{job} really caught my eye. Since you're at {contact_company}, "
                f"I figured I'd ask — any chance you'd be open to referring me?\n\n"
                f"No worries if not, but would love to chat either way.\n\n"
                f"Cheers"
            )
        drafts.append(
            DraftedMessage(
                variant_label="casual",
                subject_line=None
                if is_linkedin
                else f"Quick ask about {contact_company}",
                message_body=body,
                sequence_step=1,
                step_label="referral_ask",
                send_after_days=0,
                coaching_notes=coaching,
            )
        )

    elif sequence == ["reconnect", "ask"]:
        # 2 sequential messages: reconnect first, then referral ask
        reconnect_coaching = (
            f"Formal-indirect approach. {cultural_notes} "
            "Re-establish the relationship before asking for the referral."
            if cultural_notes
            else "Re-establish the connection first. Reference shared history or mutual context."
        )
        ask_coaching = (
            "Wait a few days after reconnecting. Once they've responded, "
            "transition to your referral ask naturally."
        )

        # Step 1: Reconnect — personalize with relationship context when available
        reconnect_body = _build_reconnect_body(
            contact_first,
            contact_title,
            contact_company,
            rel_type,
            how_know,
            is_linkedin,
        )
        drafts.append(
            DraftedMessage(
                variant_label="only",
                subject_line=None
                if is_linkedin
                else f"Great to reconnect, {contact_first}",
                message_body=reconnect_body,
                sequence_step=1,
                step_label="reconnect",
                send_after_days=0,
                coaching_notes=reconnect_coaching,
            )
        )

        # Step 2: Referral ask
        if is_linkedin:
            body = _truncate_linkedin(
                f"Thanks for reconnecting, {contact_first}! I'm currently "
                f"exploring {job}. Given your experience at {contact_company}, "
                f"would you consider referring me?"
            )
        else:
            body = (
                f"Hi {contact_first},\n\n"
                f"Thanks for catching up! I wanted to mention — I'm actively "
                f"interested in {job}. With my background as {sender_desc}, "
                f"I think it could be a great fit.\n\n"
                f"Would you be open to putting in a referral? I can send over "
                f"my resume anytime.\n\n"
                f"Thanks"
            )
        drafts.append(
            DraftedMessage(
                variant_label="only",
                subject_line=None if is_linkedin else f"Following up — {job}",
                message_body=body,
                sequence_step=2,
                step_label="referral_ask",
                send_after_days=3,
                coaching_notes=ask_coaching,
            )
        )

    elif sequence == ["reconnect", "explore", "ask"]:
        # 3 sequential messages: reconnect → explore → referral ask
        reconnect_coaching = (
            f"Relationship-first approach. {cultural_notes} "
            "Start by reconnecting genuinely — no mention of jobs yet."
            if cultural_notes
            else "Start by rebuilding the relationship. Show genuine interest in their work."
        )
        explore_coaching = (
            "Show interest in their work and the company. "
            "Ask about the team culture and what they enjoy. "
            "This builds rapport before the ask."
        )
        ask_coaching = (
            "Now that rapport is re-established, make your referral request. "
            "Reference what they shared about the company to show you listened."
        )

        # Step 1: Reconnect — personalize with relationship context when available
        reconnect_body = _build_reconnect_body(
            contact_first,
            contact_title,
            contact_company,
            rel_type,
            how_know,
            is_linkedin,
        )
        drafts.append(
            DraftedMessage(
                variant_label="only",
                subject_line=None if is_linkedin else f"Catching up, {contact_first}",
                message_body=reconnect_body,
                sequence_step=1,
                step_label="reconnect",
                send_after_days=0,
                coaching_notes=reconnect_coaching,
            )
        )

        # Step 2: Explore
        if is_linkedin:
            body = _truncate_linkedin(
                f"Great to reconnect! I'm curious — how's the team at "
                f"{contact_company}? I've been impressed by what they're "
                f"building."
            )
        else:
            body = (
                f"Hi {contact_first},\n\n"
                f"Thanks for catching up! I've been following {contact_company}'s "
                f"growth and I'm really impressed. How are you finding the "
                f"team culture? What's been the most exciting project?\n\n"
                f"Cheers"
            )
        drafts.append(
            DraftedMessage(
                variant_label="only",
                subject_line=None
                if is_linkedin
                else f"Curious about {contact_company}",
                message_body=body,
                sequence_step=2,
                step_label="explore",
                send_after_days=5,
                coaching_notes=explore_coaching,
            )
        )

        # Step 3: Referral ask
        if is_linkedin:
            body = _truncate_linkedin(
                f"Thanks for sharing about {contact_company}, {contact_first}! "
                f"I'm very interested in {job}. Would you be open to referring me? "
                f"Happy to send my resume."
            )
        else:
            body = (
                f"Hi {contact_first},\n\n"
                f"Really appreciate you sharing about life at {contact_company}. "
                f"It sounds like an amazing team. I've been looking at {job} and "
                f"I think my experience as {sender_desc} would be a strong fit.\n\n"
                f"Would you be comfortable putting in a referral for me? "
                f"I can share my resume and any other details that would help.\n\n"
                f"Thanks so much"
            )
        drafts.append(
            DraftedMessage(
                variant_label="only",
                subject_line=None if is_linkedin else f"Referral request — {job}",
                message_body=body,
                sequence_step=3,
                step_label="referral_ask",
                send_after_days=10,
                coaching_notes=ask_coaching,
            )
        )

    return drafts


# ---------------------------------------------------------------------------
# Real Claude API
# ---------------------------------------------------------------------------


def _build_referral_prompt(
    contact: Contact,
    profile: ConnectorProfile | None,
    match_result: MatchResult | None,
    job_opening: JobOpening | None,
    channel: str,
) -> str:
    """Build the Claude prompt for referral request message generation."""
    ctx = _extract_cultural_context(match_result)
    sequence = ctx["message_sequence"]
    approach = ctx["approach_style"]
    cultural_notes = ctx["cultural_notes"]

    # --- Sender info ---
    if profile:
        sender_parts = []
        if profile.current_title:
            sender_parts.append(f"Title: {profile.current_title}")
        if profile.current_company:
            sender_parts.append(f"Company: {profile.current_company}")
        if getattr(profile, "headline", None):
            sender_parts.append(f"Headline: {profile.headline}")
        if profile.industry:
            sender_parts.append(f"Industry: {profile.industry}")
        if profile.location:
            sender_parts.append(f"Location: {profile.location}")
        if profile.bio_summary:
            sender_parts.append(f"Bio: {profile.bio_summary}")
        if getattr(profile, "work_history", None):
            history_str = ", ".join(
                f"{e.get('company', '?')} ({e.get('title', '')})"
                for e in profile.work_history[:5]
            )
            sender_parts.append(f"Work history: {history_str}")
        if getattr(profile, "github_url", None):
            sender_parts.append(f"GitHub: {profile.github_url}")
        if getattr(profile, "portfolio_url", None):
            sender_parts.append(f"Portfolio: {profile.portfolio_url}")
        sender_info = "\n".join(sender_parts) if sender_parts else "No profile details"
    else:
        sender_info = "No profile available — write as a generic professional"

    # --- Recipient info ---
    contact_parts = [f"Name: {contact.full_name}"]
    if contact.current_title:
        contact_parts.append(f"Title: {contact.current_title}")
    if contact.current_company:
        contact_parts.append(f"Company: {contact.current_company}")
    if contact.location:
        contact_parts.append(f"Location: {contact.location}")
    if getattr(contact, "relationship_type", None):
        contact_parts.append(f"Relationship: {contact.relationship_type}")
    if getattr(contact, "how_you_know", None):
        contact_parts.append(f"How sender knows them: {contact.how_you_know}")
    contact_info = "\n".join(contact_parts)

    # --- Match context ---
    match_info = ""
    if match_result and match_result.match_reasoning:
        match_info = f"\nWhy this contact was matched: {match_result.match_reasoning}"

    # --- Job opening ---
    job_info = ""
    if job_opening:
        job_parts = [f"Job Title: {job_opening.title}"]
        if job_opening.department:
            job_parts.append(f"Department: {job_opening.department}")
        if job_opening.location:
            job_parts.append(f"Location: {job_opening.location}")
        if job_opening.is_remote:
            job_parts.append("Remote: Yes")
        job_info = "\nTARGET JOB OPENING:\n" + "\n".join(job_parts)

    # --- Channel instructions ---
    if channel == "linkedin":
        channel_instruction = (
            f"\nCHANNEL: LinkedIn message"
            f"\n- Each message MUST be under {LINKEDIN_CHAR_LIMIT} characters"
            f"\n- Do NOT include a subject line (set subject_line to null)"
            f"\n- Keep it concise — LinkedIn messages are short"
        )
    else:
        channel_instruction = (
            "\nCHANNEL: Email"
            "\n- Include a compelling subject line for each message"
            "\n- Subject lines should be short (under 60 chars), not clickbaity"
            "\n- Body can be 3-5 sentences"
        )

    # --- Sequence instructions ---
    if sequence == ["direct_ask"]:
        seq_instruction = """
MESSAGE STRUCTURE: Generate 3 VARIANTS of a single referral request (user picks one).
Each variant should be a different approach but all are direct referral asks.
- variant 1: "confident" — Lead confidently with qualifications and a clear ask
- variant 2: "value-led" — Emphasize the value you'd bring to the team
- variant 3: "casual" — Friendly, low-pressure referral request

All 3 messages should have sequence_step: 1, step_label: "referral_ask", send_after_days: 0."""
    elif sequence == ["reconnect", "ask"]:
        seq_instruction = """
MESSAGE STRUCTURE: Generate 2 SEQUENTIAL messages (sent days apart).
- Message 1: "reconnect" — Re-establish the relationship. Reference shared history. Do NOT mention the job.
  sequence_step: 1, step_label: "reconnect", send_after_days: 0, variant_label: "only"
- Message 2: "referral_ask" — After they respond, transition to the referral request.
  sequence_step: 2, step_label: "referral_ask", send_after_days: 3, variant_label: "only" """
    else:
        seq_instruction = """
MESSAGE STRUCTURE: Generate 3 SEQUENTIAL messages (sent days apart).
- Message 1: "reconnect" — Rebuild the relationship. Show genuine interest. No job mention.
  sequence_step: 1, step_label: "reconnect", send_after_days: 0, variant_label: "only"
- Message 2: "explore" — Ask about their experience at the company. Build rapport.
  sequence_step: 2, step_label: "explore", send_after_days: 5, variant_label: "only"
- Message 3: "referral_ask" — Make the referral request, referencing what they shared.
  sequence_step: 3, step_label: "referral_ask", send_after_days: 10, variant_label: "only" """

    return f"""You are a career networking coach specializing in culturally-aware referral requests. The sender wants an employee referral from this contact.

SENDER (the person requesting the referral):
{sender_info}

RECIPIENT (the contact who can refer them):
{contact_info}
{match_info}
{job_info}

CULTURAL CONTEXT:
- Approach style: {approach}
- Cultural notes: {cultural_notes}
{channel_instruction}
{seq_instruction}

COACHING NOTES: For each message, include a "coaching_notes" field with practical advice on tone, timing, and what to watch for. Reference the cultural context.

Guidelines:
- These are REFERRAL REQUESTS, not networking messages. The goal is to get referred for a specific role.
- Be specific about the job/company — never generic "let's connect" language
- Reference the sender's relevant experience to justify the referral
- Use the recipient's name and company naturally
- Avoid cliches like "pick your brain" or "synergies"
- Be genuine and respectful — you're asking for a favor

Return a JSON array of objects:
[{{"variant_label": "...", "subject_line": "..." or null, "message_body": "...", "sequence_step": N, "step_label": "...", "send_after_days": N, "coaching_notes": "..."}}]

Return ONLY the JSON array. No markdown fences, no explanation."""


async def _call_claude_api(
    contact: Contact,
    profile: ConnectorProfile | None,
    match_result: MatchResult | None,
    job_opening: JobOpening | None,
    channel: str,
) -> tuple[list[DraftedMessage], IntroTokenUsage]:
    """Call the real Claude API for referral message generation."""
    from app.utils.anthropic_client import get_async_client
    from app.utils.rate_limiter import acquire_slot, release_slot

    client = get_async_client()
    prompt = _build_referral_prompt(
        contact, profile, match_result, job_opening, channel
    )

    used_redis = await acquire_slot(
        "anthropic", max_concurrent=settings.ANTHROPIC_MAX_CONCURRENT
    )
    try:
        message = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
    finally:
        await release_slot("anthropic", used_redis)

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
        if channel == "linkedin" and len(body) > LINKEDIN_CHAR_LIMIT:
            body = body[: LINKEDIN_CHAR_LIMIT - 3] + "..."
        results.append(
            DraftedMessage(
                variant_label=item["variant_label"],
                subject_line=item.get("subject_line"),
                message_body=body,
                sequence_step=item["sequence_step"],
                step_label=item["step_label"],
                send_after_days=item["send_after_days"],
                coaching_notes=item.get("coaching_notes", ""),
            )
        )

    return results, usage


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _append_nh_recruitment_ps(messages: list[DraftedMessage], contact: Contact) -> None:
    """Append a P.S. to the last message encouraging NH recruitment."""
    if messages:
        last_msg = messages[-1]
        company = contact.current_company or "your company"
        ps = (
            f"\n\nP.S. If you know others at {company} who might be open to "
            f"helping people in their network get referred, I'd love an intro."
        )
        last_msg.message_body += ps


@timed("intro_draft")
async def draft_referral_request(
    contact: Contact,
    user_profile: ConnectorProfile | None,
    match_result: MatchResult | None,
    job_opening: JobOpening | None = None,
    channel: str = "linkedin",
    include_nh_recruitment: bool = False,
) -> list[DraftedMessage]:
    """Generate referral request messages for a contact.

    Message structure is driven by the cultural context in match_result:
    - direct_ask  → 3 variant choices at step 1
    - reconnect + ask → 2 sequential messages
    - reconnect + explore + ask → 3 sequential messages

    Uses mock mode when AI_MOCK_MODE=true, real Claude API otherwise.

    Args:
        include_nh_recruitment: When True, appends a P.S. to the last message
            encouraging the contact to refer others to the platform.
    """
    if settings.AI_MOCK_MODE:
        messages = _mock_referral_drafts(
            contact, user_profile, match_result, job_opening, channel
        )
        if include_nh_recruitment:
            _append_nh_recruitment_ps(messages, contact)
        return messages

    import asyncio

    max_retries = 2
    for attempt in range(max_retries):
        try:
            drafts, usage = await _call_claude_api(
                contact, user_profile, match_result, job_opening, channel
            )
            logger.info(
                "Referral drafts for contact %s (tokens: %d in / %d out)",
                contact.id,
                usage.input_tokens,
                usage.output_tokens,
            )
            if include_nh_recruitment:
                _append_nh_recruitment_ps(drafts, contact)
            return drafts
        except anthropic.RateLimitError:
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                logger.warning(
                    "Claude rate limit hit (intro drafter), retrying in %ds...", wait
                )
                await asyncio.sleep(wait)
            else:
                logger.error("Claude rate limit persists, falling back to mock drafts")
                messages = _mock_referral_drafts(
                    contact, user_profile, match_result, job_opening, channel
                )
                if include_nh_recruitment:
                    _append_nh_recruitment_ps(messages, contact)
                return messages
        except anthropic.APIError as exc:
            logger.error(
                "Claude API error drafting referral for contact %s: %s", contact.id, exc
            )
            messages = _mock_referral_drafts(
                contact, user_profile, match_result, job_opening, channel
            )
            if include_nh_recruitment:
                _append_nh_recruitment_ps(messages, contact)
            return messages
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.error("Failed to parse Claude referral response: %s", exc)
            messages = _mock_referral_drafts(
                contact, user_profile, match_result, job_opening, channel
            )
            if include_nh_recruitment:
                _append_nh_recruitment_ps(messages, contact)
            return messages
    # Unreachable, but satisfy type checker
    messages = _mock_referral_drafts(
        contact, user_profile, match_result, job_opening, channel
    )
    if include_nh_recruitment:
        _append_nh_recruitment_ps(messages, contact)
    return messages
