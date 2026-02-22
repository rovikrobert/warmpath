"""Email engagement service — triggered lifecycle emails.

Handles welcome emails, activation nudges, operational reminders,
weekly digests, and re-engagement campaigns. Emails are deduped via
the email_campaign_logs table (one send per user per email_type per day).

Respects marketing_opt_out on the User model.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.contact import CsvUpload
from app.models.email_campaign import EmailCampaignLog
from app.models.enrichment import UsageLog
from app.models.marketplace import IntroFacilitation, NetworkSharingPreferences
from app.models.search_request import SearchRequest
from app.models.user import User
from app.services.email_service import _send_email

logger = logging.getLogger(__name__)

APP_URL = settings.FRONTEND_URL


# ---------------------------------------------------------------------------
# Dedup helper
# ---------------------------------------------------------------------------


async def _already_sent(db: AsyncSession, user_id: uuid.UUID, email_type: str) -> bool:
    """Check if this email type was already sent to this user today."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    result = await db.execute(
        select(EmailCampaignLog.id).where(
            EmailCampaignLog.user_id == user_id,
            EmailCampaignLog.email_type == email_type,
            EmailCampaignLog.sent_date == today,
        )
    )
    return result.scalar_one_or_none() is not None


async def _record_send(
    db: AsyncSession,
    user_id: uuid.UUID,
    email_type: str,
    external_id: str | None = None,
) -> None:
    """Record that an email was sent, optionally with Resend message ID."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Ensure external_id is a real string (not a mock object)
    eid = str(external_id) if isinstance(external_id, str) else None
    db.add(
        EmailCampaignLog(
            user_id=user_id,
            email_type=email_type,
            sent_date=today,
            external_id=eid,
        )
    )
    await db.flush()


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------


def _base_style() -> str:
    return (
        'font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;'
        " max-width: 500px; margin: 0 auto; color: #1f2937; padding: 0 16px;"
    )


def _preheader_html(text: str) -> str:
    """Hidden preheader text shown in email client preview pane."""
    return (
        '<div style="display:none;font-size:1px;color:#ffffff;line-height:1px;'
        f'max-height:0px;max-width:0px;opacity:0;overflow:hidden;">{text}</div>'
    )


def _agent_signoff(intent: str | None = None) -> str:
    """Return ops agent persona signoff based on user intent."""
    if intent in ("sha[RESEND_KEY_REDACTED]",):
        return "Treb, WarmPath Ops"
    return "Keevs, WarmPath Ops"


def _footer_html() -> str:
    return f"""\
<div style="margin: 32px 0 0; padding: 16px 0; border-top: 1px solid #e5e7eb; text-align: center;">
  <p style="margin: 0 0 4px; color: #6b7280; font-size: 12px;">
    <strong>WarmPath</strong> — Helping you get referred, not rejected.
  </p>
  <p style="margin: 0; color: #6b7280; font-size: 11px;">
    <a href="{APP_URL}/settings/privacy" style="color: #6b7280; text-decoration: none; display: inline-block; padding: 8px 4px;">Unsubscribe</a> &middot;
    <a href="{APP_URL}/privacy" style="color: #6b7280; text-decoration: none; display: inline-block; padding: 8px 4px;">Privacy Policy</a>
  </p>
</div>"""


# ---------------------------------------------------------------------------
# Welcome emails
# ---------------------------------------------------------------------------


async def send_welcome_email_js(user: User, db: AsyncSession) -> bool:
    """Welcome email for job seekers."""
    if user.marketing_opt_out:
        return False
    if await _already_sent(db, user.id, "welcome_js"):
        return False

    first = user.full_name.split()[0] if user.full_name else "there"
    html = f"""\
<div lang="en" dir="ltr" style="{_base_style()}">
  {_preheader_html("Upload your LinkedIn CSV and earn 100 bonus credits")}
  <div style="padding: 24px; background: #f59e0b; background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); border-radius: 12px 12px 0 0; color: #fff; text-align: center;">
    <h1 style="margin: 0 0 4px; font-size: 24px;">Welcome to WarmPath, {first}!</h1>
    <p style="margin: 0; opacity: 0.9;">Your warm path to your next role starts here.</p>
  </div>
  <div style="padding: 24px;">
    <p style="margin: 0 0 16px;">You just got <strong>50 credits</strong> (enough for 10 referral searches). Here's your 3-step plan to land your next role:</p>
    <div style="margin: 0 0 16px; padding: 12px 16px; background: #fef3c7; border-radius: 8px;">
      <strong>Step 1:</strong> Upload your LinkedIn connections (+100 credits)
    </div>
    <div style="margin: 0 0 16px; padding: 12px 16px; background: #fef3c7; border-radius: 8px;">
      <strong>Step 2:</strong> Run your first Smart Search — see who can refer you
    </div>
    <div style="margin: 0 0 16px; padding: 12px 16px; background: #fef3c7; border-radius: 8px;">
      <strong>Step 3:</strong> Request an intro through someone who knows the hiring team
    </div>
    <div style="text-align: center; margin: 24px 0;">
      <a href="{APP_URL}/contacts" style="display: inline-block; padding: 12px 28px; background: #f59e0b; color: #fff; text-decoration: none; border-radius: 8px; font-weight: 600;">Upload My LinkedIn &amp; Earn 100 Credits</a>
    </div>
    <p style="margin: 16px 0 0; font-size: 14px; color: #6b7280;">&mdash; {_agent_signoff("job_seeker")}</p>
  </div>
  {_footer_html()}
