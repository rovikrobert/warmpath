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

async def _already_sent(
    db: AsyncSession, user_id: uuid.UUID, email_type: str
) -> bool:
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
    db: AsyncSession, user_id: uuid.UUID, email_type: str
) -> None:
    """Record that an email was sent."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    db.add(
        EmailCampaignLog(
            user_id=user_id,
            email_type=email_type,
            sent_date=today,
        )
    )
    await db.flush()


def _base_style() -> str:
    return 'font-family: system-ui, -apple-system, sans-serif; max-width: 500px; color: #1f2937;'


def _footer_html() -> str:
    return f"""\
<div style="margin: 32px 0 0; padding: 16px 0; border-top: 1px solid #e5e7eb; text-align: center;">
  <p style="margin: 0 0 4px; color: #9ca3af; font-size: 12px;">
    <strong>WarmPath</strong> — Helping you get referred, not rejected.
  </p>
  <p style="margin: 0; color: #d1d5db; font-size: 11px;">
    <a href="{APP_URL}/settings/privacy" style="color: #9ca3af; text-decoration: none;">Unsubscribe</a> &middot;
    <a href="{APP_URL}/privacy" style="color: #9ca3af; text-decoration: none;">Privacy Policy</a>
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
<div style="{_base_style()}">
  <div style="padding: 24px; background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); border-radius: 12px 12px 0 0; color: #fff; text-align: center;">
    <h1 style="margin: 0 0 4px; font-size: 24px;">Welcome to WarmPath, {first}!</h1>
    <p style="margin: 0; opacity: 0.9;">Your warm path to your next role starts here.</p>
  </div>
  <div style="padding: 24px;">
    <p style="margin: 0 0 16px;">You just earned <strong>50 welcome credits</strong>. Here's how to make the most of them:</p>
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
      <a href="{APP_URL}/dashboard" style="display: inline-block; padding: 12px 28px; background: #f59e0b; color: #fff; text-decoration: none; border-radius: 8px; font-weight: 600;">Go to Dashboard</a>
    </div>
    <p style="margin: 16px 0 0; font-size: 14px; color: #6b7280;">Questions? Just reply to this email.</p>
  </div>
  {_footer_html()}
</div>"""
    _send_email(user.email, "Welcome to WarmPath — your warm path starts here", html)
    await _record_send(db, user.id, "welcome_js")
    return True


async def send_welcome_email_nh(user: User, db: AsyncSession) -> bool:
    """Welcome email for network holders."""
    if user.marketing_opt_out:
        return False
    if await _already_sent(db, user.id, "welcome_nh"):
        return False

    first = user.full_name.split()[0] if user.full_name else "there"
    html = f"""\
<div style="{_base_style()}">
  <div style="padding: 24px; background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); border-radius: 12px 12px 0 0; color: #fff; text-align: center;">
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
      <strong>Step 3:</strong> Review intro requests and earn credits + referral bonuses
    </div>
    <div style="text-align: center; margin: 24px 0;">
      <a href="{APP_URL}/contacts" style="display: inline-block; padding: 12px 28px; background: #2563eb; color: #fff; text-decoration: none; border-radius: 8px; font-weight: 600;">Upload Your Network</a>
    </div>
    <p style="margin: 16px 0 0; font-size: 14px; color: #6b7280;">Questions? Just reply to this email.</p>
  </div>
  {_footer_html()}
</div>"""
    _send_email(user.email, "Welcome to WarmPath — start earning referral bonuses", html)
    await _record_send(db, user.id, "welcome_nh")
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
    count = 0
    for u in users:
        if await _already_sent(db, u.id, "csv_reminder_d1"):
            continue
        first = u.full_name.split()[0] if u.full_name else "there"
        html = f"""\
<div style="{_base_style()}">
  <p style="margin: 0 0 16px;">Hi {first},</p>
  <p style="margin: 0 0 16px;">You signed up yesterday but haven't uploaded your LinkedIn connections yet. <strong>Without your network, we can't show you warm paths to your target companies.</strong></p>
  <p style="margin: 0 0 16px;">It takes 2 minutes: <a href="https://www.linkedin.com/mypreferences/d/download-my-data" style="color: #2563eb;">Export from LinkedIn</a> &rarr; Upload to WarmPath.</p>
  <a href="{APP_URL}/contacts" style="display: inline-block; background: #2563eb; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 16px 0;">Upload Now</a>
  <p style="margin: 16px 0 0; font-size: 14px; color: #6b7280;">&mdash; The WarmPath Team</p>
  {_footer_html()}
</div>"""
        _send_email(u.email, "Your network is waiting — upload your LinkedIn connections", html)
        await _record_send(db, u.id, "csv_reminder_d1")
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
    count = 0
    for u in users:
        if await _already_sent(db, u.id, "csv_reminder_d3"):
            continue
        first = u.full_name.split()[0] if u.full_name else "there"
        html = f"""\
