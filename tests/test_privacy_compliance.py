"""Tests for privacy compliance — all 11 gaps from privacy policy audit.

Covers:
- Gap 1:  Data retention sweeps (usage log purge, credit archive)
- Gap 2:  Data export / portability endpoint
- Gap 3:  Data rectification across vaults
- Gap 4:  Right to restrict processing
- Gap 5:  Marketing opt-out
- Gap 6:  Consent tracking
- Gap 7:  Breach notification infrastructure
- Gap 8:  Network holder notification on suppression
- Gap 9:  DSAR tracking with deadlines
- Gap 10: Public suppression request endpoint
- Gap 11: Usage log IP/user agent (verified via existing middleware)
"""

import uuid as uuid_mod
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.models.enrichment import UsageLog
from app.models.privacy import (
    ArchivedCreditTransaction,
    ConsentRecord,
    DataRequest,
)
from app.services.breach_notification import (
    create_data_request,
    get_pending_requests,
    resolve_data_request,
    send_breach_notification,
)
from app.services.data_retention import (
    archive_credit_history,
    purge_expired_archives,
    purge_old_usage_logs,
)
from app.services.suppression import rectify_contact_data
from tests.conftest import TestSessionLocal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "privacy@test.com",
            "password": "Testpass123",
            "full_name": "Privacy Tester",
        },
    )
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "privacy@test.com", "password": "Testpass123"},
    )
    token = login_res.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def user_id(client: AsyncClient, auth_headers: dict) -> uuid_mod.UUID:
    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    return uuid_mod.UUID(me.json()["data"]["id"])


@pytest_asyncio.fixture
async def user_with_contacts(auth_headers: dict, client: AsyncClient) -> dict:
    """Create user with contacts for suppression / rectification tests."""
    await client.post(
        "/api/v1/contacts/manual/bulk",
        headers=auth_headers,
        json={
            "contacts": [
                {
                    "first_name": "Alice",
                    "last_name": "Smith",
                    "company": "TechCorp",
                    "email": "alice@techcorp.com",
                },
                {
                    "first_name": "Bob",
                    "last_name": "Jones",
                    "company": "StartupXYZ",
                    "email": "bob@startupxyz.com",
                },
            ]
        },
    )
    return auth_headers


# ---------------------------------------------------------------------------
# Gap 1: Data retention sweeps
# ---------------------------------------------------------------------------


class TestDataRetention:
    async def test_archive_credit_history(
        self, client: AsyncClient, auth_headers: dict, user_id: uuid_mod.UUID
    ):
        """Credit history is archived via the service function."""
        from app.models.credits import CreditTransaction
        from app.services.credits import earn_credits

        # Create a credit transaction in the test session
        async with TestSessionLocal() as db:
            await earn_credits(user_id, 100, "test_archive", db)
            await db.commit()

        async with TestSessionLocal() as db:
            count = await archive_credit_history(user_id, db)
            await db.commit()

        assert count >= 1

        async with TestSessionLocal() as db:
            result = await db.execute(
                select(ArchivedCreditTransaction).where(
                    ArchivedCreditTransaction.original_user_id == user_id
                )
            )
            archives = result.scalars().all()
            assert len(archives) >= 1
            purge = archives[0].purge_after
            if purge.tzinfo is None:
                purge = purge.replace(tzinfo=timezone.utc)
            assert purge > datetime.now(timezone.utc)

    async def test_purge_old_usage_logs(
        self, client: AsyncClient, auth_headers: dict, user_id: uuid_mod.UUID
    ):
        """Usage logs older than 12 months are purged."""
        async with TestSessionLocal() as db:
            # Insert an old usage log
            old_log = UsageLog(
                user_id=user_id,
                action="test_action",
                created_at=datetime.now(timezone.utc) - timedelta(days=400),
            )
            db.add(old_log)
            await db.commit()

            count = await purge_old_usage_logs(db)
            await db.commit()

        assert count >= 1

    async def test_purge_expired_archives(self, client: AsyncClient):
        """Archived credit transactions past purge date are removed."""
        async with TestSessionLocal() as db:
            expired = ArchivedCreditTransaction(
                original_user_id=uuid_mod.uuid4(),
                original_transaction_id=uuid_mod.uuid4(),
                amount=100,
                type="earned",
                reason="test",
                original_created_at=datetime.now(timezone.utc) - timedelta(days=800),
                purge_after=datetime.now(timezone.utc) - timedelta(days=1),
            )
            db.add(expired)
            await db.commit()

            count = await purge_expired_archives(db)
            await db.commit()

        assert count >= 1

    async def test_account_delete_archives_credits(
        self, client: AsyncClient, auth_headers: dict, user_id: uuid_mod.UUID
    ):
        """Account deletion archives credit history before CASCADE delete."""
        resp = await client.post(
            "/api/v1/auth/delete-account",
            headers=auth_headers,
            json={"password": "Testpass123", "confirm_deletion": True},
        )
        assert resp.status_code == 200

        # Credit history should be in archive table
        async with TestSessionLocal() as db:
            result = await db.execute(
                select(ArchivedCreditTransaction).where(
                    ArchivedCreditTransaction.original_user_id == user_id
                )
            )
            assert len(result.scalars().all()) >= 1