</div>"""
    eid = _send_email(user.email, f"Your 50 welcome credits are ready, {first}", html)
    await _record_send(db, user.id, "welcome_js", external_id=eid)
    return True


async def send_welcome_email_nh(user: User, db: AsyncSession) -> bool:
    """Welcome email for network holders."""
    if user.marketing_opt_out:
        return False
    if await _already_sent(db, user.id, "welcome_nh"):
        return False

    first = user.full_name.split()[0] if user.full_name else "there"
    html = f"""\
<div lang="en" dir="ltr" style="{_base_style()}">
  {_preheader_html("Your company's referral bonuses are waiting to be claimed")}
  <div style="padding: 24px; background: #2563eb; background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); border-radius: 12px 12px 0 0; color: #fff; text-align: center;">
    <h1 style="margin: 0 0 4px; font-size: 24px;">Welcome to WarmPath, {first}!</h1>
    <p style="margin: 0; opacity: 0.9;">Turn your network into referral bonuses.</p>
  </div>
  <div style="padding: 24px;">
    <p style="margin: 0 0 16px;">Most people leave <strong>$5,000-$10,000/year in unclaimed referral bonuses</strong> on the table. WarmPath sends you pre-qualified candidates so you can claim them.</p>
    <div style="margin: 0 0 16px; padding: 12px 16px; background: #eff6ff; border-radius: 8px;">
      <strong>Step 1:</strong> Upload your LinkedIn connections (+100 credits)
    </div>
    <div style="margin: 0 0 16px; padding: 12px 16px; background: #eff6ff; border-radius: 8px;">
      <strong>Step 2:</strong> Enable marketplace sharing — choose what to share
    </div>
    <div style="margin: 0 0 16px; padding: 12px 16px; background: #eff6ff; border-radius: 8px;">
      <strong>Step 3:</strong> Review intro requests — approve good candidates and earn $2-10K when they get hired
    </div>
    <div style="text-align: center; margin: 24px 0;">
      <a href="{APP_URL}/contacts" style="display: inline-block; padding: 12px 28px; background: #2563eb; color: #fff; text-decoration: none; border-radius: 8px; font-weight: 600;">Upload &amp; Start Earning</a>
    </div>
    <p style="margin: 16px 0 0; font-size: 14px; color: #6b7280;">&mdash; {_agent_signoff("sha[RESEND_KEY_REDACTED]")}</p>
  </div>
  {_footer_html()}
