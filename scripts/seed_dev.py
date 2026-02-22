"""Idempotent dev seed script for WarmPath.

Populates a local Postgres DB with realistic test data:
- 3 users (seeker, network holder, dual-role)
- 5 companies (Stripe, Google, Shopee, Grab, DBS)
- 50 contacts belonging to the network holder (10 per company)
- 30 marketplace listings (holder opts in 30 of 50 contacts)
- Credit transactions (100 credits per user for csv_upload)
- 5 feed items for the seeker
- 3 applications for the seeker

Usage:
    python3 -m scripts.seed_dev
"""

import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# ---------------------------------------------------------------------------
# Ensure the app root is on sys.path so `app.*` imports work
# ---------------------------------------------------------------------------
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app.models.company import Company  # noqa: E402
from app.models.contact import Contact  # noqa: E402
from app.models.credits import CreditTransaction  # noqa: E402
from app.models.feed import FeedItem  # noqa: E402
from app.models.job import Application  # noqa: E402
from app.models.marketplace import MarketplaceListing  # noqa: E402
from app.models.user import User  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "[DATABASE_URL_REDACTED]",
)

# Stable UUIDs for seed data — makes re-runs idempotent and cross-references easy
SEEKER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
HOLDER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
DUAL_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")

SEED_EMAILS = {
    "seeker@test.dev": SEEKER_ID,
    "holder@test.dev": HOLDER_ID,
    "dual@test.dev": DUAL_ID,
}

# Company definitions: (name, domain, industry, size, headquarters)
COMPANY_DEFS = [
    ("Stripe", "stripe.com", "Fintech", "1001-5000", "San Francisco, CA"),
    ("Google", "google.com", "Technology", "10001+", "Mountain View, CA"),
    ("Shopee", "shopee.com", "E-commerce", "10001+", "Singapore"),
    ("Grab", "grab.com", "Technology", "5001-10000", "Singapore"),
    ("DBS", "dbs.com", "Banking", "10001+", "Singapore"),
]

# Contact templates per company: (first, last, title, dept_category, role_level)
CONTACT_TEMPLATES = {
    "Stripe": [
        ("Alex", "Chen", "Senior Software Engineer", "engineering", "senior"),
        ("Maria", "Rodriguez", "Staff Engineer", "engineering", "staff"),
        ("James", "Kim", "Engineering Manager", "engineering", "manager"),
        ("Sarah", "Patel", "Product Manager", "product", "mid"),
        ("David", "Tanaka", "Senior Product Designer", "design", "senior"),
        ("Emily", "Johansson", "Data Scientist", "data", "mid"),
        ("Michael", "Brown", "DevOps Engineer", "engineering", "mid"),
        ("Lisa", "Nguyen", "Technical Recruiter", "hr", "mid"),
        ("Robert", "Garcia", "Finance Manager", "finance", "manager"),
        ("Priya", "Sharma", "Backend Engineer", "engineering", "mid"),
    ],
    "Google": [
        ("Wei", "Zhang", "Staff Software Engineer", "engineering", "staff"),
        ("Jennifer", "O'Brien", "Senior UX Researcher", "design", "senior"),
        ("Raj", "Gupta", "Principal Engineer", "engineering", "principal"),
        ("Amanda", "Lee", "Product Lead", "product", "lead"),
        ("Chris", "Williams", "SRE Manager", "engineering", "manager"),
        ("Fatima", "Al-Hassan", "Machine Learning Engineer", "engineering", "senior"),
        ("Tom", "Anderson", "Program Manager", "operations", "mid"),
        ("Yuki", "Sato", "Security Engineer", "engineering", "senior"),
        ("Natasha", "Ivanova", "Data Engineer", "data", "mid"),
        ("Kevin", "Park", "Software Engineer", "engineering", "mid"),
    ],
    "Shopee": [
        ("Boon", "Lim", "Senior Backend Engineer", "engineering", "senior"),
        ("Mei", "Tan", "Product Manager", "product", "mid"),
        ("Arjun", "Nair", "Tech Lead", "engineering", "lead"),
        ("Siti", "Aminah", "QA Engineer", "engineering", "mid"),
        ("Daniel", "Ong", "Frontend Developer", "engineering", "mid"),
        ("Nurul", "Huda", "Business Analyst", "operations", "mid"),
        ("Cheng", "Wei", "DevOps Engineer", "engineering", "mid"),
        ("Aisha", "Rahman", "UX Designer", "design", "mid"),
        ("Jun", "Ho", "Data Analyst", "data", "junior"),
        ("Kai", "Xuan", "Mobile Engineer", "engineering", "senior"),
    ],
    "Grab": [
        ("Ming", "Teo", "Senior Platform Engineer", "engineering", "senior"),
        ("Ravi", "Kumar", "Engineering Director", "engineering", "director"),
        ("Ling", "Wong", "Senior Product Manager", "product", "senior"),
        ("Hafiz", "Ibrahim", "ML Engineer", "engineering", "mid"),
        ("Tanya", "Santos", "People Operations Lead", "hr", "lead"),
        ("Vishal", "Mehta", "Staff Backend Engineer", "engineering", "staff"),
        ("Pei", "Lin", "Growth Marketing Manager", "marketing", "manager"),
        ("Ahmad", "Zulkifli", "iOS Developer", "engineering", "mid"),
        ("Jasmine", "Chua", "Corporate Finance Analyst", "finance", "mid"),
        ("Dian", "Permata", "Android Engineer", "engineering", "mid"),
    ],
    "DBS": [
        ("Kenneth", "Goh", "VP Technology", "engineering", "vp"),
        ("Swee", "Lian", "Senior Developer", "engineering", "senior"),
        ("Arun", "Pillai", "Quantitative Analyst", "data", "senior"),
        ("Michelle", "Foo", "Digital Banking PM", "product", "mid"),
        ("Jia", "Hao", "Cloud Architect", "engineering", "senior"),
        ("Deepa", "Krishnan", "Risk Analytics Lead", "data", "lead"),
        ("Chong", "Ming", "Software Engineer", "engineering", "mid"),
        ("Farah", "Ismail", "Compliance Officer", "operations", "mid"),
        ("Yong", "Sheng", "Platform Engineer", "engineering", "mid"),
        ("Rani", "Devi", "IT Project Manager", "operations", "manager"),
    ],
}

