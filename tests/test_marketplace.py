"""Tests for marketplace indexing, anonymization, and sharing preferences."""

import uuid as uuid_mod
from datetime import date, timedelta

import pytest_asyncio
from httpx import AsyncClient

from app.models.company import Company
from app.models.contact import Contact
from app.models.marketplace import MarketplaceListing, NetworkSharingPreferences
from app.models.match_result import WarmScore
from app.services.marketplace_indexer import (
    classify_connection_recency,
    classify_department,
    classify_role_level,
    classify_warm_score_range,
    generate_marketplace_listings,
)
from tests.conftest import TestSessionLocal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "marketplace@test.com",
            "password": "testpass123",
            "full_name": "Marketplace Tester",
        },
    )
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "marketplace@test.com", "password": "testpass123"},
    )
    token = login_res.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def user_id(auth_headers: dict, client: AsyncClient) -> str:
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    return resp.json()["data"]["id"]


@pytest_asyncio.fixture
async def company_and_contacts(user_id: str):
    """Create a company and contacts for marketplace indexing tests."""
    uid = uuid_mod.UUID(user_id)
    async with TestSessionLocal() as db:
        company = Company(name="Stripe", domain="stripe.com")
        db.add(company)
        await db.flush()

        contacts = [
            Contact(
                user_id=uid,
                full_name="Alice Engineer",
                first_name="Alice",
                last_name="Engineer",
                email="alice@stripe.com",
                current_title="Senior Software Engineer",
                current_company="Stripe",
                company_id=company.id,
                connected_on=date.today() - timedelta(days=180),
            ),
            Contact(
                user_id=uid,
                full_name="Bob VP",
                first_name="Bob",
                last_name="VP",
                email="bob@stripe.com",
                current_title="VP of Engineering",
                current_company="Stripe",
                company_id=company.id,
                connected_on=date.today() - timedelta(days=800),
            ),
            Contact(
                user_id=uid,
                full_name="Charlie Design",
                first_name="Charlie",
                last_name="Design",
                email="charlie@stripe.com",
                current_title="Junior Product Designer",
                current_company="Stripe",
                company_id=company.id,
                connected_on=date.today() - timedelta(days=1500),
            ),
        ]
        for c in contacts:
            db.add(c)
        await db.flush()

        # Add warm scores
        db.add(WarmScore(
            user_id=uid,
            contact_id=contacts[0].id,
            total_score=80,
            recency_score=90,
            tenure_score=70,
            context_score=80,
            role_score=75,
            referral_likelihood="high",
        ))
        db.add(WarmScore(
            user_id=uid,
            contact_id=contacts[1].id,
            total_score=55,
            recency_score=40,
            tenure_score=60,
            context_score=50,
            role_score=70,
            referral_likelihood="medium",
        ))
        db.add(WarmScore(
            user_id=uid,
            contact_id=contacts[2].id,
            total_score=30,
            recency_score=20,
            tenure_score=30,
            context_score=40,
            role_score=30,
            referral_likelihood="low",
        ))
        await db.commit()

        return {
            "company_id": company.id,
            "contact_ids": [c.id for c in contacts],
        }


# ---------------------------------------------------------------------------
# Test Classification Helpers
# ---------------------------------------------------------------------------


class TestClassifyRoleLevel:
    def test_senior(self):
        assert classify_role_level("Senior Software Engineer") == "senior"

    def test_vp(self):
        assert classify_role_level("VP of Engineering") == "vp"

    def test_c_suite(self):
        assert classify_role_level("CTO") == "c_suite"

    def test_director(self):
        assert classify_role_level("Director of Product") == "director"

    def test_lead(self):
        assert classify_role_level("Staff Engineer") == "lead"

    def test_junior(self):
        assert classify_role_level("Junior Analyst") == "junior"

    def test_mid_default(self):
        assert classify_role_level("Software Engineer") == "mid"

    def test_none_defaults_to_mid(self):
        assert classify_role_level(None) == "mid"

    def test_principal(self):
        assert classify_role_level("Principal Engineer") == "lead"

    def test_intern(self):
        assert classify_role_level("Engineering Intern") == "junior"

    def test_chief(self):
        assert classify_role_level("Chief Revenue Officer") == "c_suite"

    def test_vice_president(self):
        assert classify_role_level("Vice President of Sales") == "vp"