</div>"""
    eid = _send_email(
        user.email,
        f"{first}, $5K+ in referral bonuses — here's how to claim them",
        html,
    )
    await _record_send(db, user.id, "welcome_nh", external_id=eid)
    return True


# ---------------------------------------------------------------------------
# Activation nudges
# ---------------------------------------------------------------------------


async def send_csv_reminder_d1(db: AsyncSession) -> int:
    """Nudge users who signed up 24h ago but haven't uploaded CSV."""
    cutoff_start = datetime.now(timezone.utc) - timedelta(hours=30)
    cutoff_end = datetime.now(timezone.utc) - timedelta(hours=18)

    # Users created 18-30h ago with no CSV upload
    uploaded_subq = select(CsvUpload.user_id).distinct().scalar_subquery()
    result = await db.execute(
        select(User).where(
            User.created_at.between(cutoff_start, cutoff_end),
            User.deleted_at.is_(None),
            User.marketing_opt_out.is_(False),
            User.id.not_in(uploaded_subq),
        )
    )
    users = result.scalars().all()

    # Batch-load already-sent set for today (avoids N+1)
    user_ids = [u.id for u in users]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    already_sent_ids: set[uuid.UUID] = set()
    if user_ids:
        sent_result = await db.execute(
            select(EmailCampaignLog.user_id).where(
                EmailCampaignLog.user_id.in_(user_ids),
                EmailCampaignLog.email_type == "csv_reminder_d1",
                EmailCampaignLog.sent_date == today,
            )
        )
        already_sent_ids = {row[0] for row in sent_result.all()}

    count = 0
    for u in users:
        if u.id in already_sent_ids:
            continue
        first = u.full_name.split()[0] if u.full_name else "there"
        agent = _agent_signoff(u.intent)
        html = f"""\
<div lang="en" dir="ltr" style="{_base_style()}">
  {_preheader_html("It takes 2 minutes to unlock referral paths")}
  <p style="margin: 0 0 16px;">Hi {first},</p>
  <p style="margin: 0 0 16px;">You signed up but haven't uploaded your LinkedIn connections yet. <strong>Without them, we can't show you who in your network (or the marketplace) can get you referred at your target companies.</strong></p>
  <p style="margin: 0 0 16px;">It takes 2 minutes: <a href="https://www.linkedin.com/mypreferences/d/download-my-data" style="color: #2563eb;">Export from LinkedIn</a> &rarr; Upload to WarmPath.</p>
  <div style="margin: 16px 0;">
    <a href="{APP_URL}/contacts" style="display: inline-block; background: #2563eb; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 600;">Upload LinkedIn CSV (2 min)</a>
  </div>
  <p style="margin: 16px 0 0; font-size: 14px; color: #6b7280;">&mdash; {agent}</p>
  {_footer_html()}
</div>"""
        eid = _send_email(
            u.email, "2 minutes to unlock referral paths at your target companies", html
        )
        await _record_send(db, u.id, "csv_reminder_d1", external_id=eid)
        count += 1
    await db.commit()
    logger.info("csv_reminder_d1: sent %d emails", count)
    return count


async def send_csv_reminder_d3(db: AsyncSession) -> int:
    """More urgent nudge — 3 days without CSV upload."""
    cutoff_start = datetime.now(timezone.utc) - timedelta(hours=78)
    cutoff_end = datetime.now(timezone.utc) - timedelta(hours=66)

    uploaded_subq = select(CsvUpload.user_id).distinct().scalar_subquery()
    result = await db.execute(
        select(User).where(
            User.created_at.between(cutoff_start, cutoff_end),
            User.deleted_at.is_(None),
            User.marketing_opt_out.is_(False),
            User.id.not_in(uploaded_subq),
        )
    )
    users = result.scalars().all()

    # Batch-load already-sent set for today (avoids N+1)
    user_ids = [u.id for u in users]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    already_sent_ids: set[uuid.UUID] = set()
    if user_ids:
        sent_result = await db.execute(
            select(EmailCampaignLog.user_id).where(
                EmailCampaignLog.user_id.in_(user_ids),
                EmailCampaignLog.email_type == "csv_reminder_d3",
                EmailCampaignLog.sent_date == today,
            )
        )
        already_sent_ids = {row[0] for row in sent_result.all()}

    count = 0
    for u in users:
        if u.id in already_sent_ids:
            continue
        first = u.full_name.split()[0] if u.full_name else "there"
        agent = _agent_signoff(u.intent)
        html = f"""\
<div lang="en" dir="ltr" style="{_base_style()}">
  {_preheader_html("Reply if you're stuck — we'll help you upload")}
  <p style="margin: 0 0 16px;">Hi {first},</p>
  <p style="margin: 0 0 16px;">Still need to upload? Most users finish in under 2 minutes. Reply to this email if you're stuck — we'll help.</p>
  <div style="margin: 16px 0;">
    <a href="{APP_URL}/contacts" style="display: inline-block; background: #f59e0b; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 600;">Get Help Uploading</a>
  </div>
  <p style="margin: 16px 0 0; font-size: 14px; color: #6b7280;">&mdash; {agent}</p>
  {_footer_html()}
</div>"""
        eid = _send_email(u.email, "Quick question: what's blocking your upload?", html)
        await _record_send(db, u.id, "csv_reminder_d3", external_id=eid)
        count += 1
    await db.commit()
    logger.info("csv_reminder_d3: sent %d emails", count)
    return count


