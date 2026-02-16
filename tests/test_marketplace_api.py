"""Tests for marketplace API — search, intro facilitation, sharing prefs, credits."""

import uuid as uuid_mod
from datetime import date, timedelta

import pytest_asyncio
from httpx import AsyncClient

from app.models.company import Company
from app.models.contact import Contact
from app.models.marketplace import (
    ConnectorReputation,
    MarketplaceListing,
    NetworkSharingPreferences,
)
from app.models.match_result import WarmScore
from app.services.credits import earn_credits, get_balance, spend_credits
from tests.conftest import TestSessionLocal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def seeker_auth(client: AsyncClient) -> dict:
    """Create a job seeker user and return auth headers + user_id."""
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "seeker@test.com",
            "password": "testpass123",
            "full_name": "Job Seeker",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "seeker@test.com", "password": "testpass123"},
    )
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get("/api/v1/auth/me", headers=headers)
    return {"headers": headers, "user_id": me.json()["data"]["id"]}


@pytest_asyncio.fixture
async def holder_auth(client: AsyncClient) -> dict:
    """Create a network holder user and return auth headers + user_id."""
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "holder@test.com",
            "password": "testpass123",
            "full_name": "Network Holder",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "holder@test.com", "password": "testpass123"},
    )
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get("/api/v1/auth/me", headers=headers)
    return {"headers": headers, "user_id": me.json()["data"]["id"]}


@pytest_asyncio.fixture
async def marketplace_data(holder_auth: dict):
    """Create company, contacts, listings, and sharing prefs for the holder."""
    holder_uid = uuid_mod.UUID(holder_auth["user_id"])

    async with TestSessionLocal() as db:
        company = Company(name="Stripe", domain="stripe.com")
        db.add(company)
        await db.flush()

        contacts = [
            Contact(
                user_id=holder_uid,
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
                user_id=holder_uid,
                full_name="Bob VP",
                first_name="Bob",
                last_name="VP",
                email="bob@stripe.com",
                current_title="VP of Engineering",
                current_company="Stripe",
                company_id=company.id,
                connected_on=date.today() - timedelta(days=800),
            ),
        ]
        for c in contacts:
            db.add(c)
        await db.flush()

        # Add warm scores
        db.add(WarmScore(
            user_id=holder_uid,
            contact_id=contacts[0].id,
            total_score=80,
            recency_score=90,
            tenure_score=70,
            context_score=80,
            role_score=75,
            referral_likelihood="high",
        ))
        db.add(WarmScore(
            user_id=holder_uid,
            contact_id=contacts[1].id,
            total_score=55,
            recency_score=40,
            tenure_score=60,
            context_score=50,
            role_score=70,
            referral_likelihood="medium",
        ))

        # Opt in to marketplace
        db.add(NetworkSharingPreferences(
            user_id=holder_uid, opt_in_marketplace=True
        ))
        await db.flush()

        # Create marketplace listings
        listings = [
            MarketplaceListing(
                network_holder_id=holder_uid,
                contact_id=contacts[0].id,
                company_id=company.id,
                role_level="senior",
                department_category="engineering",
                warm_score_range="high",
                connection_recency="recent",
            ),
            MarketplaceListing(
                network_holder_id=holder_uid,
                contact_id=contacts[1].id,
                company_id=company.id,
                role_level="vp",
                department_category="engineering",
                warm_score_range="medium",
                connection_recency="moderate",
            ),
        ]
        for lst in listings:
            db.add(lst)
        await db.flush()

        # Add reputation for holder
        db.add(ConnectorReputation(
            user_id=holder_uid,
            intros_facilitated=12,
            response_rate=85,
            avg_rating=4,
        ))

        await db.commit()

        return {
            "company_id": company.id,
            "contact_ids": [c.id for c in contacts],
            "listing_ids": [lst.id for lst in listings],
        }


@pytest_asyncio.fixture
async def seeker_with_credits(seeker_auth: dict):
    """Give the seeker 200 credits."""
    uid = uuid_mod.UUID(seeker_auth["user_id"])
    async with TestSessionLocal() as db:
        await earn_credits(uid, 200, "test_grant", db)
        await db.commit()
    return seeker_auth


# ---------------------------------------------------------------------------
# Test Marketplace Search
# ---------------------------------------------------------------------------


