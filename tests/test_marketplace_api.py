"""Tests for marketplace API — search, intro facilitation, sharing prefs, credits."""

import uuid as uuid_mod
from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.config import settings
from app.models.audit import AuditLog
from app.models.company import Company
from app.models.contact import Contact
from app.models.job import UserJobPreferences
from app.models.marketplace import (
    ConnectorReputation,
    MarketplaceListing,
    NetworkSharingPreferences,
)
from app.models.match_result import WarmScore
from app.models.user import ConnectorProfile
from app.services.credits import earn_credits, get_balance, spend_credits
from tests.conftest import TestSessionLocal, create_test_user_in_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def seeker_auth(client: AsyncClient) -> dict:
    """Create a job seeker user and return auth headers + user_id."""
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="seeker@test.com", full_name="Job Seeker", email_verified=True
        )
    return {"headers": headers, "user_id": str(user.id)}


@pytest_asyncio.fixture
async def holder_auth(client: AsyncClient) -> dict:
    """Create a network holder user and return auth headers + user_id."""
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="holder@test.com", full_name="Network Holder", email_verified=True
        )
    return {"headers": headers, "user_id": str(user.id)}


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
        db.add(
            WarmScore(
                user_id=holder_uid,
                contact_id=contacts[0].id,
                total_score=80,
                recency_score=90,
                tenu[RESEND_KEY_REDACTED]=70,
                context_score=80,
                role_score=75,
                referral_likelihood="high",
            )
        )
        db.add(
            WarmScore(
                user_id=holder_uid,
                contact_id=contacts[1].id,
                total_score=55,
                recency_score=40,
                tenu[RESEND_KEY_REDACTED]=60,
                context_score=50,
                role_score=70,
                referral_likelihood="medium",
            )
        )

        # Opt in to marketplace
        db.add(NetworkSharingPreferences(user_id=holder_uid, opt_in_marketplace=True))
        await db.flush()

        # Create marketplace listings
        listings = [
            MarketplaceListing(
                network_holder_id=holder_uid,
                contact_id=contacts[0].id,
                company_id=company.id,
                role_level="senior",
                department_category="engineering",
                warm_sco[RESEND_KEY_REDACTED]="high",
                connection_recency="recent",
            ),
            MarketplaceListing(
                network_holder_id=holder_uid,
                contact_id=contacts[1].id,
                company_id=company.id,
                role_level="vp",
                department_category="engineering",
                warm_sco[RESEND_KEY_REDACTED]="medium",
                connection_recency="moderate",
            ),
        ]
        for lst in listings:
            db.add(lst)
        await db.flush()

        # Add reputation for holder
        db.add(
            ConnectorReputation(
                user_id=holder_uid,
                intros_facilitated=12,
                response_rate=85,
                avg_rating=4,
            )
        )

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
    @pytest.mark.smoke
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

    @pytest.mark.smoke
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
        assert "detail" in resp.json()

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

    @pytest.mark.smoke
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

    @pytest.mark.smoke
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
        assert "detail" in resp.json()

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

    @pytest.mark.smoke
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

    async def test_request_intro_rate_limited_by_velocity_cap(
        self, client: AsyncClient, seeker_with_credits, marketplace_data, monkeypatch
    ):
        """Daily intro-request velocity cap blocks excess requests."""

        async def _noop_notify(*args, **kwargs):
            return None

        monkeypatch.setattr(
            "app.services.email_engagement.send_intro_request_notification",
            _noop_notify,
        )
        monkeypatch.setattr(
            "app.services.email_engagement.send_intro_relay_email",
            _noop_notify,
        )
        monkeypatch.setattr(
            "app.services.email_engagement.send_intro_relay_email",
            _noop_notify,
        )

        old_limit = settings.RATE_LIMIT_INTRO_REQUESTS_PER_DAY
        try:
            settings.RATE_LIMIT_INTRO_REQUESTS_PER_DAY = 1
            listing_a = str(marketplace_data["listing_ids"][0])
            listing_b = str(marketplace_data["listing_ids"][1])

            first = await client.post(
                "/api/v1/marketplace/request-intro",
                json={"marketplace_listing_id": listing_a},
                headers=seeker_with_credits["headers"],
            )
            assert first.status_code == 201

            second = await client.post(
                "/api/v1/marketplace/request-intro",
                json={"marketplace_listing_id": listing_b},
                headers=seeker_with_credits["headers"],
            )
            assert second.status_code == 429
            assert "intro request limit" in second.json()["error"]["message"].lower()
            async with TestSessionLocal() as db:
                log = (
                    await db.execute(
                        select(AuditLog)
                        .where(AuditLog.action == "velocity_limit_hit")
                        .order_by(AuditLog.created_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                assert log is not None
                assert log.metadata_["action"] == "intro_request"
                assert log.metadata_["max_per_day"] == 1
        finally:
            settings.RATE_LIMIT_INTRO_REQUESTS_PER_DAY = old_limit

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
        assert "detail" in resp.json()

    async def test_request_intro_enriched_snapshot(
        self, client: AsyncClient, seeker_with_credits, marketplace_data
    ):
        """Intro snapshot includes ConnectorProfile and UserJobPreferences fields."""
        seeker_uid = uuid_mod.UUID(seeker_with_credits["user_id"])

        # Create ConnectorProfile and UserJobPreferences for the seeker
        async with TestSessionLocal() as db:
            db.add(
                ConnectorProfile(
                    user_id=seeker_uid,
                    headline="Senior Backend Engineer | Python & Go",
                    current_title="Senior Software Engineer",
                    current_company="Acme Inc",
                    bio_summary="Experienced backend engineer",
                    work_history=[
                        {
                            "company": "Acme Inc",
                            "title": "Senior Software Engineer",
                            "start": "2022-01",
                            "end": None,
                        },
                        {
                            "company": "StartupCo",
                            "title": "Software Engineer",
                            "start": "2019-06",
                            "end": "2021-12",
                        },
                    ],
                    github_url="https://github.com/seekerdev",
                )
            )
            db.add(
                UserJobPreferences(
                    user_id=seeker_uid,
                    target_role="Staff Engineer",
                    target_seniority="staff",
                    target_industries=[],
                    target_locations=[],
                )
            )
            await db.commit()

        listing_id = str(marketplace_data["listing_ids"][0])
        resp = await client.post(
            "/api/v1/marketplace/request-intro",
            json={
                "marketplace_listing_id": listing_id,
                "profile_visibility": "full",
                "request_type": "specific_role",
                "job_title": "Staff Engineer",
            },
            headers=seeker_with_credits["headers"],
        )
        assert resp.status_code == 201
        snapshot = resp.json()["data"]["job_seeker_profile_snapshot"]

        # Profile fields
        assert snapshot["headline"] == "Senior Backend Engineer | Python & Go"
        assert snapshot["current_title"] == "Senior Software Engineer"
        assert snapshot["current_company"] == "Acme Inc"
        assert snapshot["bio_summary"] == "Experienced backend engineer"
        assert snapshot["github_url"] == "https://github.com/seekerdev"

        # Job preferences
        assert snapshot["target_role"] == "Staff Engineer"
        assert snapshot["target_seniority"] == "staff"

        # Request context
        assert snapshot["request_type"] == "specific_role"
        assert snapshot["job_title"] == "Staff Engineer"

        # Work history summary
        assert isinstance(snapshot["work_history_summary"], list)
        assert len(snapshot["work_history_summary"]) == 2

    async def test_request_intro_general_networking_type(
        self, client: AsyncClient, seeker_with_credits, marketplace_data
    ):
        """Intro with general_networking type includes exploration_context in snapshot."""
        listing_id = str(marketplace_data["listing_ids"][0])
        resp = await client.post(
            "/api/v1/marketplace/request-intro",
            json={
                "marketplace_listing_id": listing_id,
                "profile_visibility": "summary",
                "request_type": "general_networking",
                "exploration_context": "Interested in learning about eng culture",
            },
            headers=seeker_with_credits["headers"],
        )
        assert resp.status_code == 201
        snapshot = resp.json()["data"]["job_seeker_profile_snapshot"]

        assert snapshot["request_type"] == "general_networking"
        assert (
            snapshot["exploration_context"]
            == "Interested in learning about eng culture"
        )
        # job_title should not be present when not provided
        assert snapshot.get("job_title") is None

    async def test_request_intro_generates_candidate_blurb(
        self, client: AsyncClient, seeker_with_credits, marketplace_data
    ):
        """Intro request generates and stores AI candidate blurb in snapshot."""
        seeker_uid = uuid_mod.UUID(seeker_with_credits["user_id"])

        # Create ConnectorProfile and UserJobPreferences for the seeker
        async with TestSessionLocal() as db:
            db.add(
                ConnectorProfile(
                    user_id=seeker_uid,
                    headline="Senior Backend Engineer | Python & Go",
                    current_title="Senior Software Engineer",
                    current_company="Acme Inc",
                    bio_summary="Experienced backend engineer",
                    work_history=[
                        {
                            "company": "Acme Inc",
                            "title": "Senior Software Engineer",
                            "start": "2022-01",
                            "end": None,
                        },
                    ],
                    github_url="https://github.com/seekerdev",
                )
            )
            db.add(
                UserJobPreferences(
                    user_id=seeker_uid,
                    target_role="Staff Engineer",
                    target_seniority="staff",
                    target_industries=[],
                    target_locations=[],
                )
            )
            await db.commit()

        listing_id = str(marketplace_data["listing_ids"][0])
        resp = await client.post(
            "/api/v1/marketplace/request-intro",
            json={
                "marketplace_listing_id": listing_id,
                "profile_visibility": "summary",
                "request_type": "specific_role",
                "job_title": "Staff Engineer",
            },
            headers=seeker_with_credits["headers"],
        )
        assert resp.status_code == 201
        snapshot = resp.json()["data"]["job_seeker_profile_snapshot"]
        assert "candidate_blurb" in snapshot
        assert len(snapshot["candidate_blurb"]) > 20


# ---------------------------------------------------------------------------
# Duplicate Detection (contact already in seeker's vault)
# ---------------------------------------------------------------------------


class TestDuplicateDetection:
    @pytest.mark.smoke
    async def test_intro_blocked_when_contact_in_seeker_vault(
        self,
        client: AsyncClient,
        seeker_with_credits,
        holder_auth,
        marketplace_data,
    ):
        """If the listed contact is already in the seeker's vault, return 409."""
        seeker_uid = uuid_mod.UUID(seeker_with_credits["user_id"])

        # Add "Alice Engineer" to the seeker's own contacts (same email)
        async with TestSessionLocal() as db:
            db.add(
                Contact(
                    user_id=seeker_uid,
                    full_name="Alice Engineer",
                    first_name="Alice",
                    last_name="Engineer",
                    email="alice@stripe.com",
                    current_company="Stripe",
                    current_title="Senior Software Engineer",
                    connected_on=date.today(),
                )
            )
            await db.commit()

        # Get balance before
        bal_resp = await client.get(
            "/api/v1/credits/balance",
            headers=seeker_with_credits["headers"],
        )
        balance_before = bal_resp.json()["data"]["balance"]

        # Request intro for Alice's listing → should be blocked
        listing_id = str(marketplace_data["listing_ids"][0])
        resp = await client.post(
            "/api/v1/marketplace/request-intro",
            json={"marketplace_listing_id": listing_id},
            headers=seeker_with_credits["headers"],
        )
        assert resp.status_code == 409
        assert "already in your network" in resp.json()["detail"]

        # Credits should NOT be deducted
        bal_resp2 = await client.get(
            "/api/v1/credits/balance",
            headers=seeker_with_credits["headers"],
        )
        assert bal_resp2.json()["data"]["balance"] == balance_before

    async def test_intro_succeeds_when_contact_not_in_vault(
        self,
        client: AsyncClient,
        seeker_with_credits,
        marketplace_data,
    ):
        """If the contact is NOT in the seeker's vault, intro proceeds normally."""
        # Get balance before
        bal_resp = await client.get(
            "/api/v1/credits/balance",
            headers=seeker_with_credits["headers"],
        )
        balance_before = bal_resp.json()["data"]["balance"]

        listing_id = str(marketplace_data["listing_ids"][0])
        resp = await client.post(
            "/api/v1/marketplace/request-intro",
            json={"marketplace_listing_id": listing_id},
            headers=seeker_with_credits["headers"],
        )
        assert resp.status_code == 201

        # Credits should be deducted (20 for intro)
        bal_resp2 = await client.get(
            "/api/v1/credits/balance",
            headers=seeker_with_credits["headers"],
        )
        assert bal_resp2.json()["data"]["balance"] == balance_before - 20

    async def test_name_company_fallback_match(
        self,
        client: AsyncClient,
        seeker_with_credits,
        marketplace_data,
    ):
        """Duplicate detected via name+company hash even without email match."""
        seeker_uid = uuid_mod.UUID(seeker_with_credits["user_id"])

        # Add contact with same name+company but different email
        async with TestSessionLocal() as db:
            db.add(
                Contact(
                    user_id=seeker_uid,
                    full_name="Alice Engineer",
                    first_name="Alice",
                    last_name="Engineer",
                    email="alice-personal@gmail.com",
                    current_company="Stripe",
                    current_title="Engineer",
                    connected_on=date.today(),
                )
            )
            await db.commit()

        listing_id = str(marketplace_data["listing_ids"][0])
        resp = await client.post(
            "/api/v1/marketplace/request-intro",
            json={"marketplace_listing_id": listing_id},
            headers=seeker_with_credits["headers"],
        )
        assert resp.status_code == 409
        assert "already in your network" in resp.json()["detail"]


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
    @pytest.mark.smoke
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

    async def test_incoming_requests_includes_relationship_context(
        self, client: AsyncClient, seeker_with_credits, holder_auth, marketplace_data
    ):
        """NH review screen includes relationship_type, would_refer, and how_you_know."""
        # Set relationship context on the first contact
        async with TestSessionLocal() as db:
            from sqlalchemy import select as sa_select

            result = await db.execute(
                sa_select(Contact).where(
                    Contact.id == marketplace_data["contact_ids"][0]
                )
            )
            contact = result.scalar_one()
            contact.relationship_type = "former_colleague"
            contact.would_refer = "probably"
            contact.how_you_know = "Worked together at Stripe"
            await db.commit()

        # Create an intro request from the seeker
        listing_id = str(marketplace_data["listing_ids"][0])
        await client.post(
            "/api/v1/marketplace/request-intro",
            json={
                "marketplace_listing_id": listing_id,
                "message_to_holder": "Interested in Stripe!",
            },
            headers=seeker_with_credits["headers"],
        )

        # Fetch incoming requests as the NH
        resp = await client.get(
            "/api/v1/marketplace/incoming-requests",
            headers=holder_auth["headers"],
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1

        req = data[0]
        assert req["relationship_type"] == "former_colleague"
        assert req["would_refer"] == "probably"
        assert req["how_you_know"] == "Worked together at Stripe"


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

    @pytest.mark.smoke
    async def test_approve_defers_credits_for_email_relay(
        self, client: AsyncClient, seeker_with_credits, holder_auth, marketplace_data
    ):
        """Approving with contact email uses relay path; credits NOT awarded yet."""
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
        data = resp.json()["data"]
        assert data["status"] == "approved"
        assert data["delivery_method"] == "email_relay"
        # delivery_status is "failed" in tests because RESEND_API_KEY is empty
        assert data["delivery_status"] in ("sent", "failed")
        assert data["credits_awarded_at"] is None

        # Credits should NOT have been awarded
        async with TestSessionLocal() as db:
            after = await get_balance(holder_uid, db)
        assert after == before

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
        approve_resp = await client.patch(
            f"/api/v1/marketplace/requests/{fac_id}",
            json={"action": "approve"},
            headers=holder_auth["headers"],
        )
        assert approve_resp.status_code == 200
        resp = await client.patch(
            f"/api/v1/marketplace/requests/{fac_id}",
            json={"action": "decline"},
            headers=holder_auth["headers"],
        )
        assert resp.status_code == 400
        assert "detail" in resp.json()

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

    async def test_nonexistent_facilitation(self, client: AsyncClient, holder_auth):
        resp = await client.patch(
            f"/api/v1/marketplace/requests/{uuid_mod.uuid4()}",
            json={"action": "approve"},
            headers=holder_auth["headers"],
        )
        assert resp.status_code == 404

    async def test_approve_rate_limited_by_velocity_cap(
        self,
        client: AsyncClient,
        seeker_with_credits,
        holder_auth,
        marketplace_data,
        monkeypatch,
    ):
        """Daily intro-approval velocity cap blocks excess approvals."""

        async def _noop_notify(*args, **kwargs):
            return None

        monkeypatch.setattr(
            "app.services.email_engagement.send_intro_request_notification",
            _noop_notify,
        )

        old_limit = settings.RATE_LIMIT_INTRO_APPROVALS_PER_DAY
        try:
            settings.RATE_LIMIT_INTRO_APPROVALS_PER_DAY = 1

            listing_a = str(marketplace_data["listing_ids"][0])
            listing_b = str(marketplace_data["listing_ids"][1])

            first_req = await client.post(
                "/api/v1/marketplace/request-intro",
                json={"marketplace_listing_id": listing_a},
                headers=seeker_with_credits["headers"],
            )
            second_req = await client.post(
                "/api/v1/marketplace/request-intro",
                json={"marketplace_listing_id": listing_b},
                headers=seeker_with_credits["headers"],
            )
            fac1 = first_req.json()["data"]["id"]
            fac2 = second_req.json()["data"]["id"]

            first_approve = await client.patch(
                f"/api/v1/marketplace/requests/{fac1}",
                json={"action": "approve"},
                headers=holder_auth["headers"],
            )
            assert first_approve.status_code == 200

            second_approve = await client.patch(
                f"/api/v1/marketplace/requests/{fac2}",
                json={"action": "approve"},
                headers=holder_auth["headers"],
            )
            assert second_approve.status_code == 429
            assert (
                "intro approval limit"
                in second_approve.json()["error"]["message"].lower()
            )
            async with TestSessionLocal() as db:
                log = (
                    await db.execute(
                        select(AuditLog)
                        .where(AuditLog.action == "velocity_limit_hit")
                        .order_by(AuditLog.created_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                assert log is not None
                assert log.metadata_["action"] == "intro_approve"
                assert log.metadata_["max_per_day"] == 1
        finally:
            settings.RATE_LIMIT_INTRO_APPROVALS_PER_DAY = old_limit


# ---------------------------------------------------------------------------
# Test LinkedIn Fallback (contact without email)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def marketplace_no_email(holder_auth: dict):
    """Create marketplace data where the contact has no email (LinkedIn fallback)."""
    holder_uid = uuid_mod.UUID(holder_auth["user_id"])

    async with TestSessionLocal() as db:
        company = Company(name="Acme Corp", domain="acme.com")
        db.add(company)
        await db.flush()

        contact = Contact(
            user_id=holder_uid,
            full_name="Diana NoEmail",
            first_name="Diana",
            last_name="NoEmail",
            email=None,
            linkedin_url="https://linkedin.com/in/diana-noemail",
            current_title="Staff Engineer",
            current_company="Acme Corp",
            company_id=company.id,
            connected_on=date.today() - timedelta(days=90),
        )
        db.add(contact)
        await db.flush()

        db.add(
            WarmScore(
                user_id=holder_uid,
                contact_id=contact.id,
                total_score=75,
                recency_score=80,
                tenu[RESEND_KEY_REDACTED]=70,
                context_score=75,
                role_score=70,
                referral_likelihood="high",
            )
        )

        db.add(NetworkSharingPreferences(user_id=holder_uid, opt_in_marketplace=True))
        await db.flush()

        listing = MarketplaceListing(
            network_holder_id=holder_uid,
            contact_id=contact.id,
            company_id=company.id,
            role_level="lead",
            department_category="engineering",
            warm_sco[RESEND_KEY_REDACTED]="high",
            connection_recency="recent",
        )
        db.add(listing)
        await db.flush()

        db.add(
            ConnectorReputation(
                user_id=holder_uid,
                intros_facilitated=5,
                response_rate=90,
                avg_rating=5,
            )
        )
        await db.commit()

        return {
            "company_id": company.id,
            "contact_id": contact.id,
            "listing_id": listing.id,
        }


class TestLinkedInFallback:
    async def _create_request(self, client, seeker_with_credits, marketplace_no_email):
        listing_id = str(marketplace_no_email["listing_id"])
        resp = await client.post(
            "/api/v1/marketplace/request-intro",
            json={"marketplace_listing_id": listing_id},
            headers=seeker_with_credits["headers"],
        )
        return resp.json()["data"]["id"]

    async def test_approve_returns_linkedin_url_and_drafted_message(
        self,
        client: AsyncClient,
        seeker_with_credits,
        holder_auth,
        marketplace_no_email,
    ):
        """When contact has no email, approve returns linkedin_url and drafted_message."""
        fac_id = await self._create_request(
            client, seeker_with_credits, marketplace_no_email
        )

        resp = await client.patch(
            f"/api/v1/marketplace/requests/{fac_id}",
            json={"action": "approve"},
            headers=holder_auth["headers"],
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "approved"
        assert data["delivery_method"] is None
        assert data["linkedin_url"] == "https://linkedin.com/in/diana-noemail"
        assert "Diana" in data["drafted_message"]
        assert data["credits_awarded_at"] is None

    async def test_approve_no_email_no_credits_awarded(
        self,
        client: AsyncClient,
        seeker_with_credits,
        holder_auth,
        marketplace_no_email,
    ):
        """LinkedIn fallback path does not award credits immediately."""
        fac_id = await self._create_request(
            client, seeker_with_credits, marketplace_no_email
        )

        holder_uid = uuid_mod.UUID(holder_auth["user_id"])
        async with TestSessionLocal() as db:
            before = await get_balance(holder_uid, db)

        await client.patch(
            f"/api/v1/marketplace/requests/{fac_id}",
            json={"action": "approve"},
            headers=holder_auth["headers"],
        )

        async with TestSessionLocal() as db:
            after = await get_balance(holder_uid, db)
        assert after == before

    async def test_approve_includes_candidate_blurb_in_drafted_message(
        self,
        client: AsyncClient,
        seeker_with_credits,
        holder_auth,
        marketplace_no_email,
    ):
        """LinkedIn drafted message includes candidate_blurb from snapshot."""
        seeker_uid = uuid_mod.UUID(seeker_with_credits["user_id"])

        # Create ConnectorProfile so blurb generation has material to work with
        async with TestSessionLocal() as db:
            db.add(
                ConnectorProfile(
                    user_id=seeker_uid,
                    headline="Senior Backend Engineer | Python & Go",
                    current_title="Senior Software Engineer",
                    current_company="Acme Inc",
                    bio_summary="Experienced backend engineer with 5 years in distributed systems",
                )
            )
            db.add(
                UserJobPreferences(
                    user_id=seeker_uid,
                    target_role="Staff Engineer",
                    target_seniority="staff",
                    target_industries=[],
                    target_locations=[],
                )
            )
            await db.commit()

        # Request intro (generates candidate_blurb in snapshot)
        listing_id = str(marketplace_no_email["listing_id"])
        req_resp = await client.post(
            "/api/v1/marketplace/request-intro",
            json={
                "marketplace_listing_id": listing_id,
                "profile_visibility": "summary",
                "request_type": "specific_role",
                "job_title": "Staff Engineer",
            },
            headers=seeker_with_credits["headers"],
        )
        assert req_resp.status_code == 201
        fac_id = req_resp.json()["data"]["id"]

        # Verify blurb was generated in snapshot
        snapshot = req_resp.json()["data"]["job_seeker_profile_snapshot"]
        assert "candidate_blurb" in snapshot
        blurb_text = snapshot["candidate_blurb"]
        assert len(blurb_text) > 20

        # NH approves — LinkedIn fallback path
        resp = await client.patch(
            f"/api/v1/marketplace/requests/{fac_id}",
            json={"action": "approve"},
            headers=holder_auth["headers"],
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["delivery_method"] is None  # LinkedIn fallback
        assert "drafted_message" in data

        # Drafted message should contain the blurb text
        assert blurb_text in data["drafted_message"]


# ---------------------------------------------------------------------------
# Test Confirm Manual Send
# ---------------------------------------------------------------------------


class TestConfirmManualSend:
    async def _create_and_approve(
        self, client, seeker_with_credits, holder_auth, marketplace_no_email
    ):
        """Helper: create request and approve it (LinkedIn fallback path)."""
        listing_id = str(marketplace_no_email["listing_id"])
        req_resp = await client.post(
            "/api/v1/marketplace/request-intro",
            json={"marketplace_listing_id": listing_id},
            headers=seeker_with_credits["headers"],
        )
        fac_id = req_resp.json()["data"]["id"]

        await client.patch(
            f"/api/v1/marketplace/requests/{fac_id}",
            json={"action": "approve"},
            headers=holder_auth["headers"],
        )
        return fac_id

    @pytest.mark.smoke
    async def test_confirm_sent_awards_credits_and_sets_delivery(
        self,
        client: AsyncClient,
        seeker_with_credits,
        holder_auth,
        marketplace_no_email,
    ):
        """Confirming manual send awards 50 credits and sets delivery fields."""
        fac_id = await self._create_and_approve(
            client, seeker_with_credits, holder_auth, marketplace_no_email
        )

        holder_uid = uuid_mod.UUID(holder_auth["user_id"])
        async with TestSessionLocal() as db:
            before = await get_balance(holder_uid, db)

        resp = await client.post(
            f"/api/v1/marketplace/requests/{fac_id}/confirm-sent",
            headers=holder_auth["headers"],
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "confirmed"
        assert data["credits_awarded"] == 50

        async with TestSessionLocal() as db:
            after = await get_balance(holder_uid, db)
        assert after - before == 50

    async def test_confirm_sent_deferred_when_manual_awards_disabled(
        self,
        client: AsyncClient,
        seeker_with_credits,
        holder_auth,
        marketplace_no_email,
    ):
        """Kill switch: manual confirm records delivery but does not award credits."""
        fac_id = await self._create_and_approve(
            client, seeker_with_credits, holder_auth, marketplace_no_email
        )

        holder_uid = uuid_mod.UUID(holder_auth["user_id"])
        old_flag = settings.MANUAL_INTRO_CREDIT_AWARD_ENABLED
        try:
            settings.MANUAL_INTRO_CREDIT_AWARD_ENABLED = False
            async with TestSessionLocal() as db:
                before = await get_balance(holder_uid, db)

            resp = await client.post(
                f"/api/v1/marketplace/requests/{fac_id}/confirm-sent",
                headers=holder_auth["headers"],
            )
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["status"] == "confirmed"
            assert data["credits_awarded"] == 0
            assert data["credits_deferred"] is True

            async with TestSessionLocal() as db:
                after = await get_balance(holder_uid, db)
            assert after == before
        finally:
            settings.MANUAL_INTRO_CREDIT_AWARD_ENABLED = old_flag

    async def test_confirm_sent_404_for_wrong_user(
        self,
        client: AsyncClient,
        seeker_with_credits,
        holder_auth,
        marketplace_no_email,
    ):
        """Other users cannot confirm-sent on someone else's facilitation."""
        fac_id = await self._create_and_approve(
            client, seeker_with_credits, holder_auth, marketplace_no_email
        )

        # Seeker tries to confirm — should get 404
        resp = await client.post(
            f"/api/v1/marketplace/requests/{fac_id}/confirm-sent",
            headers=seeker_with_credits["headers"],
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    async def test_confirm_sent_400_for_non_approved(
        self,
        client: AsyncClient,
        seeker_with_credits,
        holder_auth,
        marketplace_no_email,
    ):
        """Cannot confirm-sent on a request that is still in 'requested' state."""
        listing_id = str(marketplace_no_email["listing_id"])
        req_resp = await client.post(
            "/api/v1/marketplace/request-intro",
            json={"marketplace_listing_id": listing_id},
            headers=seeker_with_credits["headers"],
        )
        fac_id = req_resp.json()["data"]["id"]

        # Try to confirm without approving first
        resp = await client.post(
            f"/api/v1/marketplace/requests/{fac_id}/confirm-sent",
            headers=holder_auth["headers"],
        )
        assert resp.status_code == 400
        assert "not in approved state" in resp.json()["detail"]

    async def test_confirm_sent_400_for_already_awarded(
        self,
        client: AsyncClient,
        seeker_with_credits,
        holder_auth,
        marketplace_no_email,
    ):
        """Cannot double-confirm — second call returns 400."""
        fac_id = await self._create_and_approve(
            client, seeker_with_credits, holder_auth, marketplace_no_email
        )

        # First confirm — should succeed
        resp1 = await client.post(
            f"/api/v1/marketplace/requests/{fac_id}/confirm-sent",
            headers=holder_auth["headers"],
        )
        assert resp1.status_code == 200

        # Second confirm — should fail
        resp2 = await client.post(
            f"/api/v1/marketplace/requests/{fac_id}/confirm-sent",
            headers=holder_auth["headers"],
        )
        assert resp2.status_code == 400
        assert (
            "already awarded" in resp2.json()["detail"].lower()
            or "already confirmed" in resp2.json()["detail"].lower()
        )

    async def test_confirm_sent_404_nonexistent(self, client: AsyncClient, holder_auth):
        """Nonexistent facilitation returns 404."""
        resp = await client.post(
            f"/api/v1/marketplace/requests/{uuid_mod.uuid4()}/confirm-sent",
            headers=holder_auth["headers"],
        )
        assert resp.status_code == 404

    async def test_confirm_sent_rate_limited_by_velocity_cap(
        self,
        client: AsyncClient,
        seeker_with_credits,
        holder_auth,
        marketplace_no_email,
        monkeypatch,
    ):
        """Daily manual-confirm velocity cap blocks excess confirms."""

        async def _noop_notify(*args, **kwargs):
            return None

        monkeypatch.setattr(
            "app.services.email_engagement.send_intro_request_notification",
            _noop_notify,
        )

        old_limit = settings.RATE_LIMIT_MANUAL_INTRO_CONFIRMS_PER_DAY
        try:
            settings.RATE_LIMIT_MANUAL_INTRO_CONFIRMS_PER_DAY = 1

            fac1 = await self._create_and_approve(
                client, seeker_with_credits, holder_auth, marketplace_no_email
            )
            fac2 = await self._create_and_approve(
                client, seeker_with_credits, holder_auth, marketplace_no_email
            )

            first = await client.post(
                f"/api/v1/marketplace/requests/{fac1}/confirm-sent",
                headers=holder_auth["headers"],
            )
            assert first.status_code == 200

            second = await client.post(
                f"/api/v1/marketplace/requests/{fac2}/confirm-sent",
                headers=holder_auth["headers"],
            )
            assert second.status_code == 429
            assert (
                "manual intro confirmation limit"
                in second.json()["error"]["message"].lower()
            )
            async with TestSessionLocal() as db:
                log = (
                    await db.execute(
                        select(AuditLog)
                        .where(AuditLog.action == "velocity_limit_hit")
                        .order_by(AuditLog.created_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                assert log is not None
                assert log.metadata_["action"] == "manual_intro_confirm"
                assert log.metadata_["max_per_day"] == 1
        finally:
            settings.RATE_LIMIT_MANUAL_INTRO_CONFIRMS_PER_DAY = old_limit


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
        assert "detail" in resp.json()

    async def test_own_network_scope_is_free(self, client: AsyncClient, seeker_auth):
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