async def send_nh_sharing_reminder_d2(db: AsyncSession) -> int:
    """Nudge network holders who uploaded CSV but haven't enabled sharing."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

    # Users who have CSV uploads but no opt-in
    uploaded_subq = select(CsvUpload.user_id).distinct().scalar_subquery()
    opted_in_subq = (
        select(NetworkSharingPreferences.user_id)
        .where(NetworkSharingPreferences.opt_in_marketplace.is_(True))
        .scalar_subquery()
    )
    result = await db.execute(
        select(User).where(
            User.deleted_at.is_(None),
            User.marketing_opt_out.is_(False),
            User.created_at < cutoff,
            User.id.in_(uploaded_subq),
            User.id.not_in(opted_in_subq),
        )
    )
    users = result.scalars().all()

    # Batch-load already-sent set for today (avoids N+1)
    user_ids = [u.id for u in users]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    already_sent_ids: set[uuid.UUID] = set()
    if user_ids:
        sent_result = await db.execute(
            select(EmailCampaignLog.user_id).where(
                EmailCampaignLog.user_id.in_(user_ids),
                EmailCampaignLog.email_type == "nh_sharing_d2",
                EmailCampaignLog.sent_date == today,
            )
        )
        already_sent_ids = {row[0] for row in sent_result.all()}

    count = 0
    for u in users:
        if u.id in already_sent_ids:
            continue
        first = u.full_name.split()[0] if u.full_name else "there"
        html = f"""\
<div lang="en" dir="ltr" style="{_base_style()}">
  {_preheader_html("Enable sharing to start receiving intro requests")}
  <p style="margin: 0 0 16px;">Hi {first},</p>
  <p style="margin: 0 0 16px;">Great — we've processed your LinkedIn connections. <strong>But you haven't enabled marketplace sharing yet.</strong> That means:</p>
  <ul style="margin: 0 0 16px; padding-left: 20px;">
    <li>You're not earning credits for helping job seekers</li>
    <li>You're missing out on referral bonuses ($2-10K per successful hire)</li>
  </ul>
  <div style="margin: 16px 0;">
    <a href="{APP_URL}/marketplace/settings" style="display: inline-block; background: #2563eb; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 600;">Turn On Sharing &amp; Earn Bonuses</a>
  </div>
  <p style="margin: 16px 0 0; font-size: 14px; color: #6b7280;">&mdash; {_agent_signoff("sha[RESEND_KEY_REDACTED]")}</p>
  {_footer_html()}
</div>"""
        eid = _send_email(
            u.email,
            "Your network is uploaded — unlock $2-10K in referral bonuses",
            html,
        )
        await _record_send(db, u.id, "nh_sharing_d2", external_id=eid)
        count += 1
    await db.commit()
    logger.info("nh_sharing_d2: sent %d emails", count)
    return count


async def send_first_search_nudge_d2(db: AsyncSession) -> int:
    """Nudge job seekers who uploaded CSV but haven't searched."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

    uploaded_subq = select(CsvUpload.user_id).distinct().scalar_subquery()
    searched_subq = select(SearchRequest.user_id).distinct().scalar_subquery()
    result = await db.execute(
        select(User).where(
            User.deleted_at.is_(None),
            User.marketing_opt_out.is_(False),
            User.created_at < cutoff,
            User.id.in_(uploaded_subq),
            User.id.not_in(searched_subq),
        )
    )
    users = result.scalars().all()

    # Batch-load already-sent set for today (avoids N+1)
    user_ids = [u.id for u in users]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    already_sent_ids: set[uuid.UUID] = set()
    if user_ids:
        sent_result = await db.execute(
            select(EmailCampaignLog.user_id).where(
                EmailCampaignLog.user_id.in_(user_ids),
                EmailCampaignLog.email_type == "first_search_d2",
                EmailCampaignLog.sent_date == today,
            )
        )
        already_sent_ids = {row[0] for row in sent_result.all()}

    count = 0
    for u in users:
        if u.id in already_sent_ids:
            continue
        first = u.full_name.split()[0] if u.full_name else "there"
        html = f"""\
<div lang="en" dir="ltr" style="{_base_style()}">
  {_preheader_html("Your contacts are analyzed — see who can refer you")}
  <p style="margin: 0 0 16px;">Hi {first},</p>
  <p style="margin: 0 0 16px;">We've analyzed your connections. <strong>You haven't searched for warm paths yet.</strong></p>
  <p style="margin: 0 0 16px;">Try it now: enter target companies and we'll show you who in your network (or the marketplace) can refer you.</p>
  <div style="margin: 16px 0;">
    <a href="{APP_URL}/referrals" style="display: inline-block; background: #2563eb; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 600;">See Who Can Refer Me</a>
  </div>
  <p style="margin: 16px 0 0; font-size: 14px; color: #6b7280;">&mdash; {_agent_signoff("job_seeker")}</p>
  {_footer_html()}
</div>"""
        eid = _send_email(
            u.email, "We found warm paths in your network — see who can refer you", html
        )
        await _record_send(db, u.id, "first_search_d2", external_id=eid)
        count += 1
    await db.commit()
    logger.info("first_search_d2: sent %d emails", count)
    return count