# Warm score ranges and connection recency values for marketplace listings
WARM_RANGES = ["70-80", "60-70", "80-90", "50-60", "75-85"]
RECENCY_VALUES = ["recent", "moderate", "stale"]

# Relationship types used in contacts
RELATIONSHIP_TYPES = [
    "colleague",
    "former_colleague",
    "classmate",
    "friend",
    "acquaintance",
    "manager",
    "former_manager",
    "alumni",
]


def _build_sync_engine():
    """Create a sync SQLAlchemy engine from DATABASE_URL."""
    url = DATABASE_URL
    # Normalize to psycopg2 sync driver
    url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(url, echo=False)


def _seed_users_exist(session: Session) -> bool:
    """Check if all 3 seed users already exist."""
    result = session.execute(
        text("SELECT COUNT(*) FROM users WHERE email IN (:e1, :e2, :e3)"),
        {"e1": "seeker@test.dev", "e2": "holder@test.dev", "e3": "dual@test.dev"},
    )
    count = result.scalar()
    return count == len(SEED_EMAILS)


def _create_users(session: Session) -> dict[str, User]:
    """Create the 3 seed users. Returns {email: User}."""
    now = datetime.now(timezone.utc)
    users_map: dict[str, User] = {}

    user_defs = [
        {
            "id": SEEKER_ID,
            "email": "seeker@test.dev",
            "full_name": "Sam Seeker",
            "plan_tier": "pro",
            "intent": "find_referrals",
            "email_verified": True,
            "is_active": True,
            "clerk_user_id": "seed_clerk_seeker",
            "onboarding_completed_at": now,
        },
        {
            "id": HOLDER_ID,
            "email": "holder@test.dev",
            "full_name": "Hannah Holder",
            "plan_tier": "free",
            "intent": "share_network",
            "email_verified": True,
            "is_active": True,
            "clerk_user_id": "seed_clerk_holder",
            "onboarding_completed_at": now,
        },
        {
            "id": DUAL_ID,
            "email": "dual@test.dev",
            "full_name": "Dana Dual",
            "plan_tier": "pro",
            "intent": "explore",
            "email_verified": True,
            "is_active": True,
            "clerk_user_id": "seed_clerk_dual",
            "onboarding_completed_at": now,
        },
    ]

    for udef in user_defs:
        user = User(**udef)
        session.add(user)
        users_map[udef["email"]] = user

    session.flush()
    return users_map


