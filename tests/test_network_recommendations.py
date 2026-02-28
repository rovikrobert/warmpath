"""Tests for the network-driven recommendation service.

Verifies that get_network_recommendations correctly merges a user's own
contacts with opted-in marketplace listings to surface companies where the
user has the strongest referral network.
"""

import pytest
import pytest_asyncio

from app.models.company import Company
from app.models.contact import Contact
from app.models.marketplace import MarketplaceListing, NetworkSharingPreferences
from app.services.network_recommendations import get_network_recommendations
from tests.conftest import TestSessionLocal, create_test_user_in_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session(truncate_tables):
    """Yield a test DB session."""
    async with TestSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNetworkRecommendations:
    @pytest.mark.asyncio
    async def test_returns_companies_from_marketplace_listings(self, db_session):
        """Marketplace listings from opted-in holders appear in recommendations."""
        # Create the requesting user (job seeker)
        seeker, _ = await create_test_user_in_db(
            db_session, email="seeker@test.com", full_name="Job Seeker"
        )

        # Create a network holder with opted-in prefs
        holder, _ = await create_test_user_in_db(
            db_session, email="holder@test.com", full_name="Network Holder"
        )
        db_session.add(
            NetworkSharingPreferences(
                user_id=holder.id,
                opt_in_marketplace=True,
                is_paused=False,
            )
        )

        # Create a company
        company = Company(name="Stripe", domain="stripe.com")
        db_session.add(company)
        await db_session.flush()

        # Create a contact owned by the holder
        contact = Contact(
            user_id=holder.id,
            full_name="Alice Engineer",
            email="alice@stripe.com",
            current_company="Stripe",
            company_id=company.id,
        )
        db_session.add(contact)
        await db_session.flush()

        # Create a marketplace listing for that contact
        listing = MarketplaceListing(
            network_holder_id=holder.id,
            contact_id=contact.id,
            company_id=company.id,
            role_level="senior",
            department_category="engineering",
            warm_sco[RESEND_KEY_REDACTED]="70-80",
            connection_recency="recent",
            is_available=True,
        )
        db_session.add(listing)
        await db_session.commit()

        # Call as the seeker
        results = await get_network_recommendations(
            user_id=seeker.id,
            target_locations=None,
            exclude_companies=None,
            target_industries=None,
            limit=10,
            db=db_session,
        )

        assert len(results) >= 1
        stripe_rec = next((r for r in results if r["company_name"] == "stripe"), None)
        assert stripe_rec is not None
        assert stripe_rec["network_density"] >= 1
        assert stripe_rec["marketplace_listings"] >= 1
        assert stripe_rec["source"] == "network_signal"

    @pytest.mark.asyncio
    async def test_excludes_paused_holders(self, db_session):
        """Marketplace listings from paused holders should NOT appear."""
        seeker, _ = await create_test_user_in_db(
            db_session, email="seeker2@test.com", full_name="Job Seeker 2"
        )

        holder, _ = await create_test_user_in_db(
            db_session, email="holder2@test.com", full_name="Paused Holder"
        )
        db_session.add(
            NetworkSharingPreferences(
                user_id=holder.id,
                opt_in_marketplace=True,
                is_paused=True,  # Paused!
            )
        )

        company = Company(name="Notion", domain="notion.so")
        db_session.add(company)
        await db_session.flush()

        contact = Contact(
            user_id=holder.id,
            full_name="Bob Designer",
            email="bob@notion.so",
            current_company="Notion",
            company_id=company.id,
        )
        db_session.add(contact)
        await db_session.flush()

        listing = MarketplaceListing(
            network_holder_id=holder.id,
            contact_id=contact.id,
            company_id=company.id,
            role_level="mid",
            department_category="design",
            warm_sco[RESEND_KEY_REDACTED]="60-70",
            connection_recency="recent",
            is_available=True,
        )
        db_session.add(listing)
        await db_session.commit()

        results = await get_network_recommendations(
            user_id=seeker.id,
            target_locations=None,
            exclude_companies=None,
            target_industries=None,
            limit=10,
            db=db_session,
        )

        notion_rec = next((r for r in results if r["company_name"] == "notion"), None)
        assert notion_rec is None

    @pytest.mark.asyncio
    async def test_includes_own_contacts(self, db_session):
        """User's own contacts at a company should appear even without marketplace listings."""
        user, _ = await create_test_user_in_db(
            db_session, email="owncontacts@test.com", full_name="Own Contacts User"
        )

        company = Company(name="Figma", domain="figma.com")
        db_session.add(company)
        await db_session.flush()

        # Two contacts at Figma
        for i, name in enumerate(["Carol PM", "Dave Eng"]):
            db_session.add(
                Contact(
                    user_id=user.id,
                    full_name=name,
                    email=f"person{i}@figma.com",
                    current_company="Figma",
                    company_id=company.id,
                )
            )
        await db_session.commit()

        results = await get_network_recommendations(
            user_id=user.id,
            target_locations=None,
            exclude_companies=None,
            target_industries=None,
            limit=10,
            db=db_session,
        )

        figma_rec = next((r for r in results if r["company_name"] == "figma"), None)
        assert figma_rec is not None
        assert figma_rec["own_contacts"] == 2
        assert figma_rec["marketplace_listings"] == 0
        assert figma_rec["network_density"] == 2
        assert "your network" in figma_rec["network_label"]

    @pytest.mark.asyncio
    async def test_exclude_companies(self, db_session):
        """Companies in the exclude_companies list should be filtered out."""
        user, _ = await create_test_user_in_db(
            db_session, email="excludetest@test.com", full_name="Exclude Tester"
        )

        company = Company(name="Google", domain="google.com")
        db_session.add(company)
        await db_session.flush()

        db_session.add(
            Contact(
                user_id=user.id,
                full_name="Eve SRE",
                email="eve@google.com",
                current_company="Google",
                company_id=company.id,
            )
        )
        await db_session.commit()

        results = await get_network_recommendations(
            user_id=user.id,
            target_locations=None,
            exclude_companies=["google"],
            target_industries=None,
            limit=10,
            db=db_session,
        )

        google_rec = next((r for r in results if r["company_name"] == "google"), None)
        assert google_rec is None

    @pytest.mark.asyncio
    async def test_returns_careers_url(self, db_session):
        """Companies in the board registry should return a careers_url."""
        user, _ = await create_test_user_in_db(
            db_session, email="careersurl@test.com", full_name="Careers URL Tester"
        )

        company = Company(name="Stripe", domain="stripe.com")
        db_session.add(company)
        await db_session.flush()

        db_session.add(
            Contact(
                user_id=user.id,
                full_name="Frank Eng",
                email="frank@stripe.com",
                current_company="Stripe",
                company_id=company.id,
            )
        )
        await db_session.commit()

        results = await get_network_recommendations(
            user_id=user.id,
            target_locations=None,
            exclude_companies=None,
            target_industries=None,
            limit=10,
            db=db_session,
        )

        stripe_rec = next((r for r in results if r["company_name"] == "stripe"), None)
        assert stripe_rec is not None
        assert stripe_rec["careers_url"] == "https://stripe.com/jobs"