# ---------------------------------------------------------------------------
# Operational reminders
# ---------------------------------------------------------------------------


async def send_intro_pending_reminder(db: AsyncSession) -> int:
    """Remind network holders of pending intro requests older than 24h."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    result = await db.execute(
        select(
            IntroFacilitation.network_holder_id,
            func.count(IntroFacilitation.id).label("cnt"),
        )
        .where(
            IntroFacilitation.status == "requested",
            IntroFacilitation.requested_at < cutoff,
        )
        .group_by(IntroFacilitation.network_holder_id)
    )
    rows = result.all()
    if not rows:
        logger.info("intro_pending_24h: sent 0 emails")
        return 0

    nh_ids = [nh_id for nh_id, _ in rows]

    # Batch-load users
    user_result = await db.execute(
        select(User).where(
            User.id.in_(nh_ids),
            User.deleted_at.is_(None),
        )
    )
    users_by_id: dict[uuid.UUID, User] = {u.id: u for u in user_result.scalars().all()}

    # Batch-load already-sent set for today
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sent_result = await db.execute(
        select(EmailCampaignLog.user_id).where(
            EmailCampaignLog.user_id.in_(nh_ids),
            EmailCampaignLog.email_type == "intro_pending_24h",
            EmailCampaignLog.sent_date == today,
        )
    )
    already_sent_ids: set[uuid.UUID] = {row[0] for row in sent_result.all()}

    count = 0
    for nh_id, pending_count in rows:
        if nh_id in already_sent_ids:
            continue
        u = users_by_id.get(nh_id)
        if not u or u.marketing_opt_out:
            continue
        first = u.full_name.split()[0] if u.full_name else "there"
        html = f"""\
<div lang="en" dir="ltr" style="{_base_style()}">
  {_preheader_html(f"{pending_count} candidates want your referral")}
  <p style="margin: 0 0 16px;">Hi {first},</p>
  <p style="margin: 0 0 16px;"><strong>You have {pending_count} intro request(s) waiting.</strong> Each one is a potential referral bonus of $2-10K.</p>
  <div style="margin: 16px 0;">
    <a href="{APP_URL}/marketplace/requests" style="display: inline-block; background: #2563eb; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 600;">Review &amp; Earn Credits</a>
  </div>
  <p style="margin: 16px 0 0; font-size: 14px; color: #6b7280;">&mdash; {_agent_signoff("sha[RESEND_KEY_REDACTED]")}</p>
  {_footer_html()}
</div>"""
        eid = _send_email(
            u.email,
            f"{pending_count} referral bonus opportunity waiting for your review",
            html,
        )
        await _record_send(db, nh_id, "intro_pending_24h", external_id=eid)
        count += 1
    await db.commit()
    logger.info("intro_pending_24h: sent %d emails", count)
    return count


async def send_intro_request_notification(
    nh_user: User,
    company_name: str,
    role_level: str,
    job_seeker_snapshot: dict,
    facilitation_id: uuid.UUID,
    db: AsyncSession,
) -> bool:
    """Send immediate email to NH when a job seeker requests an intro.

    Returns True if email was sent, False if skipped (opt-out).
    """
    if nh_user.marketing_opt_out:
        return False

    first = nh_user.full_name.split()[0] if nh_user.full_name else "there"

    # Build seeker summary from snapshot
    seeker_info = ""
    if job_seeker_snapshot.get("full_name"):
        seeker_info = f'<p style="margin: 0 0 8px; font-size: 14px;"><strong>From:</strong> {job_seeker_snapshot["full_name"]}</p>'
    if job_seeker_snapshot.get("message"):
        seeker_info += f'<p style="margin: 0 0 8px; font-size: 14px; color: #4b5563;"><em>"{job_seeker_snapshot["message"]}"</em></p>'

    html = f"""\
<div lang="en" dir="ltr" style="{_base_style()}">
  {_preheader_html(f"Someone wants a referral at {company_name}")}
  <p style="margin: 0 0 16px;">Hi {first},</p>
  <p style="margin: 0 0 16px;">A candidate is looking for a <strong>{role_level}-level</strong> referral at <strong>{company_name}</strong> and matched one of your contacts.</p>
  {seeker_info}
  <p style="margin: 0 0 16px;">If this leads to a hire, you could earn <strong>$2-10K</strong> in referral bonuses from your employer.</p>
  <div style="margin: 16px 0;">
    <a href="{APP_URL}/marketplace/requests" style="display: inline-block; background: #2563eb; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 600;">Review Request</a>
  </div>
  <p style="margin: 16px 0 0; font-size: 14px; color: #6b7280;">&mdash; {_agent_signoff("sha[RESEND_KEY_REDACTED]")}</p>
  {_footer_html()}