# ---------------------------------------------------------------------------
# Gap 2: Data export
# ---------------------------------------------------------------------------


class TestDataExport:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/privacy/export-data")
        assert resp.status_code in (401, 403)

    async def test_export_returns_all_sections(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.get("/api/v1/privacy/export-data", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "user" in data
        assert "contacts" in data
        assert "credit_transactions" in data
        assert "applications" in data
        assert "search_history" in data
        assert "export_version" in data
        assert "exported_at" in data

    async def test_export_contains_user_info(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.get("/api/v1/privacy/export-data", headers=auth_headers)
        user_data = resp.json()["data"]["user"]
        assert user_data["email"] == "privacy@test.com"
        assert user_data["full_name"] == "Privacy Tester"

    async def test_export_contains_contacts(
        self, client: AsyncClient, user_with_contacts: dict
    ):
        resp = await client.get(
            "/api/v1/privacy/export-data", headers=user_with_contacts
        )
        contacts = resp.json()["data"]["contacts"]
        assert len(contacts) >= 2
        names = [c["first_name"] for c in contacts]
        assert "Alice" in names


# ---------------------------------------------------------------------------
# Gap 3: Data rectification
# ---------------------------------------------------------------------------


class TestDataRectification:
    async def test_rectify_by_email(
        self, client: AsyncClient, user_with_contacts: dict
    ):
        """Corrections are applied to matching contacts across vaults."""
        resp = await client.post(
            "/api/v1/privacy/rectification",
            json={
                "email": "alice@techcorp.com",
                "corrections": {"current_company": "NewCorp Inc."},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["records_updated"] >= 1

    async def test_rectify_requires_identification(self, client: AsyncClient):
        """Must provide email or name+company."""
        resp = await client.post(
            "/api/v1/privacy/rectification",
            json={"corrections": {"current_company": "NewCorp"}},
        )
        assert resp.status_code == 422

    async def test_rectify_no_match_returns_zero(
        self, client: AsyncClient, user_with_contacts: dict
    ):
        resp = await client.post(
            "/api/v1/privacy/rectification",
            json={
                "email": "nobody@example.com",
                "corrections": {"current_company": "X"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["records_updated"] == 0


# ---------------------------------------------------------------------------
# Gap 4: Right to restrict processing
# ---------------------------------------------------------------------------


class TestRestrictProcessing:
    async def test_restrict_processing(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.post(
            "/api/v1/privacy/restrict-processing", headers=auth_headers
        )
        assert resp.status_code == 200
        assert "restricted" in resp.json()["data"]["message"].lower()

    async def test_unrestrict_processing(
        self, client: AsyncClient, auth_headers: dict
    ):
        # First restrict
        await client.post(
            "/api/v1/privacy/restrict-processing", headers=auth_headers
        )
        # Then unrestrict
        resp = await client.post(
            "/api/v1/privacy/unrestrict-processing", headers=auth_headers
        )
        assert resp.status_code == 200
        assert "removed" in resp.json()["data"]["message"].lower()

    async def test_restricted_user_blocked_from_marketplace(
        self, client: AsyncClient, auth_headers: dict, user_id: uuid_mod.UUID
    ):
        """Restricted user cannot perform marketplace search."""
        # Verify email so we reach the restriction check
        async with TestSessionLocal() as db:
            from app.models.user import User

            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one()
            user.email_verified = True
            await db.commit()

        # Restrict processing
        await client.post(
            "/api/v1/privacy/restrict-processing", headers=auth_headers
        )
        # Attempt marketplace search
        resp = await client.post(
            "/api/v1/marketplace/search",
            headers=auth_headers,
            json={"company_names": ["Google"]},
        )
        assert resp.status_code == 403
        assert "restricted" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Gap 5: Marketing opt-out
# ---------------------------------------------------------------------------


class TestMarketingOptOut:
    async def test_opt_out(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            "/api/v1/privacy/marketing-opt-out", headers=auth_headers
        )
        assert resp.status_code == 200

    async def test_opt_in(self, client: AsyncClient, auth_headers: dict):
        await client.post(
            "/api/v1/privacy/marketing-opt-out", headers=auth_headers
        )
        resp = await client.post(
            "/api/v1/privacy/marketing-opt-in", headers=auth_headers
        )
        assert resp.status_code == 200

    async def test_opt_out_persists(self, client: AsyncClient, auth_headers: dict):
        await client.post(
            "/api/v1/privacy/marketing-opt-out", headers=auth_headers
        )
        me = await client.get("/api/v1/auth/me", headers=auth_headers)
        # marketing_opt_out flag should be in the user response
        # (depends on schema — verified via DB check below)
        user_id = uuid_mod.UUID(me.json()["data"]["id"])
        async with TestSessionLocal() as db:
            from app.models.user import User

            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one()
            assert user.marketing_opt_out is True


# ---------------------------------------------------------------------------
# Gap 6: Consent tracking
# ---------------------------------------------------------------------------


class TestConsentTracking:
    async def test_record_consent_granted(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.post(
            "/api/v1/privacy/consent",
            headers=auth_headers,
            json={"activity": "marketplace_participation", "action": "granted"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["activity"] == "marketplace_participation"

    async def test_withdraw_consent(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.post(
            "/api/v1/privacy/consent",
            headers=auth_headers,
            json={"activity": "ai_processing", "action": "withdrawn"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["action"] == "withdrawn"

    async def test_list_consent_records(
        self, client: AsyncClient, auth_headers: dict
    ):
        # Record two consents
        await client.post(
            "/api/v1/privacy/consent",
            headers=auth_headers,
            json={"activity": "analytics", "action": "granted"},
        )
        await client.post(
            "/api/v1/privacy/consent",
            headers=auth_headers,
            json={"activity": "marketing", "action": "withdrawn"},
        )

        resp = await client.get("/api/v1/privacy/consent", headers=auth_headers)
        assert resp.status_code == 200
        records = resp.json()["data"]
        assert len(records) >= 2

    async def test_invalid_action_rejected(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.post(
            "/api/v1/privacy/consent",
            headers=auth_headers,
            json={"activity": "test", "action": "invalid"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Gap 7: Breach notification
# ---------------------------------------------------------------------------


class TestBreachNotification:
    async def test_send_breach_notification(
        self, client: AsyncClient, auth_headers: dict, user_id: uuid_mod.UUID
    ):
        """Breach notifications are sent to affected users."""
        async with TestSessionLocal() as db:
            with patch("app.services.breach_notification._send_email") as mock_email:
                count = await send_breach_notification(
                    affected_user_ids=[user_id],
                    breach_summary="Test breach summary",
                    data_affected="Email addresses",
                    db=db,
                )
                await db.commit()

            assert count == 1
            mock_email.assert_called_once()
            call_args = mock_email.call_args
            assert "Security Notice" in call_args[1]["subject"]


# ---------------------------------------------------------------------------
# Gap 8: Network holder notification on suppression
# ---------------------------------------------------------------------------


class TestSuppressionNotification:
    async def test_holder_notified_on_suppression(
        self, client: AsyncClient, user_with_contacts: dict
    ):
        """Network holder receives email when their contact is suppressed."""
        with patch("app.services.email_service._send_email") as mock_email:
            resp = await client.post(
                "/api/v1/privacy/suppression-request",
                json={"email": "alice@techcorp.com"},
            )
            assert resp.status_code == 200
            # Should have sent notification to the network holder
            assert mock_email.called


# ---------------------------------------------------------------------------
# Gap 9: DSAR tracking
# ---------------------------------------------------------------------------


class TestDSARTracking:
    async def test_create_data_request(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.post(
            "/api/v1/privacy/data-request",
            headers=auth_headers,
            json={"request_type": "access", "regulation": "gdpr"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "pending"
        assert data["deadline"] is not None

    async def test_gdpr_30_day_deadline(
        self, client: AsyncClient, auth_headers: dict, user_id: uuid_mod.UUID
    ):
        async with TestSessionLocal() as db:
            request = await create_data_request(
                request_type="access",
                requester_email="test@test.com",
                user_id=user_id,
                regulation="gdpr",
                db=db,
            )
            await db.commit()

        # Deadline should be ~30 days from now
        now = datetime.now(timezone.utc)
        delta = request.deadline_at - now
        assert 29 <= delta.days <= 31

    async def test_ccpa_45_day_deadline(
        self, client: AsyncClient, auth_headers: dict, user_id: uuid_mod.UUID
    ):
        async with TestSessionLocal() as db:
            request = await create_data_request(
                request_type="deletion",
                requester_email="test@test.com",
                user_id=user_id,
                regulation="ccpa",
                db=db,
            )
            await db.commit()

        delta = request.deadline_at - datetime.now(timezone.utc)
        assert 44 <= delta.days <= 46

    async def test_resolve_data_request(
        self, client: AsyncClient, auth_headers: dict, user_id: uuid_mod.UUID
    ):
        async with TestSessionLocal() as db:
            request = await create_data_request(
                request_type="access",
                requester_email="test@test.com",
                user_id=user_id,
                regulation="general",
                db=db,
            )
            await db.flush()

            resolved = await resolve_data_request(
                request.id, "Data exported and sent via email", db
            )
            await db.commit()

        assert resolved.status == "completed"
        assert resolved.resolved_at is not None

    async def test_get_pending_requests(
        self, client: AsyncClient, auth_headers: dict, user_id: uuid_mod.UUID
    ):
        async with TestSessionLocal() as db:
            await create_data_request(
                request_type="access",
                requester_email="test@test.com",
                user_id=user_id,
                db=db,
            )
            await db.flush()

            pending = await get_pending_requests(db)
            await db.commit()

        assert len(pending) >= 1
        assert pending[0].status == "pending"


# ---------------------------------------------------------------------------
# Gap 10: Public suppression request
# ---------------------------------------------------------------------------


class TestPublicSuppressionRequest:
    async def test_suppression_by_email(
        self, client: AsyncClient, user_with_contacts: dict
    ):
        resp = await client.post(
            "/api/v1/privacy/suppression-request",
            json={"email": "bob@startupxyz.com"},
        )
        assert resp.status_code == 200
        assert "purged" in resp.json()["data"]["message"].lower()

    async def test_suppression_by_name_company(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/privacy/suppression-request",
            json={
                "first_name": "Unknown",
                "last_name": "Person",
                "company": "SomeCompany",
            },
        )
        assert resp.status_code == 200

    async def test_suppression_requires_identification(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/privacy/suppression-request",
            json={},
        )
        assert resp.status_code == 422

    async def test_no_auth_required(self, client: AsyncClient):
        """Suppression requests don't require authentication."""
        resp = await client.post(
            "/api/v1/privacy/suppression-request",
            json={"email": "anyone@example.com"},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Gap 11: Usage log metadata (IP, user agent)
# ---------------------------------------------------------------------------


class TestUsageLogMetadata:
    async def test_usage_log_has_ip_and_ua_columns(
        self, client: AsyncClient, auth_headers: dict, user_id: uuid_mod.UUID
    ):
        """Verify the UsageLog model has ip_address and user_agent columns."""
        # Make an API call to generate a usage log
        await client.get("/api/v1/auth/me", headers=auth_headers)

        async with TestSessionLocal() as db:
            result = await db.execute(
                select(UsageLog).where(UsageLog.user_id == user_id).limit(1)
            )
            log = result.scalar_one_or_none()

        # Log should exist and have these columns (may be None in test env)
        assert log is not None
        assert hasattr(log, "ip_address")
        assert hasattr(log, "user_agent")