class TestClassifyDepartment:
    def test_engineering(self):
        assert classify_department("Software Engineer") == "engineering"

    def test_product(self):
        assert classify_department("Product Manager") == "product"

    def test_design(self):
        assert classify_department("UX Designer") == "design"

    def test_marketing(self):
        assert classify_department("Growth Marketing Manager") == "marketing"

    def test_sales(self):
        assert classify_department("Account Executive") == "sales"

    def test_hr(self):
        assert classify_department("Talent Recruiter") == "hr"

    def test_finance(self):
        assert classify_department("FP&A Analyst") == "finance"

    def test_legal(self):
        assert classify_department("General Counsel") == "legal"

    def test_ops(self):
        assert classify_department("Operations Manager") == "ops"

    def test_other_default(self):
        assert classify_department("Office Barista") == "other"

    def test_none(self):
        assert classify_department(None) == "other"

    def test_data_scientist(self):
        assert classify_department("Data Scientist") == "engineering"

    def test_sdr(self):
        assert classify_department("SDR") == "sales"


class TestClassifyWarmScoreRange:
    def test_high(self):
        assert classify_warm_score_range(85) == "high"

    def test_medium(self):
        assert classify_warm_score_range(55) == "medium"

    def test_low(self):
        assert classify_warm_score_range(20) == "low"

    def test_boundary_70(self):
        assert classify_warm_score_range(70) == "medium"

    def test_boundary_71(self):
        assert classify_warm_score_range(71) == "high"

    def test_boundary_40(self):
        assert classify_warm_score_range(40) == "medium"

    def test_boundary_39(self):
        assert classify_warm_score_range(39) == "low"

    def test_none(self):
        assert classify_warm_score_range(None) == "low"


class TestClassifyConnectionRecency:
    def test_recent(self):
        assert classify_connection_recency(date.today() - timedelta(days=100)) == "recent"

    def test_moderate(self):
        assert classify_connection_recency(date.today() - timedelta(days=600)) == "moderate"

    def test_stale(self):
        assert classify_connection_recency(date.today() - timedelta(days=1500)) == "stale"

    def test_none(self):
        assert classify_connection_recency(None) == "stale"


# ---------------------------------------------------------------------------
# Test Marketplace Listing Generation
# ---------------------------------------------------------------------------