def _create_companies(session: Session) -> dict[str, Company]:
    """Create 5 companies. Returns {name: Company}."""
    companies_map: dict[str, Company] = {}
    for name, domain, industry, size, hq in COMPANY_DEFS:
        company = Company(
            name=name,
            domain=domain,
            industry=industry,
            company_size=size,
            headquarters=hq,
        )
        session.add(company)
        companies_map[name] = company
    session.flush()
    return companies_map


def _create_contacts(
    session: Session,
    holder: User,
    companies: dict[str, Company],
) -> list[Contact]:
    """Create 50 contacts (10 per company) belonging to the holder. Returns all contacts."""
    all_contacts: list[Contact] = []
    base_date = date(2023, 6, 15)

    for company_name, templates in CONTACT_TEMPLATES.items():
        company = companies[company_name]
        for i, (first, last, title, _dept, _role_level) in enumerate(templates):
            connected = base_date + timedelta(days=i * 30)
            rel_type = RELATIONSHIP_TYPES[i % len(RELATIONSHIP_TYPES)]
            would_refer_options = ["definitely", "probably", "maybe", "no"]

            contact = Contact(
                user_id=holder.id,
                first_name=first,
                last_name=last,
                full_name=f"{first} {last}",
                email=f"{first.lower()}.{last.lower()}@{company_name.lower()}.example",
                current_title=title,
                current_company=company_name,
                company_id=company.id,
                location=company.headquarters or "Singapore",
                connected_on=connected,
                relationship_type=rel_type,
                would_refer=would_refer_options[i % len(would_refer_options)],
                source="linkedin_csv",
            )
            session.add(contact)
            all_contacts.append(contact)

    session.flush()
    return all_contacts


def _create_marketplace_listings(
    session: Session,
    holder: User,
    contacts: list[Contact],
    companies: dict[str, Company],
) -> list[MarketplaceListing]:
    """Create 30 marketplace listings from the first 30 contacts (6 per company)."""
    listings: list[MarketplaceListing] = []
    # Take first 6 contacts from each company = 30 total
    selected_contacts = (
        contacts[:6]
        + contacts[10:16]
        + contacts[20:26]
        + contacts[30:36]
        + contacts[40:46]
    )

    for i, contact in enumerate(selected_contacts):
        # Look up template data for this contact
        company_name = contact.current_company
        company = companies[company_name]
        # Find the matching template to get dept_category and role_level
        templates = CONTACT_TEMPLATES[company_name]
        # Determine the contact's index within its company group
        company_start = list(CONTACT_TEMPLATES.keys()).index(company_name) * 10
        contact_idx_in_company = contacts.index(contact) - company_start
        _first, _last, _title, dept_category, role_level = templates[
            contact_idx_in_company
        ]

        listing = MarketplaceListing(
            network_holder_id=holder.id,
            contact_id=contact.id,
            company_id=company.id,
            role_level=role_level,
            department_category=dept_category,
            warm_score_range=WARM_RANGES[i % len(WARM_RANGES)],
            connection_recency=RECENCY_VALUES[i % len(RECENCY_VALUES)],
            is_available=True,
        )
        session.add(listing)
        listings.append(listing)

    session.flush()
    return listings