<div style="{_base_style()}">
  <p style="margin: 0 0 16px;">Hi {first},</p>
  <p style="margin: 0 0 16px;">We haven't seen your LinkedIn connections upload yet. <strong>Without it, WarmPath can't find you referral paths.</strong></p>
  <p style="margin: 0 0 16px;">Still stuck? Reply to this email and we'll walk you through it. Otherwise, <a href="{APP_URL}/contacts" style="color: #2563eb;">upload here</a> (2 min).</p>
  <a href="{APP_URL}/contacts" style="display: inline-block; background: #dc2626; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 16px 0;">Upload Your Network &rarr;</a>
  <p style="margin: 16px 0 0; font-size: 14px; color: #6b7280;">&mdash; The WarmPath Team</p>
  {_footer_html()}
</div>"""
        _send_email(u.email, "Still here? 3 days without your network upload", html)
        await _record_send(db, u.id, "csv_reminder_d3")
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
            User.user_type.in_(["network_holder", "both"]),
            User.deleted_at.is_(None),
            User.marketing_opt_out.is_(False),
            User.created_at < cutoff,
            User.id.in_(uploaded_subq),
            User.id.not_in(opted_in_subq),
        )
    )
    users = result.scalars().all()
    count = 0
    for u in users:
        if await _already_sent(db, u.id, "nh_sharing_d2"):
            continue
        first = u.full_name.split()[0] if u.full_name else "there"
        html = f"""\
<div style="{_base_style()}">
  <p style="margin: 0 0 16px;">Hi {first},</p>
  <p style="margin: 0 0 16px;">Great — we've processed your LinkedIn connections. <strong>But you haven't enabled marketplace sharing yet.</strong> That means:</p>
  <ul style="margin: 0 0 16px; padding-left: 20px;">
    <li>You're not earning credits for helping job seekers</li>
    <li>You're missing out on referral bonuses ($2-10K per successful hire)</li>
  </ul>
  <a href="{APP_URL}/marketplace/settings" style="display: inline-block; background: #2563eb; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 16px 0;">Enable Marketplace Sharing</a>
  <p style="margin: 16px 0 0; font-size: 14px; color: #6b7280;">&mdash; The WarmPath Team</p>
  {_footer_html()}
</div>"""
        _send_email(u.email, "You uploaded your network — now share it to earn credits", html)
        await _record_send(db, u.id, "nh_sharing_d2")
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
            User.user_type.in_(["job_seeker", "both"]),
            User.deleted_at.is_(None),
            User.marketing_opt_out.is_(False),
            User.created_at < cutoff,
            User.id.in_(uploaded_subq),
            User.id.not_in(searched_subq),
        )
    )
    users = result.scalars().all()
    count = 0
    for u in users:
        if await _already_sent(db, u.id, "first_search_d2"):
            continue
        first = u.full_name.split()[0] if u.full_name else "there"
        html = f"""\
<div style="{_base_style()}">
  <p style="margin: 0 0 16px;">Hi {first},</p>
  <p style="margin: 0 0 16px;">We've analyzed your connections. <strong>You haven't searched for warm paths yet.</strong></p>
  <p style="margin: 0 0 16px;">Try it now: enter target companies and we'll show you who in your network (or the marketplace) can refer you.</p>
  <a href="{APP_URL}/referrals" style="display: inline-block; background: #2563eb; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 16px 0;">Find Referrals &rarr;</a>
  <p style="margin: 16px 0 0; font-size: 14px; color: #6b7280;">&mdash; The WarmPath Team</p>
  {_footer_html()}
</div>"""
        _send_email(u.email, "Your network is ready — run your first search", html)
        await _record_send(db, u.id, "first_search_d2")
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
    count = 0
    for nh_id, pending_count in rows:
        if await _already_sent(db, nh_id, "intro_pending_24h"):
            continue
        user_result = await db.execute(
            select(User).where(User.id == nh_id, User.deleted_at.is_(None))
        )
        u = user_result.scalar_one_or_none()
        if not u or u.marketing_opt_out:
            continue
        first = u.full_name.split()[0] if u.full_name else "there"
        html = f"""\
<div style="{_base_style()}">
  <p style="margin: 0 0 16px;">Hi {first},</p>
  <p style="margin: 0 0 16px;"><strong>You have {pending_count} pending intro request(s)</strong> from job seekers looking to connect with your network. Each approval earns you 50 credits + a shot at a referral bonus.</p>
  <a href="{APP_URL}/marketplace/requests" style="display: inline-block; background: #2563eb; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 16px 0;">Review Requests &rarr;</a>
  <p style="margin: 16px 0 0; font-size: 14px; color: #6b7280;">&mdash; The WarmPath Team</p>
  {_footer_html()}