class TestGenerateMarketplaceListings:
    async def test_no_prefs_returns_zero(self, user_id: str):
        """No sharing preferences = no listings generated."""
        uid = uuid_mod.UUID(user_id)
        async with TestSessionLocal() as db:
            count = await generate_marketplace_listings(uid, db)
            assert count == 0

    async def test_opted_out_returns_zero(self, user_id: str):
        """Opted out of marketplace = no listings generated."""
        uid = uuid_mod.UUID(user_id)
        async with TestSessionLocal() as db:
            db.add(NetworkSharingPreferences(
                user_id=uid, opt_in_marketplace=False
            ))
            await db.flush()
            count = await generate_marketplace_listings(uid, db)
            assert count == 0

    async def test_paused_returns_zero(self, user_id: str, company_and_contacts):
        """Paused sharing = no listings generated."""
        uid = uuid_mod.UUID(user_id)
        async with TestSessionLocal() as db:
            db.add(NetworkSharingPreferences(
                user_id=uid, opt_in_marketplace=True, is_paused=True
            ))
            await db.flush()
            count = await generate_marketplace_listings(uid, db)
            assert count == 0

    async def test_generates_listings(self, user_id: str, company_and_contacts):
        """Opted-in network holder gets listings for all contacts."""
        uid = uuid_mod.UUID(user_id)
        async with TestSessionLocal() as db:
            db.add(NetworkSharingPreferences(
                user_id=uid, opt_in_marketplace=True
            ))
            await db.flush()
            count = await generate_marketplace_listings(uid, db)
            assert count == 3

    async def test_listings_are_anonymized(self, user_id: str, company_and_contacts):
        """Listings contain no PII — only anonymized fields."""
        uid = uuid_mod.UUID(user_id)
        async with TestSessionLocal() as db:
            db.add(NetworkSharingPreferences(
                user_id=uid, opt_in_marketplace=True
            ))
            await db.flush()
            await generate_marketplace_listings(uid, db)
            await db.flush()

            result = await db.execute(
                MarketplaceListing.__table__.select().where(
                    MarketplaceListing.network_holder_id == uid,
                    MarketplaceListing.deleted_at.is_(None),
                )
            )
            rows = result.fetchall()
            assert len(rows) == 3

            for row in rows:
                # Anonymized fields present
                assert row.role_level in (
                    "junior", "mid", "senior", "lead", "director", "vp", "c_suite"
                )
                assert row.department_category in (
                    "engineering", "product", "design", "marketing", "sales",
                    "ops", "finance", "hr", "legal", "other"
                )
                assert row.warm_score_range in ("high", "medium", "low")
                assert row.connection_recency in ("recent", "moderate", "stale")

    async def test_correct_role_levels(self, user_id: str, company_and_contacts):
        """Role levels match the contact titles."""
        uid = uuid_mod.UUID(user_id)
        async with TestSessionLocal() as db:
            db.add(NetworkSharingPreferences(
                user_id=uid, opt_in_marketplace=True
            ))
            await db.flush()
            await generate_marketplace_listings(uid, db)
            await db.flush()

            result = await db.execute(
                MarketplaceListing.__table__.select().where(
                    MarketplaceListing.network_holder_id == uid,
                    MarketplaceListing.deleted_at.is_(None),
                ).order_by(MarketplaceListing.role_level)
            )
            rows = result.fetchall()
            role_levels = sorted(r.role_level for r in rows)
            # Alice=senior, Bob=vp, Charlie=junior
            assert role_levels == ["junior", "senior", "vp"]

    async def test_correct_warm_score_ranges(self, user_id: str, company_and_contacts):
        """Warm score ranges derived from actual warm scores."""
        uid = uuid_mod.UUID(user_id)
        async with TestSessionLocal() as db:
            db.add(NetworkSharingPreferences(
                user_id=uid, opt_in_marketplace=True
            ))
            await db.flush()
            await generate_marketplace_listings(uid, db)
            await db.flush()

            result = await db.execute(
                MarketplaceListing.__table__.select().where(
                    MarketplaceListing.network_holder_id == uid,
                    MarketplaceListing.deleted_at.is_(None),
                ).order_by(MarketplaceListing.warm_score_range)
            )
            rows = result.fetchall()
            ranges = sorted(r.warm_score_range for r in rows)
            # Alice=80(high), Bob=55(medium), Charlie=30(low)
            assert ranges == ["high", "low", "medium"]

    async def test_excluded_contacts_skipped(self, user_id: str, company_and_contacts):
        """Excluded contacts don't get marketplace listings."""
        uid = uuid_mod.UUID(user_id)
        contact_ids = company_and_contacts["contact_ids"]
        excluded_id = str(contact_ids[0])  # Exclude Alice

        async with TestSessionLocal() as db:
            db.add(NetworkSharingPreferences(
                user_id=uid,
                opt_in_marketplace=True,
                excluded_contact_ids=[excluded_id],
            ))
            await db.flush()
            count = await generate_marketplace_listings(uid, db)
            assert count == 2  # Bob and Charlie only

    async def test_department_filter(self, user_id: str, company_and_contacts):
        """Category filters restrict listings to specific departments."""
        uid = uuid_mod.UUID(user_id)
        async with TestSessionLocal() as db:
            db.add(NetworkSharingPreferences(
                user_id=uid,
                opt_in_marketplace=True,
                category_filters={"include_departments": ["engineering"]},
            ))
            await db.flush()
            count = await generate_marketplace_listings(uid, db)
            # Alice (Senior Software Engineer) = engineering
            # Bob (VP of Engineering) = engineering
            # Charlie (Junior Product Designer) = design -> excluded
            assert count == 2

    async def test_regeneration_replaces_old_listings(
        self, user_id: str, company_and_contacts
    ):
        """Re-running indexer soft-deletes old listings and creates new ones."""
        uid = uuid_mod.UUID(user_id)
        async with TestSessionLocal() as db:
            db.add(NetworkSharingPreferences(
                user_id=uid, opt_in_marketplace=True
            ))
            await db.flush()

            # First run
            count1 = await generate_marketplace_listings(uid, db)
            assert count1 == 3

            # Second run should soft-delete old and create new
            count2 = await generate_marketplace_listings(uid, db)
            assert count2 == 3

            # Check only 3 active (not deleted) listings
            await db.flush()
            result = await db.execute(
                MarketplaceListing.__table__.select().where(
                    MarketplaceListing.network_holder_id == uid,
                    MarketplaceListing.deleted_at.is_(None),
                )
            )
            active = result.fetchall()
            assert len(active) == 3

    async def test_company_exclusion_filter(self, user_id: str, company_and_contacts):
        """Exclude companies filter prevents listings for that company."""
        uid = uuid_mod.UUID(user_id)
        company_id = company_and_contacts["company_id"]

        async with TestSessionLocal() as db:
            db.add(NetworkSharingPreferences(
                user_id=uid,
                opt_in_marketplace=True,
                category_filters={"exclude_companies": [str(company_id)]},
            ))
            await db.flush()
            count = await generate_marketplace_listings(uid, db)
            assert count == 0  # All contacts at Stripe, which is excluded