def _create_credit_transactions(
    session: Session,
    users: dict[str, User],
) -> None:
    """Award 100 credits to each user for csv_upload."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=365)

    for user in users.values():
        txn = CreditTransaction(
            user_id=user.id,
            amount=100,
            type="earn",
            reason="csv_upload",
            expires_at=expires,
        )
        session.add(txn)

    session.flush()


def _create_feed_items(session: Session, seeker: User) -> None:
    """Create 5 feed items for the seeker."""
    feed_defs = [
        {
            "item_type": "job_alert",
            "title": "New Senior Engineer opening at Stripe",
            "body": "A contact at Stripe could refer you for this role.",
            "priority": 85,
            "action_url": "/search?company=Stripe",
            "action_label": "View matches",
            "icon": "briefcase",
            "dedup_key": "job_alert:stripe:seed",
        },
        {
            "item_type": "marketplace_signal",
            "title": "3 new connections available at Google",
            "body": "Network holders recently shared Google contacts in the marketplace.",
            "priority": 70,
            "action_url": "/marketplace?company=Google",
            "action_label": "Browse marketplace",
            "icon": "globe",
            "dedup_key": "marketplace_signal:google:seed",
        },
        {
            "item_type": "enrichment_prompt",
            "title": "Tell us more about your Grab contacts",
            "body": "Adding relationship context improves your warm scores.",
            "priority": 55,
            "action_url": "/contacts?company=Grab",
            "action_label": "Enrich contacts",
            "icon": "sparkles",
            "dedup_key": "enrichment_prompt:grab:seed",
        },
        {
            "item_type": "outcome_check",
            "title": "Any updates on your DBS application?",
            "body": "You applied 2 weeks ago. Let us know how it went.",
            "priority": 60,
            "action_url": "/applications",
            "action_label": "Update status",
            "icon": "clipboard",
            "dedup_key": "outcome_check:dbs:seed",
        },
        {
            "item_type": "network_insight",
            "title": "Your network covers 5 target companies",
            "body": "You have warm paths into Stripe, Google, Shopee, Grab, and DBS.",
            "priority": 40,
            "action_url": "/dashboard",
            "action_label": "View dashboard",
            "icon": "chart",
            "dedup_key": "network_insight:coverage:seed",
        },
    ]

    for fdef in feed_defs:
        item = FeedItem(user_id=seeker.id, **fdef)
        session.add(item)

    session.flush()


def _create_applications(
    session: Session,
    seeker: User,
    companies: dict[str, Company],
) -> None:
    """Create 3 applications for the seeker."""
    app_defs = [
        {
            "company_name": "Stripe",
            "company_id": companies["Stripe"].id,
            "role_title": "Senior Backend Engineer",
            "status": "message_sent",
            "source_type": "marketplace",
        },
        {
            "company_name": "Google",
            "company_id": companies["Google"].id,
            "role_title": "Staff Software Engineer",
            "status": "draft",
            "source_type": "own_network",
        },
        {
            "company_name": "DBS",
            "company_id": companies["DBS"].id,
            "role_title": "Platform Engineer",
            "status": "interview_scheduled",
            "source_type": "marketplace",
        },
    ]

    for adef in app_defs:
        app = Application(user_id=seeker.id, **adef)
        session.add(app)

    session.flush()


def seed() -> None:
    """Main seed function — idempotent."""
    engine = _build_sync_engine()
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()

    try:
        # Idempotency check: skip if seed users already exist
        if _seed_users_exist(session):
            print("[seed_dev] Seed users already exist — skipping. (Idempotent)")
            return

        print("[seed_dev] Seeding dev database...")

        # 1. Users
        users = _create_users(session)
        seeker = users["seeker@test.dev"]
        holder = users["holder@test.dev"]
        print(f"  Created {len(users)} users")

        # 2. Companies
        companies = _create_companies(session)
        print(f"  Created {len(companies)} companies")

        # 3. Contacts (50 belonging to holder)
        contacts = _create_contacts(session, holder, companies)
        print(f"  Created {len(contacts)} contacts for holder")

        # 4. Marketplace listings (30 of 50 contacts)
        listings = _create_marketplace_listings(session, holder, contacts, companies)
        print(f"  Created {len(listings)} marketplace listings")

        # 5. Credit transactions (100 per user)
        _create_credit_transactions(session, users)
        print(f"  Created credit transactions ({len(users)} x 100 credits)")

        # 6. Feed items (5 for seeker)
        _create_feed_items(session, seeker)
        print("  Created 5 feed items for seeker")

        # 7. Applications (3 for seeker)
        _create_applications(session, seeker, companies)
        print("  Created 3 applications for seeker")

        session.commit()
        print("[seed_dev] Done. Dev database seeded successfully.")

    except Exception:
        session.rollback()
        print("[seed_dev] Error — rolled back transaction.")
        raise
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    seed()