</div>"""

    eid = _send_email(
        nh_user.email,
        f"Referral opportunity at {company_name} — review and earn",
        html,
    )
    await _record_send(db, nh_user.id, "intro_request_notify", external_id=eid)
    logger.info(
        "intro_request_notify: sent to %s for facilitation %s",
        nh_user.id,
        facilitation_id,
    )
    return True


async def send_weekly_digest(db: AsyncSession) -> int:
    """Weekly activity digest for active users (any activity in last 7d)."""
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    # Active users = anyone with a usage_log entry in last 7 days
    active_subq = (
        select(UsageLog.user_id)
        .where(UsageLog.created_at > week_ago)
        .distinct()
        .scalar_subquery()
    )
    result = await db.execute(
        select(User).where(
            User.id.in_(active_subq),
            User.deleted_at.is_(None),
            User.marketing_opt_out.is_(False),
        )
    )
    users = result.scalars().all()
    if not users:
        logger.info("weekly_digest: sent 0 emails")
        return 0

    user_ids = [u.id for u in users]

    # Batch-load already-sent set for today
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sent_result = await db.execute(
        select(EmailCampaignLog.user_id).where(
            EmailCampaignLog.user_id.in_(user_ids),
            EmailCampaignLog.email_type == "weekly_digest",
            EmailCampaignLog.sent_date == today,
        )
    )
    already_sent_ids: set[uuid.UUID] = {row[0] for row in sent_result.all()}

    # Batch-compute search counts per user (GROUP BY)
    search_result = await db.execute(
        select(
            SearchRequest.user_id,
            func.count(SearchRequest.id),
        )
        .where(
            SearchRequest.user_id.in_(user_ids),
            SearchRequest.created_at > week_ago,
        )
        .group_by(SearchRequest.user_id)
    )
    search_counts: dict[uuid.UUID, int] = dict(search_result.all())

    # Batch-compute intro_sent counts per user (as job seeker)
    intro_sent_result = await db.execute(
        select(
            IntroFacilitation.job_seeker_id,
            func.count(IntroFacilitation.id),
        )
        .where(
            IntroFacilitation.job_seeker_id.in_(user_ids),
            IntroFacilitation.requested_at > week_ago,
        )
        .group_by(IntroFacilitation.job_seeker_id)
    )
    intro_sent_counts: dict[uuid.UUID, int] = dict(intro_sent_result.all())

    # Batch-compute intro_received counts per user (as network holder)
    intro_recv_result = await db.execute(
        select(
            IntroFacilitation.network_holder_id,
            func.count(IntroFacilitation.id),
        )
        .where(
            IntroFacilitation.network_holder_id.in_(user_ids),
            IntroFacilitation.requested_at > week_ago,
        )
        .group_by(IntroFacilitation.network_holder_id)
    )
    intro_recv_counts: dict[uuid.UUID, int] = dict(intro_recv_result.all())

    count = 0
    for u in users:
        if u.id in already_sent_ids:
            continue
        first = u.full_name.split()[0] if u.full_name else "there"

        search_count = search_counts.get(u.id, 0)
        intro_sent = intro_sent_counts.get(u.id, 0)
        intro_received = intro_recv_counts.get(u.id, 0)

        stats_html = ""
        if search_count or intro_sent:
            stats_html += f"<li><strong>{search_count}</strong> searches run</li>"
            stats_html += f"<li><strong>{intro_sent}</strong> intro requests sent</li>"
        if intro_received:
            stats_html += (
                f"<li><strong>{intro_received}</strong> intro requests received</li>"
            )

        if not stats_html:
            stats_html = "<li>You were active this week!</li>"

        # Build subject with actual stats
        subject_parts = []
        if search_count:
            subject_parts.append(f"{search_count} searches")
        if intro_sent:
            subject_parts.append(f"{intro_sent} intros")
        if intro_received:
            subject_parts.append(f"{intro_received} requests")
        subject = (
            f"Your week: {', '.join(subject_parts)}"
            if subject_parts
            else "Your WarmPath weekly digest"
        )

        agent = _agent_signoff(u.intent)
        html = f"""\