</div>"""
        _send_email(u.email, f"New intro request waiting for you ({pending_count} pending)", html)
        await _record_send(db, nh_id, "intro_pending_24h")
        count += 1
    await db.commit()
    logger.info("intro_pending_24h: sent %d emails", count)
    return count


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
    count = 0
    for u in users:
        if await _already_sent(db, u.id, "weekly_digest"):
            continue
        first = u.full_name.split()[0] if u.full_name else "there"

        # Gather stats
        search_count = (
            await db.execute(
                select(func.count(SearchRequest.id)).where(
                    SearchRequest.user_id == u.id,
                    SearchRequest.created_at > week_ago,
                )
            )
        ).scalar() or 0

        intro_sent = (
            await db.execute(
                select(func.count(IntroFacilitation.id)).where(
                    IntroFacilitation.job_seeker_id == u.id,
                    IntroFacilitation.requested_at > week_ago,
                )
            )
        ).scalar() or 0

        intro_received = (
            await db.execute(
                select(func.count(IntroFacilitation.id)).where(
                    IntroFacilitation.network_holder_id == u.id,
                    IntroFacilitation.requested_at > week_ago,
                )
            )
        ).scalar() or 0

        stats_html = ""
        if u.user_type in ("job_seeker", "both"):
            stats_html += f"<li><strong>{search_count}</strong> searches run</li>"
            stats_html += f"<li><strong>{intro_sent}</strong> intro requests sent</li>"
        if u.user_type in ("network_holder", "both"):
            stats_html += f"<li><strong>{intro_received}</strong> intro requests received</li>"

        if not stats_html:
            stats_html = "<li>You were active this week!</li>"

        html = f"""\
<div style="{_base_style()}">
  <p style="margin: 0 0 16px;">Hi {first},</p>
  <p style="margin: 0 0 8px; font-weight: 600;">Your week on WarmPath:</p>
  <ul style="margin: 0 0 16px; padding-left: 20px;">{stats_html}</ul>
  <a href="{APP_URL}/dashboard" style="display: inline-block; background: #2563eb; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 16px 0;">View Dashboard</a>
  <p style="margin: 16px 0 0; font-size: 14px; color: #6b7280;">&mdash; The WarmPath Team</p>
  {_footer_html()}
</div>"""
        _send_email(u.email, "Your WarmPath weekly digest", html)
        await _record_send(db, u.id, "weekly_digest")
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
    count = 0
    for u in users:
        if await _already_sent(db, u.id, "reengagement_d30"):
            continue
        first = u.full_name.split()[0] if u.full_name else "there"
        html = f"""\
<div style="{_base_style()}">
  <p style="margin: 0 0 16px;">Hi {first},</p>
  <p style="margin: 0 0 16px;">It's been a month since you were last on WarmPath. Your uploaded contacts are still indexed and ready to unlock referrals.</p>
  <p style="margin: 0 0 16px;">Log back in to check pending intro requests or refresh your network for fresh opportunities.</p>
  <a href="{APP_URL}/dashboard" style="display: inline-block; background: #f59e0b; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 16px 0;">Come Back &rarr;</a>
  <p style="margin: 16px 0 0; font-size: 14px; color: #6b7280;">&mdash; The WarmPath Team</p>
  {_footer_html()}
</div>"""
        _send_email(u.email, "Your WarmPath network is waiting", html)
        await _record_send(db, u.id, "reengagement_d30")
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
    count = 0
    for u in users:
        if await _already_sent(db, u.id, "reengagement_d90"):
            continue
        first = u.full_name.split()[0] if u.full_name else "there"
        html = f"""\
<div style="{_base_style()}">
  <p style="margin: 0 0 16px;">Hi {first},</p>
  <p style="margin: 0 0 16px;">We haven't seen you in 90 days. Your network data remains private, but you're missing out on referral bonuses and connector reputation.</p>
  <p style="margin: 0 0 16px;">If you're no longer job hunting, consider switching to network holder mode — help others get referred and earn credits for your own future search.</p>
  <a href="{APP_URL}/dashboard" style="display: inline-block; background: #f59e0b; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 16px 0;">Log Back In</a>
  <p style="margin: 16px 0 0; font-size: 14px; color: #6b7280;">&mdash; The WarmPath Team</p>
  {_footer_html()}
</div>"""
        _send_email(u.email, "Final reminder: referral bonuses going unclaimed", html)
        await _record_send(db, u.id, "reengagement_d90")
        count += 1
    await db.commit()
    logger.info("reengagement_d90: sent %d emails", count)
    return count