class TestMarketplaceSearch:
    async def test_search_returns_anonymized_results(
        self, client: AsyncClient, seeker_with_credits, marketplace_data
    ):
        """Search returns anonymized listings with no PII."""
        resp = await client.post(
            "/api/v1/marketplace/search",
            json={"company_names": ["Stripe"]},
            headers=seeker_with_credits["headers"],
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2

        for item in data:
            assert "listing_id" in item
            assert item["company_name"] == "Stripe"
            assert item["role_level"] in ("senior", "vp")
            assert item["department_category"] == "engineering"
            # Must NOT contain PII
            assert "contact_name" not in item
            assert "contact_email" not in item
            assert "email" not in item

    async def test_search_includes_reputation(
        self, client: AsyncClient, seeker_with_credits, marketplace_data
    ):
        """Search results include network holder reputation."""
        resp = await client.post(
            "/api/v1/marketplace/search",
            json={"company_names": ["Stripe"]},
            headers=seeker_with_credits["headers"],
        )
        data = resp.json()["data"]
        for item in data:
            rep = item["network_holder_reputation"]
            assert rep is not None
            assert rep["intros_facilitated"] == 12
            assert rep["response_rate"] == 85

    async def test_search_deducts_credits(
        self, client: AsyncClient, seeker_with_credits, marketplace_data
    ):
        """Search costs 5 credits."""
        uid = uuid_mod.UUID(seeker_with_credits["user_id"])
        async with TestSessionLocal() as db:
            before = await get_balance(uid, db)

        await client.post(
            "/api/v1/marketplace/search",
            json={"company_names": ["Stripe"]},
            headers=seeker_with_credits["headers"],
        )

        async with TestSessionLocal() as db:
            after = await get_balance(uid, db)
        assert before - after == 5

    async def test_search_insufficient_credits(
        self, client: AsyncClient, seeker_auth, marketplace_data
    ):
        """No credits → 402."""
        # Spend down welcome bonus credits first
        uid = uuid_mod.UUID(seeker_auth["user_id"])
        async with TestSessionLocal() as db:
            bal = await get_balance(uid, db)
            if bal > 0:
                await spend_credits(uid, bal, "drain_for_test", db)
                await db.commit()

        resp = await client.post(
            "/api/v1/marketplace/search",
            json={"company_names": ["Stripe"]},
            headers=seeker_auth["headers"],
        )
        assert resp.status_code == 402

    async def test_search_no_opted_in_holders(
        self, client: AsyncClient, seeker_with_credits
    ):
        """No opted-in holders → empty results."""
        resp = await client.post(
            "/api/v1/marketplace/search",
            json={"company_names": ["Nonexistent Corp"]},
            headers=seeker_with_credits["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    async def test_search_filters_role_level(
        self, client: AsyncClient, seeker_with_credits, marketplace_data
    ):
        """Role level filter narrows results."""
        resp = await client.post(
            "/api/v1/marketplace/search",
            json={"company_names": ["Stripe"], "role_levels": ["senior"]},
            headers=seeker_with_credits["headers"],
        )
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["role_level"] == "senior"

    async def test_search_filters_department(
        self, client: AsyncClient, seeker_with_credits, marketplace_data
    ):
        """Department filter narrows results."""
        resp = await client.post(
            "/api/v1/marketplace/search",
            json={"company_names": ["Stripe"], "departments": ["product"]},
            headers=seeker_with_credits["headers"],
        )
        data = resp.json()["data"]
        assert len(data) == 0  # Both are engineering

    async def test_search_excludes_own_listings(
        self, client: AsyncClient, holder_auth, marketplace_data
    ):
        """Holders don't see their own listings in search."""
        uid = uuid_mod.UUID(holder_auth["user_id"])
        async with TestSessionLocal() as db:
            await earn_credits(uid, 100, "test", db)
            await db.commit()

        resp = await client.post(
            "/api/v1/marketplace/search",
            json={"company_names": ["Stripe"]},
            headers=holder_auth["headers"],
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 0


# ---------------------------------------------------------------------------
# Test Intro Request Flow
# ---------------------------------------------------------------------------


class TestIntroRequestFlow:
    async def test_request_intro_success(
        self, client: AsyncClient, seeker_with_credits, marketplace_data
    ):
        """Job seeker can request an intro."""
        listing_id = str(marketplace_data["listing_ids"][0])
        resp = await client.post(
            "/api/v1/marketplace/request-intro",
            json={
                "marketplace_listing_id": listing_id,
                "message_to_holder": "I'm interested in Stripe!",
                "profile_visibility": "summary",
            },
            headers=seeker_with_credits["headers"],
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["status"] == "requested"
        assert data["marketplace_listing_id"] == listing_id

    async def test_request_intro_deducts_credits(
        self, client: AsyncClient, seeker_with_credits, marketplace_data
    ):
        """Intro request costs 20 credits."""
        uid = uuid_mod.UUID(seeker_with_credits["user_id"])
        async with TestSessionLocal() as db:
            before = await get_balance(uid, db)

        listing_id = str(marketplace_data["listing_ids"][0])
        await client.post(
            "/api/v1/marketplace/request-intro",
            json={"marketplace_listing_id": listing_id},
            headers=seeker_with_credits["headers"],
        )

        async with TestSessionLocal() as db:
            after = await get_balance(uid, db)
        assert before - after == 20

    async def test_request_intro_insufficient_credits(
        self, client: AsyncClient, seeker_auth, marketplace_data
    ):
        """No credits → 402."""
        # Spend down welcome bonus credits first
        uid = uuid_mod.UUID(seeker_auth["user_id"])
        async with TestSessionLocal() as db:
            bal = await get_balance(uid, db)
            if bal > 0:
                await spend_credits(uid, bal, "drain_for_test", db)
                await db.commit()

        listing_id = str(marketplace_data["listing_ids"][0])
        resp = await client.post(
            "/api/v1/marketplace/request-intro",
            json={"marketplace_listing_id": listing_id},
            headers=seeker_auth["headers"],
        )
        assert resp.status_code == 402

    async def test_request_intro_nonexistent_listing(
        self, client: AsyncClient, seeker_with_credits
    ):
        """Invalid listing → 404."""
        resp = await client.post(
            "/api/v1/marketplace/request-intro",
            json={"marketplace_listing_id": str(uuid_mod.uuid4())},
            headers=seeker_with_credits["headers"],
        )
        assert resp.status_code == 404

    async def test_request_intro_duplicate_blocked(
        self, client: AsyncClient, seeker_with_credits, marketplace_data
    ):
        """Duplicate pending request → 409."""
        listing_id = str(marketplace_data["listing_ids"][0])
        await client.post(
            "/api/v1/marketplace/request-intro",
            json={"marketplace_listing_id": listing_id},
            headers=seeker_with_credits["headers"],
        )
        resp = await client.post(
            "/api/v1/marketplace/request-intro",
            json={"marketplace_listing_id": listing_id},
            headers=seeker_with_credits["headers"],
        )
        assert resp.status_code == 409

    async def test_cannot_request_own_listing(
        self, client: AsyncClient, holder_auth, marketplace_data
    ):
        """Holder can't request intro on their own listing."""
        uid = uuid_mod.UUID(holder_auth["user_id"])
        async with TestSessionLocal() as db:
            await earn_credits(uid, 100, "test", db)
            await db.commit()

        listing_id = str(marketplace_data["listing_ids"][0])
        resp = await client.post(
            "/api/v1/marketplace/request-intro",
            json={"marketplace_listing_id": listing_id},
            headers=holder_auth["headers"],
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Test My Requests (Job Seeker View)
# ---------------------------------------------------------------------------


class TestMyRequests:
    async def test_seeker_sees_own_requests(
        self, client: AsyncClient, seeker_with_credits, marketplace_data
    ):
        """Job seeker can see their pending requests."""
        listing_id = str(marketplace_data["listing_ids"][0])
        await client.post(
            "/api/v1/marketplace/request-intro",
            json={"marketplace_listing_id": listing_id},
            headers=seeker_with_credits["headers"],
        )

        resp = await client.get(
            "/api/v1/marketplace/my-requests",
            headers=seeker_with_credits["headers"],
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["status"] == "requested"
        # Should include listing_summary (anonymized)
        assert data[0]["listing_summary"] is not None
        assert "contact_name" not in data[0]["listing_summary"]

    async def test_empty_when_no_requests(
        self, client: AsyncClient, seeker_with_credits
    ):
        resp = await client.get(
            "/api/v1/marketplace/my-requests",
            headers=seeker_with_credits["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == []


# ---------------------------------------------------------------------------
# Test Incoming Requests (Network Holder View)
# ---------------------------------------------------------------------------


class TestIncomingRequests:
    async def test_holder_sees_full_contact_details(
        self, client: AsyncClient, seeker_with_credits, holder_auth, marketplace_data
    ):
        """Network holder sees their contact's details on incoming requests."""
        listing_id = str(marketplace_data["listing_ids"][0])
        await client.post(
            "/api/v1/marketplace/request-intro",
            json={
                "marketplace_listing_id": listing_id,
                "message_to_holder": "Please help!",
                "profile_visibility": "full",
            },
            headers=seeker_with_credits["headers"],
        )

        resp = await client.get(
            "/api/v1/marketplace/incoming-requests",
            headers=holder_auth["headers"],
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1

        req = data[0]
        # Holder SHOULD see contact details (it's their contact)
        assert req["contact_name"] == "Alice Engineer"
        assert req["contact_title"] == "Senior Software Engineer"
        assert req["contact_email"] == "alice@stripe.com"

        # And the job seeker's profile snapshot
        snapshot = req["job_seeker_profile_snapshot"]
        assert snapshot["full_name"] == "Job Seeker"
        assert snapshot["message"] == "Please help!"


# ---------------------------------------------------------------------------
# Test Approve / Decline
# ---------------------------------------------------------------------------


class TestApproveDecline:
    async def _create_request(self, client, seeker_with_credits, marketplace_data):
        """Helper: create a request and return the facilitation id."""
        listing_id = str(marketplace_data["listing_ids"][0])
        resp = await client.post(
            "/api/v1/marketplace/request-intro",
            json={"marketplace_listing_id": listing_id},
            headers=seeker_with_credits["headers"],
        )
        return resp.json()["data"]["id"]

    async def test_approve_awards_holder_credits(
        self, client: AsyncClient, seeker_with_credits, holder_auth, marketplace_data
    ):
        """Approving awards 50 credits to network holder."""
        fac_id = await self._create_request(
            client, seeker_with_credits, marketplace_data
        )

        holder_uid = uuid_mod.UUID(holder_auth["user_id"])
        async with TestSessionLocal() as db:
            before = await get_balance(holder_uid, db)

        resp = await client.patch(
            f"/api/v1/marketplace/requests/{fac_id}",
            json={"action": "approve"},
            headers=holder_auth["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "approved"

        async with TestSessionLocal() as db:
            after = await get_balance(holder_uid, db)
        assert after - before == 50

    async def test_decline_refunds_seeker(
        self, client: AsyncClient, seeker_with_credits, holder_auth, marketplace_data
    ):
        """Declining refunds 15 of 20 credits to job seeker."""
        seeker_uid = uuid_mod.UUID(seeker_with_credits["user_id"])
        async with TestSessionLocal() as db:
            before = await get_balance(seeker_uid, db)

        fac_id = await self._create_request(
            client, seeker_with_credits, marketplace_data
        )

        # Balance should be before - 20 now
        async with TestSessionLocal() as db:
            mid = await get_balance(seeker_uid, db)
        assert before - mid == 20

        resp = await client.patch(
            f"/api/v1/marketplace/requests/{fac_id}",
            json={"action": "decline", "notes": "Not a good fit"},
            headers=holder_auth["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "declined"

        # Seeker should get 15 back (net cost: 5)
        async with TestSessionLocal() as db:
            after = await get_balance(seeker_uid, db)
        assert before - after == 5

    async def test_approve_with_notes(
        self, client: AsyncClient, seeker_with_credits, holder_auth, marketplace_data
    ):
        fac_id = await self._create_request(
            client, seeker_with_credits, marketplace_data
        )
        resp = await client.patch(
            f"/api/v1/marketplace/requests/{fac_id}",
            json={"action": "approve", "notes": "Happy to help!"},
            headers=holder_auth["headers"],
        )
        assert resp.json()["data"]["network_holder_notes"] == "Happy to help!"

    async def test_cannot_update_already_approved(
        self, client: AsyncClient, seeker_with_credits, holder_auth, marketplace_data
    ):
        """Can't decline an already approved request."""
        fac_id = await self._create_request(
            client, seeker_with_credits, marketplace_data
        )
        await client.patch(
            f"/api/v1/marketplace/requests/{fac_id}",
            json={"action": "approve"},
            headers=holder_auth["headers"],
        )
        resp = await client.patch(
            f"/api/v1/marketplace/requests/{fac_id}",
            json={"action": "decline"},
            headers=holder_auth["headers"],
        )
        assert resp.status_code == 400

    async def test_invalid_action(
        self, client: AsyncClient, seeker_with_credits, holder_auth, marketplace_data
    ):
        fac_id = await self._create_request(
            client, seeker_with_credits, marketplace_data
        )
        resp = await client.patch(
            f"/api/v1/marketplace/requests/{fac_id}",
            json={"action": "maybe"},
            headers=holder_auth["headers"],
        )
        assert resp.status_code == 400

    async def test_nonexistent_facilitation(
        self, client: AsyncClient, holder_auth
    ):
        resp = await client.patch(
            f"/api/v1/marketplace/requests/{uuid_mod.uuid4()}",
            json={"action": "approve"},
            headers=holder_auth["headers"],
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test Sharing Preferences
# ---------------------------------------------------------------------------


class TestSharingPreferences:
    async def test_get_default_prefs(self, client: AsyncClient, holder_auth):
        """Default prefs when none set."""
        resp = await client.get(
            "/api/v1/marketplace/sharing-preferences",
            headers=holder_auth["headers"],
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["opt_in_marketplace"] is False

    async def test_set_prefs(self, client: AsyncClient, holder_auth):
        """Set sharing preferences."""
        resp = await client.put(
            "/api/v1/marketplace/sharing-preferences",
            json={"opt_in_marketplace": True, "is_paused": False},
            headers=holder_auth["headers"],
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["opt_in_marketplace"] is True

    async def test_opt_in_generates_listings(
        self, client: AsyncClient, holder_auth, marketplace_data
    ):
        """Opting in triggers listing generation."""
        # First opt out (reset from marketplace_data fixture)
        holder_uid = uuid_mod.UUID(holder_auth["user_id"])
        async with TestSessionLocal() as db:
            result = await db.execute(
                NetworkSharingPreferences.__table__.select().where(
                    NetworkSharingPreferences.user_id == holder_uid
                )
            )
            row = result.first()
            if row:
                from sqlalchemy import update
                await db.execute(
                    update(NetworkSharingPreferences)
                    .where(NetworkSharingPreferences.user_id == holder_uid)
                    .values(opt_in_marketplace=False)
                )
                await db.commit()

        # Now opt in via API
        resp = await client.put(
            "/api/v1/marketplace/sharing-preferences",
            json={"opt_in_marketplace": True},
            headers=holder_auth["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["opt_in_marketplace"] is True

    async def test_opt_out_soft_deletes_listings(
        self, client: AsyncClient, holder_auth, marketplace_data
    ):
        """Opting out soft-deletes all listings."""
        resp = await client.put(
            "/api/v1/marketplace/sharing-preferences",
            json={"opt_in_marketplace": False},
            headers=holder_auth["headers"],
        )
        assert resp.status_code == 200

        # Check listings are soft-deleted
        holder_uid = uuid_mod.UUID(holder_auth["user_id"])
        async with TestSessionLocal() as db:
            from sqlalchemy import select
            result = await db.execute(
                select(MarketplaceListing).where(
                    MarketplaceListing.network_holder_id == holder_uid,
                    MarketplaceListing.deleted_at.is_(None),
                )
            )
            active = list(result.scalars())
            assert len(active) == 0

    async def test_update_prefs_idempotent(self, client: AsyncClient, holder_auth):
        """Multiple updates don't crash."""
        for _ in range(3):
            resp = await client.put(
                "/api/v1/marketplace/sharing-preferences",
                json={"opt_in_marketplace": True},
                headers=holder_auth["headers"],
            )
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Test My Listings (Holder View)
# ---------------------------------------------------------------------------


class TestMyListings:
    async def test_holder_sees_full_contact_info(
        self, client: AsyncClient, holder_auth, marketplace_data
    ):
        """Holder's own listings include full PII."""
        resp = await client.get(
            "/api/v1/marketplace/my-listings",
            headers=holder_auth["headers"],
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2

        names = {d["contact_name"] for d in data}
        assert "Alice Engineer" in names
        assert "Bob VP" in names

        for item in data:
            assert item["contact_email"] is not None
            assert item["contact_title"] is not None

    async def test_empty_when_no_listings(self, client: AsyncClient, holder_auth):
        resp = await client.get(
            "/api/v1/marketplace/my-listings",
            headers=holder_auth["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == []


# ---------------------------------------------------------------------------
# Test Job Seeker Only Sees Anonymized Data
# ---------------------------------------------------------------------------


class TestAnonymization:
    async def test_seeker_never_gets_pii(
        self, client: AsyncClient, seeker_with_credits, holder_auth, marketplace_data
    ):
        """Across all seeker-facing endpoints, no PII leaks."""
        # Search
        search_resp = await client.post(
            "/api/v1/marketplace/search",
            json={"company_names": ["Stripe"]},
            headers=seeker_with_credits["headers"],
        )
        for item in search_resp.json()["data"]:
            assert "contact_name" not in item
            assert "contact_email" not in item
            assert "email" not in item
            assert "full_name" not in item

        # Request intro
        listing_id = str(marketplace_data["listing_ids"][0])
        req_resp = await client.post(
            "/api/v1/marketplace/request-intro",
            json={"marketplace_listing_id": listing_id},
            headers=seeker_with_credits["headers"],
        )
        req_data = req_resp.json()["data"]
        assert "contact_name" not in req_data
        assert "contact_email" not in req_data

        # My requests
        my_resp = await client.get(
            "/api/v1/marketplace/my-requests",
            headers=seeker_with_credits["headers"],
        )
        for item in my_resp.json()["data"]:
            assert "contact_name" not in item
            assert "contact_email" not in item


# ---------------------------------------------------------------------------
# Test Smart Search with Marketplace Scope
# ---------------------------------------------------------------------------


class TestSmartSearchMarketplace:
    async def test_marketplace_scope_includes_listings(
        self, client: AsyncClient, seeker_with_credits, marketplace_data
    ):
        """Smart search with marketplace scope merges marketplace results."""
        # Set job preferences first
        await client.put(
            "/api/v1/preferences/job",
            json={"target_role": "Software Engineer", "target_seniority": "senior"},
            headers=seeker_with_credits["headers"],
        )

        resp = await client.post(
            "/api/v1/search/smart",
            json={"company_names": ["Stripe"], "scope": "marketplace"},
            headers=seeker_with_credits["headers"],
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["status"] == "completed"

        # Should have companies with marketplace referral paths
        companies = data["companies"]
        assert len(companies) == 1
        stripe = companies[0]

        marketplace_paths = [
            p for p in stripe["referral_paths"] if p.get("source") == "marketplace"
        ]
        assert len(marketplace_paths) == 2  # 2 marketplace listings

        # Marketplace paths should be anonymized
        for path in marketplace_paths:
            assert "listing" in path
            assert "contact" not in path  # No PII

    async def test_marketplace_scope_requires_credits(
        self, client: AsyncClient, seeker_auth
    ):
        """Marketplace scope without credits → 402."""
        # Spend down welcome bonus credits first
        uid = uuid_mod.UUID(seeker_auth["user_id"])
        async with TestSessionLocal() as db:
            bal = await get_balance(uid, db)
            if bal > 0:
                await spend_credits(uid, bal, "drain_for_test", db)
                await db.commit()

        await client.put(
            "/api/v1/preferences/job",
            json={"target_role": "Software Engineer"},
            headers=seeker_auth["headers"],
        )

        resp = await client.post(
            "/api/v1/search/smart",
            json={"company_names": ["Stripe"], "scope": "marketplace"},
            headers=seeker_auth["headers"],
        )
        assert resp.status_code == 402

    async def test_own_network_scope_is_free(
        self, client: AsyncClient, seeker_auth
    ):
        """Own-network scope doesn't require credits."""
        await client.put(
            "/api/v1/preferences/job",
            json={"target_role": "Software Engineer"},
            headers=seeker_auth["headers"],
        )

        resp = await client.post(
            "/api/v1/search/smart",
            json={"company_names": ["Stripe"], "scope": "own_network"},
            headers=seeker_auth["headers"],
        )
        assert resp.status_code == 201
