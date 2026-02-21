"""Tests for application tracker — pipeline, stats, auto-timestamps, follow-up, from-intro."""

import uuid as uuid_mod
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from httpx import AsyncClient

from app.models.contact import Contact
from app.models.job import Application, JobOpening
from app.models.match_result import IntroRequest, MatchResult
from app.models.search_request import SearchRequest
from tests.conftest import TestSessionLocal, create_test_user_in_db

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    """Create a test user and return auth headers."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="apptest@test.com", full_name="App Tester"
        )
    return headers


@pytest_asyncio.fixture
async def user_id(auth_headers: dict, client: AsyncClient) -> str:
    """Get the current user's ID."""
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    return resp.json()["data"]["id"]


@pytest_asyncio.fixture
async def contact_id(auth_headers: dict, user_id: str) -> str:
    """Create a test contact and return its ID."""
    async with TestSessionLocal() as db:
        contact = Contact(
            user_id=uuid_mod.UUID(user_id),
            full_name="Alice Engineer",
            first_name="Alice",
            last_name="Engineer",
            current_company="Stripe",
            current_title="Senior Engineer",
            location="San Francisco, CA",
        )
        db.add(contact)
        await db.commit()
        await db.refresh(contact)
        return str(contact.id)


@pytest_asyncio.fixture
async def job_opening_id() -> str:
    """Create a test job opening and return its ID."""
    async with TestSessionLocal() as db:
        jo = JobOpening(
            title="Senior Software Engineer",
            url="https://example.com/jobs/1",
            source="greenhouse",
            source_job_id="test-001",
            department="Engineering",
            location="San Francisco, CA",
        )
        db.add(jo)
        await db.commit()
        await db.refresh(jo)
        return str(jo.id)


# ---------------------------------------------------------------------------
# Test CRUD Operations
# ---------------------------------------------------------------------------


