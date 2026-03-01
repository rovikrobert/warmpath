"""Background feed generation service.

Generates personalized FeedItems for each user by combining:
  - Job monitoring (new openings at companies where user has warm paths)
  - Contact enrichment prompts (drive self-enrichment → trust graph data)
  - Outcome checks (close the loop on intros/applications)
  - Marketplace signals (new supply at target companies)
  - Follow-up nudges (approved intros not yet acted on)
  - Network insights (network strength changes, stale contact detection)

Each generator is a standalone async function that can be called independently
or orchestrated together. All generators are idempotent via dedup_key on FeedItem.

Strategic rationale:
  - SHORT TERM: drives daily engagement and revisits (the "inbound feed")
  - MEDIUM TERM: enrichment prompts collect trust graph data; outcome tracking
    powers the B2B analytics dashboard for companies
  - LONG TERM: interaction data (seen/acted/dismissed) trains relevance ranking
"""

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.feed import ContactFreshnessSignal, FeedItem
from app.models.job import Application, JobOpening, UserJobPreferences
from app.models.marketplace import (
    IntroFacilitation,
    MarketplaceListing,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dedup(item_type: str, *parts: str) -> str:
    """Build a stable dedup key from item type + arbitrary parts.

    Date-independent so the partial unique index
    ``(user_id, item_type, dedup_key) WHERE dismissed_at IS NULL``
    prevents duplicate feed items.  After a user dismisses an item
    the next generation cycle can create a fresh one.
    """
    raw = f"{item_type}:{'|'.join(str(p) for p in parts)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


async def _user_has_feed_item(
    db: AsyncSession, user_id: uuid.UUID, dedup_key: str
) -> bool:
    """Check if a non-dismissed feed item with this dedup key already exists."""
    result = await db.execute(
        select(func.count(FeedItem.id)).where(
            FeedItem.user_id == user_id,
            FeedItem.dedup_key == dedup_key,
            FeedItem.dismissed_at.is_(None),
        )
    )
    return result.scalar_one() > 0


# ---------------------------------------------------------------------------
# Generator 1: Job Alerts (highest-value feed item)
# "Stripe just posted 3 new roles matching your target — and you have 2 contacts there"
# ---------------------------------------------------------------------------


async def generate_job_alerts(
    user_id: uuid.UUID,
    db: AsyncSession,
    lookback_hours: int = 24,
) -> list[FeedItem]:
    """Find new job openings at companies where user has warm paths."""
    # Get user's job preferences
    prefs_result = await db.execute(
        select(UserJobPreferences).where(UserJobPreferences.user_id == user_id)
    )
    prefs = prefs_result.scalar_one_or_none()
    if not prefs or not prefs.target_role:
        return []

    # Get companies where user has contacts
    contact_companies = await db.execute(
        select(Contact.company_id, func.count(Contact.id).label("contact_count"))
        .where(
            Contact.user_id == user_id,
            Contact.deleted_at.is_(None),
            Contact.company_id.isnot(None),
        )
        .group_by(Contact.company_id)
    )
    company_contacts = {row[0]: row[1] for row in contact_companies.all()}

    if not company_contacts:
        return []

    # Find recent job openings at those companies
    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    jobs_result = await db.execute(
        select(JobOpening)
        .where(
            JobOpening.company_id.in_(list(company_contacts.keys())),
            JobOpening.is_active.is_(True),
            JobOpening.discovered_at >= since,
        )
        .order_by(JobOpening.discovered_at.desc())
    )
    jobs = jobs_result.scalars().all()

    if not jobs:
        return []

    # Group by company
    by_company: dict[uuid.UUID, list[JobOpening]] = {}
    for job in jobs:
        by_company.setdefault(job.company_id, []).append(job)

    items: list[FeedItem] = []
    for company_id, company_jobs in by_company.items():
        # Simple title matching against target role
        target_lower = prefs.target_role.lower()
        matching = [j for j in company_jobs if target_lower in (j.title or "").lower()]
        if not matching:
            # Broader match: any new jobs at a company where they have contacts
            matching = company_jobs[:3]

        contact_count = company_contacts.get(company_id, 0)
        company_name = matching[0].company.name if matching[0].company else "a company"
        job_count = len(matching)

        dedup_key = _dedup("job_alert", str(company_id))
        if await _user_has_feed_item(db, user_id, dedup_key):
            continue

        title = (
            f"{company_name} posted {job_count} new "
            f"{'role' if job_count == 1 else 'roles'} matching your target"
        )
        body = (
            f"You have {contact_count} "
            f"{'contact' if contact_count == 1 else 'contacts'} "
            f"there who could refer you."
        )

        top_titles = [j.title for j in matching[:3]]
        item = FeedItem(
            user_id=user_id,
            item_type="job_alert",
            title=title,
            body=body,
            icon="briefcase",
            action_url=f"/referrals?company={company_name}",
            action_label="View referral paths",
            priority=90,  # High priority — this is the money item
            dedup_key=dedup_key,
            metadata_={
                "company_id": str(company_id),
                "company_name": company_name,
                "job_count": job_count,
                "contact_count": contact_count,
                "top_titles": top_titles,
            },
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db.add(item)
        items.append(item)

    return items


# ---------------------------------------------------------------------------
# Generator 2: Enrichment Prompts (drives data collection for trust graph)
# "How do you know Sarah Chen at Stripe? Colleague, friend, or acquaintance?"
# ---------------------------------------------------------------------------


async def generate_enrichment_prompts(
    user_id: uuid.UUID,
    db: AsyncSession,
    batch_size: int = 5,
) -> list[FeedItem]:
    """Generate prompts for contacts missing relationship type or recency."""

    # Find contacts that lack relationship_type or last_interaction_date
    # Prioritize contacts at companies the user has searched for
    contacts_result = await db.execute(
        select(Contact)
        .where(
            Contact.user_id == user_id,
            Contact.deleted_at.is_(None),
            Contact.relationship_type.is_(None),
        )
        .order_by(Contact.created_at.desc())
        .limit(batch_size * 2)  # fetch extra to filter
    )
    contacts = contacts_result.scalars().all()

    if not contacts:
        return []

    # Also check for contacts missing freshness signals
    existing_signals = await db.execute(
        select(ContactFreshnessSignal.contact_id).where(
            ContactFreshnessSignal.user_id == user_id,
            ContactFreshnessSignal.signal_type == "relationship_type",
        )
    )
    already_prompted = {row[0] for row in existing_signals.all()}

    items: list[FeedItem] = []
    for contact in contacts:
        if contact.id in already_prompted:
            continue
        if len(items) >= batch_size:
            break

        dedup_key = _dedup("enrichment_prompt", str(contact.id), "relationship")
        if await _user_has_feed_item(db, user_id, dedup_key):
            continue

        name = contact.full_name or "a contact"
        company = contact.current_company or "their company"
        title = f"How do you know {name}?"
        body = (
            f"Categorizing your relationship with {name} at {company} "
            f"helps us find better referral paths for you."
        )

        item = FeedItem(
            user_id=user_id,
            item_type="enrichment_prompt",
            title=title,
            body=body,
            icon="user-check",
            action_url=f"/contacts?highlight={contact.id}",
            action_label="Categorize",
            priority=60,
            dedup_key=dedup_key,
            metadata_={
                "contact_id": str(contact.id),
                "contact_name": name,
                "company_name": company,
                "prompt_type": "relationship_type",
                "options": [
                    "colleague",
                    "manager",
                    "friend",
                    "alumni",
                    "investor",
                    "acquaintance",
                ],
            },
            expires_at=datetime.now(timezone.utc) + timedelta(days=14),
        )
        db.add(item)
        items.append(item)

    return items


# ---------------------------------------------------------------------------
# Generator 2b: Would-Refer Prompts (after relationship type is known)
# "Would Sarah Chen at Stripe refer you for a role? Definitely / Probably / No"
# ---------------------------------------------------------------------------


async def generate_would_refer_prompts(
    user_id: uuid.UUID,
    db: AsyncSession,
    batch_size: int = 3,
) -> list[FeedItem]:
    """Prompt for would_refer on contacts that have relationship_type but no would_refer."""
    contacts_result = await db.execute(
        select(Contact)
        .where(
            Contact.user_id == user_id,
            Contact.deleted_at.is_(None),
            Contact.relationship_type.isnot(None),
            Contact.would_refer.is_(None),
        )
        .order_by(Contact.created_at.desc())
        .limit(batch_size * 2)
    )
    contacts = contacts_result.scalars().all()

    if not contacts:
        return []

    items: list[FeedItem] = []
    for contact in contacts:
        if len(items) >= batch_size:
            break

        dedup_key = _dedup("enrichment_prompt", str(contact.id), "would_refer")
        if await _user_has_feed_item(db, user_id, dedup_key):
            continue

        name = contact.full_name or "a contact"
        company = contact.current_company or "their company"
        title = f"Would {name} refer you?"
        body = (
            f"You categorized {name} at {company} as '{contact.relationship_type}'. "
            f"Would they actually refer you for a role? This is the single strongest "
            f"signal for referral matching."
        )

        item = FeedItem(
            user_id=user_id,
            item_type="enrichment_prompt",
            title=title,
            body=body,
            icon="user-check",
            action_url=f"/contacts?highlight={contact.id}",
            action_label="Rate referral likelihood",
            priority=65,
            dedup_key=dedup_key,
            metadata_={
                "contact_id": str(contact.id),
                "contact_name": name,
                "company_name": company,
                "prompt_type": "would_refer",
                "options": ["definitely", "probably", "maybe", "no"],
            },
            expires_at=datetime.now(timezone.utc) + timedelta(days=14),
        )
        db.add(item)
        items.append(item)

    return items


# ---------------------------------------------------------------------------
# Generator 2c: Last Interaction Prompts (for stale connections)
# "When did you last talk to Sarah Chen? Last month / Last year / 2+ years"
# ---------------------------------------------------------------------------


async def generate_last_interaction_prompts(
    user_id: uuid.UUID,
    db: AsyncSession,
    batch_size: int = 3,
) -> list[FeedItem]:
    """Prompt for last_interaction_date on old connections missing it."""
    one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)

    contacts_result = await db.execute(
        select(Contact)
        .where(
            Contact.user_id == user_id,
            Contact.deleted_at.is_(None),
            Contact.last_interaction_date.is_(None),
            Contact.connected_on <= one_year_ago.date(),
        )
        .order_by(Contact.created_at.desc())
        .limit(batch_size * 2)
    )
    contacts = contacts_result.scalars().all()

    if not contacts:
        return []

    items: list[FeedItem] = []
    for contact in contacts:
        if len(items) >= batch_size:
            break

        dedup_key = _dedup("enrichment_prompt", str(contact.id), "last_interaction")
        if await _user_has_feed_item(db, user_id, dedup_key):
            continue

        name = contact.full_name or "a contact"
        company = contact.current_company or "their company"
        title = f"When did you last talk to {name}?"
        body = (
            f"You connected with {name} at {company} a while ago. "
            f"Recent interactions mean warmer referral paths."
        )

        item = FeedItem(
            user_id=user_id,
            item_type="enrichment_prompt",
            title=title,
            body=body,
            icon="clock",
            action_url=f"/contacts?highlight={contact.id}",
            action_label="Update interaction",
            priority=50,
            dedup_key=dedup_key,
            metadata_={
                "contact_id": str(contact.id),
                "contact_name": name,
                "company_name": company,
                "prompt_type": "last_interaction",
                "options": [
                    "last_month",
                    "last_quarter",
                    "last_year",
                    "over_2_years",
                ],
            },
            expires_at=datetime.now(timezone.utc) + timedelta(days=14),
        )
        db.add(item)
        items.append(item)

    return items


# ---------------------------------------------------------------------------
# Generator 3: Outcome Checks (closes the referral loop)
# "You requested an intro at Notion 5 days ago — have you heard back?"
# ---------------------------------------------------------------------------


async def generate_outcome_checks(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[FeedItem]:
    """Prompt users to update application status for stale intros."""
    # Find approved intros where the application hasn't been updated recently
    stale_window = datetime.now(timezone.utc) - timedelta(days=5)

    apps_result = await db.execute(
        select(Application)
        .where(
            Application.user_id == user_id,
            Application.deleted_at.is_(None),
            Application.status.in_(["draft", "message_sent", "applied"]),
            Application.updated_at <= stale_window,
        )
        .order_by(Application.updated_at.asc())
        .limit(3)
    )
    stale_apps = apps_result.scalars().all()

    items: list[FeedItem] = []
    for app in stale_apps:
        dedup_key = _dedup("outcome_check", str(app.id))
        if await _user_has_feed_item(db, user_id, dedup_key):
            continue

        days_ago = (datetime.now(timezone.utc) - app.updated_at).days
        title = f"Any update on your {app.company_name} application?"
        body = (
            f"You sent a message {days_ago} days ago for "
            f"{app.role_title or 'a role'} — "
            f"updating the status helps track what's working."
        )

        item = FeedItem(
            user_id=user_id,
            item_type="outcome_check",
            title=title,
            body=body,
            icon="clipboard-check",
            action_url=f"/applications?highlight={app.id}",
            action_label="Update status",
            priority=70,
            dedup_key=dedup_key,
            metadata_={
                "application_id": str(app.id),
                "company_name": app.company_name,
                "role_title": app.role_title,
                "days_since_update": days_ago,
            },
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db.add(item)
        items.append(item)

    return items


# ---------------------------------------------------------------------------
# Generator 4: Marketplace Signals (new supply at target companies)
# "A network holder just listed 4 new connections at Databricks"
# ---------------------------------------------------------------------------


async def generate_marketplace_signals(
    user_id: uuid.UUID,
    db: AsyncSession,
    lookback_hours: int = 24,
) -> list[FeedItem]:
    """Alert job seekers when new marketplace listings appear at target companies."""
    # Get user's target preferences for company targeting
    prefs_result = await db.execute(
        select(UserJobPreferences).where(UserJobPreferences.user_id == user_id)
    )
    prefs = prefs_result.scalar_one_or_none()
    if not prefs:
        return []

    # Get companies the user has recently searched for
    from app.models.search_request import SearchRequest

    recent_searches = await db.execute(
        select(SearchRequest.metadata_)
        .where(
            SearchRequest.user_id == user_id,
            SearchRequest.created_at >= datetime.now(timezone.utc) - timedelta(days=30),
        )
        .order_by(SearchRequest.created_at.desc())
        .limit(10)
    )

    target_company_names = set()
    for row in recent_searches.all():
        meta = row[0] or {}
        if "company_names" in meta:
            target_company_names.update(name.lower() for name in meta["company_names"])

    # Also include dream companies from job preferences
    if prefs and prefs.target_companies:
        target_companies = prefs.target_companies
        if isinstance(target_companies, list):
            target_company_names.update(name.lower() for name in target_companies)

    if not target_company_names:
        return []

    # Find new marketplace listings at target companies
    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    from app.models.company import Company

    new_listings = await db.execute(
        select(
            func.lower(Company.name).label("company_key"),
            Company.name.label("display_name"),
            func.count(MarketplaceListing.id).label("listing_count"),
        )
        .join(Company, MarketplaceListing.company_id == Company.id)
        .where(
            MarketplaceListing.is_available.is_(True),
            MarketplaceListing.deleted_at.is_(None),
            MarketplaceListing.created_at >= since,
            MarketplaceListing.network_holder_id != user_id,
            func.lower(Company.name).in_(target_company_names),
        )
        .group_by(func.lower(Company.name), Company.name)
    )

    items: list[FeedItem] = []
    for row in new_listings.all():
        dedup_key = _dedup("marketplace_signal", row.company_key)
        if await _user_has_feed_item(db, user_id, dedup_key):
            continue

        count = row.listing_count
        title = (
            f"{count} new {'connection' if count == 1 else 'connections'} "
            f"available at {row.display_name}"
        )
        body = (
            "A network holder just shared connections at a company you're targeting. "
            "You can request an intro through the marketplace."
        )

        item = FeedItem(
            user_id=user_id,
            item_type="marketplace_signal",
            title=title,
            body=body,
            icon="users",
            action_url="/referrals",
            action_label="Find referral paths",
            priority=80,
            dedup_key=dedup_key,
            metadata_={
                "company_name": row.display_name,
                "new_listing_count": count,
            },
            expires_at=datetime.now(timezone.utc) + timedelta(days=3),
        )
        db.add(item)
        items.append(item)

    return items


# ---------------------------------------------------------------------------
# Generator 5: Follow-up Nudges (approved intros not acted on)
# "Your intro at Stripe was approved 3 days ago — time to follow up!"
# ---------------------------------------------------------------------------


async def generate_follow_up_nudges(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[FeedItem]:
    """Nudge users when approved intros haven't led to applications."""
    stale_window = datetime.now(timezone.utc) - timedelta(days=2)

    approved_intros = await db.execute(
        select(IntroFacilitation)
        .where(
            IntroFacilitation.job_seeker_id == user_id,
            IntroFacilitation.status == "approved",
            IntroFacilitation.updated_at <= stale_window,
        )
        .limit(3)
    )

    items: list[FeedItem] = []
    for intro in approved_intros.scalars().all():
        dedup_key = _dedup("follow_up_nudge", str(intro.id))
        if await _user_has_feed_item(db, user_id, dedup_key):
            continue

        days_ago = (datetime.now(timezone.utc) - intro.updated_at).days
        title = "An intro you requested was approved — follow up!"
        body = (
            f"Your intro was approved {days_ago} days ago. "
            f"The network holder is waiting for you to follow through."
        )

        item = FeedItem(
            user_id=user_id,
            item_type="follow_up_nudge",
            title=title,
            body=body,
            icon="message-circle",
            action_url="/applications",
            action_label="Track application",
            priority=85,
            dedup_key=dedup_key,
            metadata_={
                "intro_id": str(intro.id),
                "days_since_approval": days_ago,
            },
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db.add(item)
        items.append(item)

    return items


# ---------------------------------------------------------------------------
# Generator 6: Network Insights (stale contacts, strength changes)
# "12 of your contacts haven't been updated in over a year"
# ---------------------------------------------------------------------------


async def generate_network_insights(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[FeedItem]:
    """Surface insights about the user's network health."""
    # Count contacts with stale data (connected > 1 year ago, no recent interaction)
    one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)

    stale_count_result = await db.execute(
        select(func.count(Contact.id)).where(
            Contact.user_id == user_id,
            Contact.deleted_at.is_(None),
            Contact.updated_at <= one_year_ago,
        )
    )
    stale_count = stale_count_result.scalar_one()

    items: list[FeedItem] = []

    if stale_count >= 5:
        dedup_key = _dedup("network_insight", "stale_contacts", str(user_id))
        if not await _user_has_feed_item(db, user_id, dedup_key):
            item = FeedItem(
                user_id=user_id,
                item_type="network_insight",
                title=f"{stale_count} contacts may have outdated info",
                body=(
                    "Updating your contacts' current roles and companies "
                    "improves your referral match accuracy."
                ),
                icon="refresh-cw",
                action_url="/contacts?sort=oldest",
                action_label="Review contacts",
                priority=40,
                dedup_key=dedup_key,
                metadata_={"stale_count": stale_count},
                expires_at=datetime.now(timezone.utc) + timedelta(days=14),
            )
            db.add(item)
            items.append(item)

    # Total network stats for context
    total_result = await db.execute(
        select(func.count(Contact.id)).where(
            Contact.user_id == user_id,
            Contact.deleted_at.is_(None),
        )
    )
    total = total_result.scalar_one()

    # Enrichment progress
    enriched_result = await db.execute(
        select(func.count(Contact.id)).where(
            Contact.user_id == user_id,
            Contact.deleted_at.is_(None),
            Contact.relationship_type.isnot(None),
        )
    )
    enriched = enriched_result.scalar_one()

    if total > 0 and enriched < total * 0.5:
        pct = round(enriched / total * 100) if total > 0 else 0
        dedup_key = _dedup("network_insight", "enrichment_progress", str(user_id))
        if not await _user_has_feed_item(db, user_id, dedup_key):
            item = FeedItem(
                user_id=user_id,
                item_type="network_insight",
                title=f"You've categorized {pct}% of your contacts",
                body=(
                    f"{enriched} of {total} contacts have relationship types. "
                    f"Categorizing more improves your referral match accuracy by ~30%."
                ),
                icon="bar-chart",
                action_url="/contacts",
                action_label="Categorize contacts",
                priority=50,
                dedup_key=dedup_key,
                metadata_={
                    "total_contacts": total,
                    "enriched_contacts": enriched,
                    "enrichment_pct": pct,
                },
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            )
            db.add(item)
            items.append(item)

    return items


# ---------------------------------------------------------------------------
# Generator 7: Intro Approval Nudge (encourage NH to share more after approval)
# "Nice one! You just helped someone get closer to their next role."
# ---------------------------------------------------------------------------


async def generate_intro_approval_nudge(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[FeedItem]:
    """After NH approves an intro, encourage them to share more connections."""
    recent = await db.execute(
        select(IntroFacilitation).where(
            IntroFacilitation.network_holder_id == user_id,
            IntroFacilitation.status == "approved",
            IntroFacilitation.reviewed_at
            >= datetime.now(timezone.utc) - timedelta(hours=24),
        )
    )

    items: list[FeedItem] = []
    for f in recent.scalars():
        dedup_key = _dedup("intro_approval_nudge", str(f.id))
        if await _user_has_feed_item(db, user_id, dedup_key):
            continue
        js_name = (f.job_seeker_profile_snapshot or {}).get("full_name", "someone")
        item = FeedItem(
            user_id=user_id,
            item_type="intro_approval_nudge",
            title="Nice one!",
            body=(
                f"You just helped {js_name} get one step closer to their next role. "
                f"The more connections you share, the more referral bonuses you can capture."
            ),
            icon="thumbs-up",
            action_url="/contacts",
            action_label="Share more connections",
            priority=60,
            dedup_key=dedup_key,
            metadata_={
                "intro_id": str(f.id),
                "job_seeker_name": js_name,
            },
            expires_at=datetime.now(timezone.utc) + timedelta(days=3),
        )
        db.add(item)
        items.append(item)

    return items


# ---------------------------------------------------------------------------
# Generator 8: Manual Send Reminder (NH approved but hasn't confirmed sending)
# "Did you send the intro to Sarah? Confirm here to earn your credits."
# ---------------------------------------------------------------------------


async def generate_manual_send_reminder(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[FeedItem]:
    """Nudge NH if they approved but haven't confirmed sending after 48 hours."""
    stale = await db.execute(
        select(IntroFacilitation).where(
            IntroFacilitation.network_holder_id == user_id,
            IntroFacilitation.status == "approved",
            IntroFacilitation.delivery_method.is_(None),
            IntroFacilitation.reviewed_at
            <= datetime.now(timezone.utc) - timedelta(hours=48),
        )
    )

    # Batch-load listings and contacts to avoid N+1 queries
    facilitations = list(stale.scalars())

    listing_ids = [
        f.marketplace_listing_id for f in facilitations if f.marketplace_listing_id
    ]
    listings_map: dict[uuid.UUID, MarketplaceListing] = {}
    contacts_map: dict[uuid.UUID, Contact] = {}

    if listing_ids:
        listing_result = await db.execute(
            select(MarketplaceListing).where(MarketplaceListing.id.in_(listing_ids))
        )
        listings_map = {ml.id: ml for ml in listing_result.scalars()}

        contact_ids = [ml.contact_id for ml in listings_map.values()]
        if contact_ids:
            contact_result = await db.execute(
                select(Contact).where(
                    Contact.id.in_(contact_ids),
                    Contact.user_id == user_id,
                )
            )
            contacts_map = {c.id: c for c in contact_result.scalars()}

    items: list[FeedItem] = []
    for f in facilitations:
        dedup_key = _dedup("manual_send_reminder", str(f.id))
        if await _user_has_feed_item(db, user_id, dedup_key):
            continue

        listing = (
            listings_map.get(f.marketplace_listing_id)
            if f.marketplace_listing_id
            else None
        )
        contact = contacts_map.get(listing.contact_id) if listing else None
        contact_name = contact.first_name if contact else "your contact"

        item = FeedItem(
            user_id=user_id,
            item_type="manual_send_reminder",
            title=f"Did you send the intro to {contact_name}?",
            body=(
                "You approved an intro request a couple of days ago. "
                "Once you send it, confirm here to earn your credits."
            ),
            icon="send",
            action_url="/marketplace",
            action_label="Confirm sent",
            priority=75,
            dedup_key=dedup_key,
            metadata_={
                "intro_id": str(f.id),
                "contact_name": contact_name,
            },
            expires_at=datetime.now(timezone.utc) + timedelta(days=5),
        )
        db.add(item)
        items.append(item)

    return items


# ---------------------------------------------------------------------------
# Orchestrator: run all generators for a single user
# ---------------------------------------------------------------------------


async def generate_feed_for_user(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[FeedItem]:
    """Run all feed generators for a single user. Returns new items created."""
    all_items: list[FeedItem] = []

    generators = [
        ("job_alerts", generate_job_alerts),
        ("enrichment_prompts", generate_enrichment_prompts),
        ("would_refer_prompts", generate_would_refer_prompts),
        ("last_interaction_prompts", generate_last_interaction_prompts),
        ("outcome_checks", generate_outcome_checks),
        ("marketplace_signals", generate_marketplace_signals),
        ("follow_up_nudges", generate_follow_up_nudges),
        ("network_insights", generate_network_insights),
        ("intro_approval_nudge", generate_intro_approval_nudge),
        ("manual_send_reminder", generate_manual_send_reminder),
    ]

    for name, gen_fn in generators:
        try:
            items = await gen_fn(user_id, db)
            all_items.extend(items)
            if items:
                logger.info(
                    "Feed generator %s created %d items for user %s",
                    name,
                    len(items),
                    user_id,
                )
        except Exception:
            logger.exception("Feed generator %s failed for user %s", name, user_id)

    return all_items


# ---------------------------------------------------------------------------
# Batch orchestrator: run for all active users
# ---------------------------------------------------------------------------


async def generate_feed_for_all_active_users(
    db: AsyncSession,
    active_days: int = 14,
) -> int:
    """Generate feed items for all users active in the last N days.

    Returns total number of feed items created across all users.
    """
    from app.models.enrichment import UsageLog

    since = datetime.now(timezone.utc) - timedelta(days=active_days)

    # Find distinct users who had any activity recently
    active_users = await db.execute(
        select(func.distinct(UsageLog.user_id)).where(
            UsageLog.created_at >= since,
        )
    )
    user_ids = [row[0] for row in active_users.all()]

    total_items = 0
    for uid in user_ids:
        try:
            items = await generate_feed_for_user(uid, db)
            total_items += len(items)
        except Exception:
            logger.exception("Feed generation failed for user %s", uid)

    await db.commit()
    logger.info(
        "Feed generation complete: %d items for %d users",
        total_items,
        len(user_ids),
    )
    return total_items


# ---------------------------------------------------------------------------
# Generator 11: CSV Completion Notification
# "Your CSV upload is complete — 1,234 new contacts scored and ready"
# ---------------------------------------------------------------------------


async def generate_csv_completion(
    user_id: uuid.UUID,
    db: AsyncSession,
    upload_id: uuid.UUID,
    contacts_created: int,
    duplicates_skipped: int,
) -> list[FeedItem]:
    """Create a feed item when CSV processing completes.

    Called directly from the import pipeline, not from the periodic generator.
    """
    dedup_key = _dedup("csv_completion", str(upload_id))
    if await _user_has_feed_item(db, user_id, dedup_key):
        return []

    contacts_str = f"{contacts_created:,}"
    body = (
        f"Your {contacts_str} contacts have been cleaned, scored, and imported. "
        f"You earned 100 credits for uploading."
    )
    if duplicates_skipped > 0:
        body += f" ({duplicates_skipped:,} duplicates skipped.)"

    item = FeedItem(
        user_id=user_id,
        item_type="csv_completion",
        title=f"Your CSV upload is complete — {contacts_str} new contacts!",
        body=body,
        icon="upload",
        action_url="/contacts",
        action_label="View contacts",
        priority=80,
        dedup_key=dedup_key,
        metadata_={
            "upload_id": str(upload_id),
            "contacts_created": contacts_created,
            "duplicates_skipped": duplicates_skipped,
        },
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(item)
    return [item]


# ---------------------------------------------------------------------------
# Feed digest: pick top unseen items for email
# ---------------------------------------------------------------------------


async def get_digest_items(
    user_id: uuid.UUID,
    db: AsyncSession,
    limit: int = 3,
) -> list[FeedItem]:
    """Get the top unseen feed items for email digest.

    Marks selected items with emailed_at timestamp.
    """
    result = await db.execute(
        select(FeedItem)
        .where(
            FeedItem.user_id == user_id,
            FeedItem.seen_at.is_(None),
            FeedItem.dismissed_at.is_(None),
            FeedItem.emailed_at.is_(None),
            FeedItem.expires_at > datetime.now(timezone.utc),
        )
        .order_by(FeedItem.priority.desc(), FeedItem.created_at.desc())
        .limit(limit)
    )
    items = list(result.scalars().all())

    now = datetime.now(timezone.utc)
    for item in items:
        item.emailed_at = now

    return items