<div lang="en" dir="ltr" style="{_base_style()}">
  {_preheader_html("Here's what happened on WarmPath this week")}
  <p style="margin: 0 0 16px;">Hi {first},</p>
  <p style="margin: 0 0 8px; font-weight: 600;">Your week on WarmPath:</p>
  <ul style="margin: 0 0 16px; padding-left: 20px;">{stats_html}</ul>
  <p style="margin: 0 0 16px; font-size: 14px; color: #6b7280;">Every intro you approve brings someone closer to a referral.</p>
  <div style="margin: 16px 0;">
    <a href="{APP_URL}/coach" style="display: inline-block; background: #2563eb; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 600;">View Dashboard</a>
  </div>
  <p style="margin: 16px 0 0; font-size: 14px; color: #6b7280;">&mdash; {agent}</p>
  {_footer_html()}
</div>"""
        eid = _send_email(u.email, subject, html)
        await _record_send(db, u.id, "weekly_digest", external_id=eid)
        count += 1
    await db.commit()
    logger.info("weekly_digest: sent %d emails", count)
    return count


# ---------------------------------------------------------------------------
# Re-engagement
# ---------------------------------------------------------------------------


async def send_reengagement_d30(db: AsyncSession) -> int:
    """Re-engage users with no activity for ~30 days."""
    window_start = datetime.now(timezone.utc) - timedelta(days=31)
    window_end = datetime.now(timezone.utc) - timedelta(days=29)

    # Users whose most recent usage_log is 29-31 days ago
    recent_subq = (
        select(UsageLog.user_id)
        .where(UsageLog.created_at > window_end)
        .distinct()
        .scalar_subquery()
    )
    ever_active_subq = (
        select(UsageLog.user_id)
        .where(UsageLog.created_at > window_start)
        .distinct()
        .scalar_subquery()
    )
    result = await db.execute(
        select(User).where(
            User.deleted_at.is_(None),
            User.marketing_opt_out.is_(False),
            User.id.in_(ever_active_subq),
            User.id.not_in(recent_subq),
        )
    )
    users = result.scalars().all()

    # Batch-load already-sent set for today (avoids N+1)
    user_ids = [u.id for u in users]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    already_sent_ids: set[uuid.UUID] = set()
    if user_ids:
        sent_result = await db.execute(
            select(EmailCampaignLog.user_id).where(
                EmailCampaignLog.user_id.in_(user_ids),
                EmailCampaignLog.email_type == "reengagement_d30",
                EmailCampaignLog.sent_date == today,
            )
        )
        already_sent_ids = {row[0] for row in sent_result.all()}

    count = 0
    for u in users:
        if u.id in already_sent_ids:
            continue
        first = u.full_name.split()[0] if u.full_name else "there"
        agent = _agent_signoff(u.intent)
        html = f"""\
<div lang="en" dir="ltr" style="{_base_style()}">
  {_preheader_html("New marketplace connections since you last searched")}
  <p style="margin: 0 0 16px;">Hi {first},</p>
  <p style="margin: 0 0 16px;">It's been a month. Your contacts are still active on WarmPath — and the marketplace has grown since you last searched.</p>
  <p style="margin: 0 0 16px;">Log back in to check pending intro requests or refresh your network for fresh opportunities.</p>
  <div style="margin: 16px 0;">
    <a href="{APP_URL}/coach" style="display: inline-block; background: #f59e0b; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 600;">Check New Referral Paths</a>
  </div>
  <p style="margin: 16px 0 0; font-size: 14px; color: #6b7280;">&mdash; {agent}</p>
  {_footer_html()}
</div>"""
        eid = _send_email(
            u.email, "New referral paths appeared in your network this month", html
        )
        await _record_send(db, u.id, "reengagement_d30", external_id=eid)
        count += 1
    await db.commit()
    logger.info("reengagement_d30: sent %d emails", count)
    return count


async def send_reengagement_d90(db: AsyncSession) -> int:
    """Final re-engagement for users inactive 90 days."""
    window_start = datetime.now(timezone.utc) - timedelta(days=91)
    window_end = datetime.now(timezone.utc) - timedelta(days=89)

    recent_subq = (
        select(UsageLog.user_id)
        .where(UsageLog.created_at > window_end)
        .distinct()
        .scalar_subquery()
    )
    ever_active_subq = (
        select(UsageLog.user_id)
        .where(UsageLog.created_at > window_start)
        .distinct()
        .scalar_subquery()
    )
    result = await db.execute(
        select(User).where(
            User.deleted_at.is_(None),
            User.marketing_opt_out.is_(False),
            User.id.in_(ever_active_subq),
            User.id.not_in(recent_subq),
        )
    )
    users = result.scalars().all()

    # Batch-load already-sent set for today (avoids N+1)
    user_ids = [u.id for u in users]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    already_sent_ids: set[uuid.UUID] = set()
    if user_ids:
        sent_result = await db.execute(
            select(EmailCampaignLog.user_id).where(
                EmailCampaignLog.user_id.in_(user_ids),
                EmailCampaignLog.email_type == "reengagement_d90",
                EmailCampaignLog.sent_date == today,
            )
        )
        already_sent_ids = {row[0] for row in sent_result.all()}

    count = 0
    for u in users:
        if u.id in already_sent_ids:
            continue
        first = u.full_name.split()[0] if u.full_name else "there"
        agent = _agent_signoff(u.intent)
        html = f"""\