class TestApplicationCRUD:
    async def test_create_application(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            "/api/v1/applications",
            headers=auth_headers,
            json={"company_name": "Stripe", "role_title": "Software Engineer"},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["company_name"] == "Stripe"
        assert data["role_title"] == "Software Engineer"
        assert data["status"] == "draft"

    async def test_create_with_contact(
        self, client: AsyncClient, auth_headers: dict, contact_id: str
    ):
        resp = await client.post(
            "/api/v1/applications",
            headers=auth_headers,
            json={
                "company_name": "Stripe",
                "contact_id": contact_id,
                "channel": "linkedin",
            },
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["contact_id"] == contact_id
        assert data["contact_name"] == "Alice Engineer"
        assert data["channel"] == "linkedin"

    async def test_create_with_job_opening(
        self, client: AsyncClient, auth_headers: dict, job_opening_id: str
    ):
        resp = await client.post(
            "/api/v1/applications",
            headers=auth_headers,
            json={
                "company_name": "Stripe",
                "job_opening_id": job_opening_id,
            },
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["job_opening_id"] == job_opening_id
        assert data["job_opening_title"] == "Senior Software Engineer"

    async def test_create_invalid_contact(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.post(
            "/api/v1/applications",
            headers=auth_headers,
            json={
                "company_name": "Stripe",
                "contact_id": "00000000-0000-0000-0000-000000000001",
            },
        )
        assert resp.status_code == 404

    async def test_get_application(self, client: AsyncClient, auth_headers: dict):
        # Create first
        create_resp = await client.post(
            "/api/v1/applications",
            headers=auth_headers,
            json={"company_name": "Google"},
        )
        app_id = create_resp.json()["data"]["id"]

        # Get
        resp = await client.get(f"/api/v1/applications/{app_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["company_name"] == "Google"

    async def test_get_nonexistent(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get(
            "/api/v1/applications/00000000-0000-0000-0000-000000000001",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_list_applications(self, client: AsyncClient, auth_headers: dict):
        await client.post(
            "/api/v1/applications",
            headers=auth_headers,
            json={"company_name": "Apple"},
        )
        await client.post(
            "/api/v1/applications",
            headers=auth_headers,
            json={"company_name": "Meta"},
        )

        resp = await client.get("/api/v1/applications", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["meta"]["count"] == 2

    async def test_list_filter_by_status(self, client: AsyncClient, auth_headers: dict):
        create_resp = await client.post(
            "/api/v1/applications",
            headers=auth_headers,
            json={"company_name": "Netflix"},
        )
        app_id = create_resp.json()["data"]["id"]

        # Update to message_sent
        await client.patch(
            f"/api/v1/applications/{app_id}",
            headers=auth_headers,
            json={"status": "message_sent"},
        )

        # Create another that stays draft
        await client.post(
            "/api/v1/applications",
            headers=auth_headers,
            json={"company_name": "Amazon"},
        )

        # Filter by message_sent
        resp = await client.get(
            "/api/v1/applications?status=message_sent", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["company_name"] == "Netflix"

    async def test_list_filter_by_company(
        self, client: AsyncClient, auth_headers: dict
    ):
        await client.post(
            "/api/v1/applications",
            headers=auth_headers,
            json={"company_name": "OpenAI"},
        )
        await client.post(
            "/api/v1/applications",
            headers=auth_headers,
            json={"company_name": "Anthropic"},
        )

        resp = await client.get(
            "/api/v1/applications?company=open", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["meta"]["count"] == 1
        assert resp.json()["data"][0]["company_name"] == "OpenAI"

    async def test_soft_delete(self, client: AsyncClient, auth_headers: dict):
        create_resp = await client.post(
            "/api/v1/applications",
            headers=auth_headers,
            json={"company_name": "Twitter"},
        )
        app_id = create_resp.json()["data"]["id"]

        # Delete
        del_resp = await client.delete(
            f"/api/v1/applications/{app_id}", headers=auth_headers
        )
        assert del_resp.status_code == 200
        assert del_resp.json()["data"]["deleted"] is True

        # Can't find it anymore
        get_resp = await client.get(
            f"/api/v1/applications/{app_id}", headers=auth_headers
        )
        assert get_resp.status_code == 404

    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/applications")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Test Pipeline Status Transitions
# ---------------------------------------------------------------------------


class TestPipelineTransitions:
    async def test_full_pipeline(self, client: AsyncClient, auth_headers: dict):
        """Walk through: draft → sent → responded → interview → offer."""
        create_resp = await client.post(
            "/api/v1/applications",
            headers=auth_headers,
            json={
                "company_name": "Stripe",
                "role_title": "SWE",
                "channel": "linkedin",
            },
        )
        app_id = create_resp.json()["data"]["id"]
        assert create_resp.json()["data"]["status"] == "draft"

        # draft → message_sent
        resp = await client.patch(
            f"/api/v1/applications/{app_id}",
            headers=auth_headers,
            json={"status": "message_sent"},
        )
        data = resp.json()["data"]
        assert data["status"] == "message_sent"
        assert data["sent_at"] is not None

        # message_sent → responded
        resp = await client.patch(
            f"/api/v1/applications/{app_id}",
            headers=auth_headers,
            json={"status": "responded"},
        )
        data = resp.json()["data"]
        assert data["status"] == "responded"
        assert data["responded_at"] is not None

        # responded → interview_scheduled
        resp = await client.patch(
            f"/api/v1/applications/{app_id}",
            headers=auth_headers,
            json={"status": "interview_scheduled"},
        )
        assert resp.json()["data"]["status"] == "interview_scheduled"

        # interview_scheduled → interviewed
        resp = await client.patch(
            f"/api/v1/applications/{app_id}",
            headers=auth_headers,
            json={"status": "interviewed"},
        )
        assert resp.json()["data"]["status"] == "interviewed"

        # interviewed → offer_received
        resp = await client.patch(
            f"/api/v1/applications/{app_id}",
            headers=auth_headers,
            json={"status": "offer_received"},
        )
        assert resp.json()["data"]["status"] == "offer_received"

        # offer_received → offer_accepted
        resp = await client.patch(
            f"/api/v1/applications/{app_id}",
            headers=auth_headers,
            json={"status": "offer_accepted"},
        )
        assert resp.json()["data"]["status"] == "offer_accepted"

    async def test_auto_sent_at(self, client: AsyncClient, auth_headers: dict):
        """sent_at auto-set when status changes to message_sent."""
        create_resp = await client.post(
            "/api/v1/applications",
            headers=auth_headers,
            json={"company_name": "Google"},
        )
        app_id = create_resp.json()["data"]["id"]
        assert create_resp.json()["data"]["sent_at"] is None

        resp = await client.patch(
            f"/api/v1/applications/{app_id}",
            headers=auth_headers,
            json={"status": "message_sent"},
        )
        assert resp.json()["data"]["sent_at"] is not None

    async def test_auto_responded_at(self, client: AsyncClient, auth_headers: dict):
        """responded_at auto-set when status changes to responded."""
        create_resp = await client.post(
            "/api/v1/applications",
            headers=auth_headers,
            json={"company_name": "Meta"},
        )
        app_id = create_resp.json()["data"]["id"]

        await client.patch(
            f"/api/v1/applications/{app_id}",
            headers=auth_headers,
            json={"status": "message_sent"},
        )

        resp = await client.patch(
            f"/api/v1/applications/{app_id}",
            headers=auth_headers,
            json={"status": "responded"},
        )
        assert resp.json()["data"]["responded_at"] is not None

    async def test_invalid_status(self, client: AsyncClient, auth_headers: dict):
        create_resp = await client.post(
            "/api/v1/applications",
            headers=auth_headers,
            json={"company_name": "BadCorp"},
        )
        app_id = create_resp.json()["data"]["id"]

        resp = await client.patch(
            f"/api/v1/applications/{app_id}",
            headers=auth_headers,
            json={"status": "invalid_status"},
        )
        assert resp.status_code == 422

    async def test_update_notes_and_follow_up(
        self, client: AsyncClient, auth_headers: dict
    ):
        create_resp = await client.post(
            "/api/v1/applications",
            headers=auth_headers,
            json={"company_name": "Notion"},
        )
        app_id = create_resp.json()["data"]["id"]

        follow_up = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        resp = await client.patch(
            f"/api/v1/applications/{app_id}",
            headers=auth_headers,
            json={
                "notes": "Sent via LinkedIn, awaiting reply",
                "follow_up_at": follow_up,
            },
        )
        data = resp.json()["data"]
        assert data["notes"] == "Sent via LinkedIn, awaiting reply"
        assert data["follow_up_at"] is not None


# ---------------------------------------------------------------------------
# Test Needs Follow-Up Logic
# ---------------------------------------------------------------------------


class TestNeedsFollowUp:
    async def test_needs_follow_up_7_days(
        self, client: AsyncClient, auth_headers: dict, user_id: str
    ):
        """Application needs follow-up when 7+ days since sent with no response."""
        async with TestSessionLocal() as db:
            app_record = Application(
                user_id=uuid_mod.UUID(user_id),
                company_name="SlowCo",
                status="message_sent",
                channel="linkedin",
                sent_at=datetime.now(timezone.utc) - timedelta(days=8),
            )
            db.add(app_record)
            await db.commit()
            await db.refresh(app_record)
            app_id = str(app_record.id)

        resp = await client.get(f"/api/v1/applications/{app_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["needs_follow_up"] is True
        assert resp.json()["data"]["days_since_sent"] >= 7

    async def test_needs_follow_up_past_date(
        self, client: AsyncClient, auth_headers: dict, user_id: str
    ):
        """Application needs follow-up when follow_up_at is in the past."""
        async with TestSessionLocal() as db:
            app_record = Application(
                user_id=uuid_mod.UUID(user_id),
                company_name="UrgentCo",
                status="message_sent",
                channel="email",
                sent_at=datetime.now(timezone.utc) - timedelta(days=2),
                follow_up_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
            db.add(app_record)
            await db.commit()
            await db.refresh(app_record)
            app_id = str(app_record.id)

        resp = await client.get(f"/api/v1/applications/{app_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["needs_follow_up"] is True

    async def test_no_follow_up_when_responded(
        self, client: AsyncClient, auth_headers: dict, user_id: str
    ):
        """No follow-up needed if already responded."""
        async with TestSessionLocal() as db:
            app_record = Application(
                user_id=uuid_mod.UUID(user_id),
                company_name="FastCo",
                status="responded",
                sent_at=datetime.now(timezone.utc) - timedelta(days=10),
                responded_at=datetime.now(timezone.utc) - timedelta(days=3),
            )
            db.add(app_record)
            await db.commit()
            await db.refresh(app_record)
            app_id = str(app_record.id)

        resp = await client.get(f"/api/v1/applications/{app_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["needs_follow_up"] is False

    async def test_filter_needs_follow_up(
        self, client: AsyncClient, auth_headers: dict, user_id: str
    ):
        """GET /applications?needs_follow_up=true returns only those needing follow-up."""
        uid = uuid_mod.UUID(user_id)
        async with TestSessionLocal() as db:
            # One needing follow-up
            db.add(
                Application(
                    user_id=uid,
                    company_name="NeedFollowUp",
                    status="message_sent",
                    sent_at=datetime.now(timezone.utc) - timedelta(days=10),
                )
            )
            # One that doesn't
            db.add(
                Application(
                    user_id=uid,
                    company_name="AllGood",
                    status="draft",
                )
            )
            await db.commit()

        resp = await client.get(
            "/api/v1/applications?needs_follow_up=true", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 1
        assert all(a["needs_follow_up"] is True for a in data)


# ---------------------------------------------------------------------------
# Test Stats Endpoint
# ---------------------------------------------------------------------------


class TestApplicationStats:
    async def test_stats_empty(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/applications/stats", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 0
        assert data["response_rate"] == 0.0
        assert data["interview_rate"] == 0.0

    async def test_stats_with_data(
        self, client: AsyncClient, auth_headers: dict, user_id: str
    ):
        """Test stats with multiple applications in various states."""
        now = datetime.now(timezone.utc)
        uid = uuid_mod.UUID(user_id)
        async with TestSessionLocal() as db:
            # 1 draft
            db.add(
                Application(
                    user_id=uid,
                    company_name="DraftCo",
                    status="draft",
                    channel="linkedin",
                )
            )
            # 2 sent via linkedin (1 responded)
            db.add(
                Application(
                    user_id=uid,
                    company_name="SentCo1",
                    status="message_sent",
                    channel="linkedin",
                    sent_at=now - timedelta(days=5),
                )
            )
            db.add(
                Application(
                    user_id=uid,
                    company_name="SentCo2",
                    status="responded",
                    channel="linkedin",
                    sent_at=now - timedelta(days=10),
                    responded_at=now - timedelta(days=7),
                )
            )
            # 1 interview via email
            db.add(
                Application(
                    user_id=uid,
                    company_name="InterviewCo",
                    status="interview_scheduled",
                    channel="email",
                    sent_at=now - timedelta(days=14),
                    responded_at=now - timedelta(days=10),
                )
            )
            await db.commit()

        resp = await client.get("/api/v1/applications/stats", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 4
        assert data["by_status"]["draft"] == 1
        assert data["by_status"]["message_sent"] == 1
        assert data["by_status"]["responded"] == 1
        assert data["by_status"]["interview_scheduled"] == 1

        # sent_count = 3 (everything except draft)
        # responded_count = 2 (responded + interview_scheduled)
        # interview_count = 1
        assert data["response_rate"] == round(2 / 3, 3)
        assert data["interview_rate"] == round(1 / 3, 3)

        # Avg days to response: (3 + 4) / 2 = 3.5
        assert data["avg_days_to_response"] is not None

        # Best channel: email has 100% response rate (1/1), linkedin has 50% (1/2)
        assert data["best_channel"] == "email"


# ---------------------------------------------------------------------------
# Test From-Intro Creation
# ---------------------------------------------------------------------------


class TestFromIntro:
    async def test_create_from_intro(
        self, client: AsyncClient, auth_headers: dict, user_id: str, contact_id: str
    ):
        """Create application from existing intro request."""
        async with TestSessionLocal() as db:
            intro_req = IntroRequest(
                user_id=uuid_mod.UUID(user_id),
                contact_id=uuid_mod.UUID(contact_id),
                channel="linkedin",
                status="completed",
            )
            db.add(intro_req)
            await db.commit()
            await db.refresh(intro_req)
            intro_id = str(intro_req.id)

        resp = await client.post(
            f"/api/v1/applications/from-intro/{intro_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["contact_id"] == contact_id
        assert data["company_name"] == "Stripe"  # from contact's current_company
        assert data["channel"] == "linkedin"
        assert data["status"] == "draft"

    async def test_create_from_intro_with_job(
        self,
        client: AsyncClient,
        auth_headers: dict,
        user_id: str,
        contact_id: str,
        job_opening_id: str,
    ):
        """From-intro includes job opening title when available."""
        async with TestSessionLocal() as db:
            intro_req = IntroRequest(
                user_id=uuid_mod.UUID(user_id),
                contact_id=uuid_mod.UUID(contact_id),
                job_opening_id=uuid_mod.UUID(job_opening_id),
                channel="email",
                status="completed",
            )
            db.add(intro_req)
            await db.commit()
            await db.refresh(intro_req)
            intro_id = str(intro_req.id)

        resp = await client.post(
            f"/api/v1/applications/from-intro/{intro_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["role_title"] == "Senior Software Engineer"
        assert data["job_opening_id"] == job_opening_id

    async def test_from_intro_not_found(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            "/api/v1/applications/from-intro/00000000-0000-0000-0000-000000000001",
            headers=auth_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test From-Facilitation (Marketplace Attribution)
# ---------------------------------------------------------------------------


class TestFromFacilitation:
    async def test_create_from_approved_facilitation_sets_marketplace_attribution(
        self, client: AsyncClient, auth_headers: dict, user_id: str
    ):
        """Approved marketplace facilitation creates app with source_type=marketplace."""
        from app.models.company import Company
        from app.models.marketplace import IntroFacilitation, MarketplaceListing

        uid = uuid_mod.UUID(user_id)
        async with TestSessionLocal() as db:
            # Network holder
            from app.models.user import User

            nh = User(
                clerk_user_id="nh_facilitation_test",
                email="nh@facilitation.test",
                full_name="Network Holder",
                onboarding_completed_at=datetime.now(timezone.utc),
            )
            db.add(nh)
            await db.flush()

            company = Company(name="Google", domain="google.com")
            db.add(company)
            await db.flush()

            contact = Contact(
                user_id=nh.id,
                full_name="Contact Person",
                current_company="Google",
                company_id=company.id,
            )
            db.add(contact)
            await db.flush()

            listing = MarketplaceListing(
                network_holder_id=nh.id,
                contact_id=contact.id,
                company_id=company.id,
                role_level="senior",
                department_category="engineering",
                warm_score_range="60-80",
                connection_recency="recent",
            )
            db.add(listing)
            await db.flush()

            facilitation = IntroFacilitation(
                job_seeker_id=uid,
                network_holder_id=nh.id,
                marketplace_listing_id=listing.id,
                status="approved",
                reviewed_at=datetime.now(timezone.utc),
            )
            db.add(facilitation)
            await db.commit()
            await db.refresh(facilitation)
            facilitation_id = str(facilitation.id)
            listing_id = str(listing.id)

        resp = await client.post(
            f"/api/v1/applications/from-facilitation/{facilitation_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["company_name"] == "Google"
        assert data["source_type"] == "marketplace"
        assert data["source_intro_id"] == facilitation_id
        assert data["source_listing_id"] == listing_id
        assert data["status"] == "draft"

    async def test_from_facilitation_rejects_pending_status(
        self, client: AsyncClient, auth_headers: dict, user_id: str
    ):
        """Cannot create application from non-approved facilitation."""
        from app.models.marketplace import IntroFacilitation, MarketplaceListing

        uid = uuid_mod.UUID(user_id)
        async with TestSessionLocal() as db:
            from app.models.company import Company
            from app.models.user import User

            nh = User(
                clerk_user_id="nh_pending_test",
                email="nh@pending.test",
                full_name="NH Pending",
                onboarding_completed_at=datetime.now(timezone.utc),
            )
            db.add(nh)
            await db.flush()

            company = Company(name="Meta", domain="meta.com")
            db.add(company)
            await db.flush()

            contact = Contact(
                user_id=nh.id,
                full_name="Meta Contact",
                current_company="Meta",
                company_id=company.id,
            )
            db.add(contact)
            await db.flush()

            listing = MarketplaceListing(
                network_holder_id=nh.id,
                contact_id=contact.id,
                company_id=company.id,
                role_level="mid",
                department_category="product",
                warm_score_range="40-60",
                connection_recency="recent",
            )
            db.add(listing)
            await db.flush()

            facilitation = IntroFacilitation(
                job_seeker_id=uid,
                network_holder_id=nh.id,
                marketplace_listing_id=listing.id,
                status="requested",
            )
            db.add(facilitation)
            await db.commit()
            await db.refresh(facilitation)
            facilitation_id = str(facilitation.id)

        resp = await client.post(
            f"/api/v1/applications/from-facilitation/{facilitation_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "approved" in resp.json()["detail"].lower()

    async def test_from_facilitation_not_found(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Returns 404 for nonexistent facilitation ID."""
        resp = await client.post(
            "/api/v1/applications/from-facilitation/00000000-0000-0000-0000-000000000099",
            headers=auth_headers,
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    async def test_from_facilitation_wrong_user(
        self, client: AsyncClient, user_id: str
    ):
        """Returns 404 when facilitation belongs to a different job seeker."""
        from app.models.marketplace import IntroFacilitation, MarketplaceListing

        async with TestSessionLocal() as db:
            from app.models.company import Company
            from app.models.user import User

            other_seeker = User(
                clerk_user_id="other_seeker_test",
                email="other@seeker.test",
                full_name="Other Seeker",
                onboarding_completed_at=datetime.now(timezone.utc),
            )
            nh = User(
                clerk_user_id="nh_wrong_user_test",
                email="nh@wronguser.test",
                full_name="NH Wrong User",
                onboarding_completed_at=datetime.now(timezone.utc),
            )
            db.add_all([other_seeker, nh])
            await db.flush()

            company = Company(name="Apple", domain="apple.com")
            db.add(company)
            await db.flush()

            contact = Contact(
                user_id=nh.id,
                full_name="Apple Contact",
                current_company="Apple",
                company_id=company.id,
            )
            db.add(contact)
            await db.flush()

            listing = MarketplaceListing(
                network_holder_id=nh.id,
                contact_id=contact.id,
                company_id=company.id,
                role_level="senior",
                department_category="engineering",
                warm_score_range="80-100",
                connection_recency="recent",
            )
            db.add(listing)
            await db.flush()

            # Facilitation belongs to other_seeker, not current user
            facilitation = IntroFacilitation(
                job_seeker_id=other_seeker.id,
                network_holder_id=nh.id,
                marketplace_listing_id=listing.id,
                status="approved",
                reviewed_at=datetime.now(timezone.utc),
            )
            db.add(facilitation)
            await db.commit()
            await db.refresh(facilitation)
            facilitation_id = str(facilitation.id)

        # Auth headers for user_id (not other_seeker)
        _, wrong_headers = None, None
        async with TestSessionLocal() as db:
            _, wrong_headers = await create_test_user_in_db(
                db, email="wronguser@test.com", full_name="Wrong User"
            )

        resp = await client.post(
            f"/api/v1/applications/from-facilitation/{facilitation_id}",
            headers=wrong_headers,
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test Suggest Track on Message Select
# ---------------------------------------------------------------------------


class TestSuggestTrack:
    async def test_patch_message_suggests_tracking(
        self, client: AsyncClient, auth_headers: dict, user_id: str, contact_id: str
    ):
        """When a user selects an intro message, response includes suggest_track."""
        uid = uuid_mod.UUID(user_id)
        cid = uuid_mod.UUID(contact_id)
        async with TestSessionLocal() as db:
            sr = SearchRequest(
                user_id=uid,
                name="Stripe Engineer Search",
                target_role="Engineer",
                target_companies=["Stripe"],
                status="completed",
            )
            db.add(sr)
            await db.flush()

            mr = MatchResult(
                search_request_id=sr.id,
                contact_id=cid,
                user_id=uid,
                relevance_score=85.0,
                match_reasoning="Good match",
                match_type="direct",
            )
            db.add(mr)
            await db.commit()
            await db.refresh(mr)
            match_result_id = str(mr.id)

        # Create intro via API
        intro_resp = await client.post(
            "/api/v1/matches/intros",
            headers=auth_headers,
            json={
                "contact_id": contact_id,
                "match_result_id": match_result_id,
                "channel": "linkedin",
            },
        )
        assert intro_resp.status_code == 201
        intro_data = intro_resp.json()["data"]
        intro_id = intro_data["id"]
        message_id = intro_data["messages"][0]["id"]

        # Select the message
        patch_resp = await client.patch(
            f"/api/v1/matches/intros/{intro_id}/messages/{message_id}",
            headers=auth_headers,
            json={"is_selected": True},
        )
        assert patch_resp.status_code == 200
        meta = patch_resp.json()["meta"]
        assert meta["suggest_track"] is True
        assert "prefilled_application" in meta
        prefilled = meta["prefilled_application"]
        assert prefilled["contact_id"] == contact_id
        assert prefilled["channel"] == "linkedin"


# ---------------------------------------------------------------------------
# by_source breakdown in stats
# ---------------------------------------------------------------------------


async def test_stats_includes_by_source_breakdown(client: AsyncClient):
    """Stats endpoint returns interview rates broken down by source_type."""
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="sourcestats@test.com", full_name="Source Stats"
        )
        # Create referral apps (2 sent, 1 interview)
        for i, app_status in enumerate(["message_sent", "interview_scheduled"]):
            app = Application(
                user_id=user.id,
                company_name=f"RefCo{i}",
                status=app_status,
                source_type="own_network",
            )
            db.add(app)
        # Create manual apps (3 sent, 0 interviews)
        for i in range(3):
            app = Application(
                user_id=user.id,
                company_name=f"ColdCo{i}",
                status="message_sent",
                source_type="manual",
            )
            db.add(app)
        await db.commit()

    resp = await client.get("/api/v1/applications/stats", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "by_source" in data
    own = data["by_source"]["own_network"]
    assert own["sent"] == 2
    assert own["interview_rate"] == 0.5
    manual = data["by_source"]["manual"]
    assert manual["sent"] == 3
    assert manual["interview_rate"] == 0.0