<div lang="en" dir="ltr" style="{_base_style()}">
  {_preheader_html("Switch to connector mode and start earning")}
  <p style="margin: 0 0 16px;">Hi {first},</p>
  <p style="margin: 0 0 16px;">It's been a while. Your network is still private and secure on WarmPath. If you're no longer job hunting, your connections are still valuable — switch to connector mode and start earning referral bonuses when you help others get referred.</p>
  <div style="margin: 16px 0;">
    <a href="{APP_URL}/coach" style="display: inline-block; background: #f59e0b; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 600;">Switch to Connector Mode</a>
  </div>
  <p style="margin: 16px 0 0; font-size: 14px; color: #6b7280;">&mdash; {agent}</p>
  {_footer_html()}
</div>"""
        eid = _send_email(
            u.email,
            "Still have your network on WarmPath — switch to connector mode?",
            html,
        )
        await _record_send(db, u.id, "reengagement_d90", external_id=eid)
        count += 1
    await db.commit()
    logger.info("reengagement_d90: sent %d emails", count)
    return count


# ---------------------------------------------------------------------------
# Smart digest (feed-powered) — replaces basic weekly digest
# ---------------------------------------------------------------------------


FEED_ICON_MAP = {
    "job_alert": "💼",
    "enrichment_prompt": "❓",
    "outcome_check": "✅",
    "marketplace_signal": "🤝",
    "follow_up_nudge": "🔔",
    "network_insight": "📊",
}


async def send_smart_digest_email(user_id: uuid.UUID, db: AsyncSession) -> bool:
    """Send a feed-powered digest email with top unseen insights.

    Returns True if email was sent, False if skipped (already sent, opted out,
    or no relevant items).
    """
    from app.services.feed_generator import get_digest_items

    # Load user
    user_result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.deleted_at.is_(None),
            User.marketing_opt_out.is_(False),
        )
    )
    user = user_result.scalar_one_or_none()
    if not user or not user.email:
        return False

    # Dedup — one smart_digest per day
    if await _already_sent(db, user_id, "smart_digest"):
        return False

    # Get top 3 unseen feed items
    items = await get_digest_items(user_id, db)
    if not items:
        return False

    first_name = (user.full_name or "there").split(" ")[0]

    # Build HTML for each item
    items_html = ""
    for item in items[:3]:
        icon = FEED_ICON_MAP.get(item.item_type, "📌")
        action_html = ""
        if item.action_url:
            action_html = (
                f'<a href="{APP_URL}{item.action_url}" '
                f'style="display: inline-block; margin-top: 8px; color: #f59e0b; '
                f'text-decoration: none; font-size: 13px; font-weight: 600;">'
                f"{item.action_label or 'View'} &rarr;</a>"
            )
        items_html += f"""
  <div style="padding: 12px; margin: 8px 0; border: 1px solid #e5e7eb; border-radius: 8px; border-left: 3px solid #f59e0b;">
    <div style="font-size: 14px; font-weight: 600; color: #1f2937;">
      {icon} {item.title}
    </div>
    {f'<div style="margin-top: 4px; font-size: 13px; color: #6b7280;">{item.body}</div>' if item.body else ""}
    {action_html}
  </div>"""

    html = f"""<div style="{_base_style()}">
  <h2 style="color: #1f2937; margin: 24px 0 8px;">Hey {first_name}, Keevs found something for you</h2>
  <p style="color: #6b7280; font-size: 14px; margin: 0 0 16px;">
    Here's what's new since you last checked in:
  </p>
  {items_html}
  <div style="margin: 20px 0;">
    <a href="{APP_URL}/coach" style="display: inline-block; background: #f59e0b; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 600;">Open WarmPath</a>
  </div>
  <p style="margin: 16px 0 0; font-size: 13px; color: #9ca3af;">
    Keevs surfaces insights based on your network and job search activity.
  </p>
  {_footer_html()}
</div>"""

    eid = _send_email(
        user.email,
        f"Keevs found {len(items)} new insight{'s' if len(items) > 1 else ''} for you",
        html,
    )
    await _record_send(db, user_id, "smart_digest", external_id=eid)
    return True
