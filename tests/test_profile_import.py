"""Tests for resume PDF upload and LinkedIn OAuth features."""

import io

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.enrichment import UsageLog
from app.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _signup(client: AsyncClient, email: str = "import@test.com") -> str:
    """Signup and return access token."""
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Secret123", "full_name": "Import User"},
    )
    assert resp.status_code == 201
    return resp.json()["data"]["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_fake_pdf(content: bytes = b"some resume text") -> bytes:
    """Build a minimal byte sequence that starts with PDF magic bytes."""
    return b"%PDF-1.4 fake\n" + content


# ---------------------------------------------------------------------------
# Resume Parsing Tests
# ---------------------------------------------------------------------------


class TestResumeUpload:
    @pytest.mark.asyncio
    async def test_upload_resume_success(self, client: AsyncClient):
        token = await _signup(client)
        pdf = _make_fake_pdf()
        resp = await client.post(
            "/api/v1/auth/profile/import-resume",
            headers=_auth(token),
            files={"file": ("resume.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        # Mock mode returns deterministic data
        assert data["headline"] is not None
        assert data["current_company"] == "TechCorp Inc."
        assert data["current_title"] == "Senior Software Engineer"
        assert isinstance(data["work_history"], list)
        assert len(data["work_history"]) == 3

    @pytest.mark.asyncio
    async def test_upload_resume_wrong_file_type(self, client: AsyncClient):
        token = await _signup(client)
        resp = await client.post(
            "/api/v1/auth/profile/import-resume",
            headers=_auth(token),
            files={"file": ("resume.docx", io.BytesIO(b"not a pdf"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert resp.status_code == 400
        assert "PDF" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_resume_too_large(self, client: AsyncClient):
        token = await _signup(client)
        big_pdf = b"%PDF-1.4" + b"x" * (6 * 1024 * 1024)  # >5MB
        resp = await client.post(
            "/api/v1/auth/profile/import-resume",
            headers=_auth(token),
            files={"file": ("resume.pdf", io.BytesIO(big_pdf), "application/pdf")},
        )
        assert resp.status_code == 400
        assert "5 MB" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_resume_invalid_pdf(self, client: AsyncClient):
        token = await _signup(client)
        resp = await client.post(
            "/api/v1/auth/profile/import-resume",
            headers=_auth(token),
            files={"file": ("resume.pdf", io.BytesIO(b"NOT_A_PDF_FILE"), "application/pdf")},
        )
        assert resp.status_code == 400
        assert "not a valid PDF" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_resume_requires_auth(self, client: AsyncClient):
        pdf = _make_fake_pdf()
        resp = await client.post(
            "/api/v1/auth/profile/import-resume",
            files={"file": ("resume.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_upload_resume_logs_usage(self, client: AsyncClient):
        token = await _signup(client, email="resumelog@test.com")
        pdf = _make_fake_pdf()
        resp = await client.post(
            "/api/v1/auth/profile/import-resume",
            headers=_auth(token),
            files={"file": ("resume.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        assert resp.status_code == 200

        # Verify usage log was created
        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            result = await session.execute(
                select(UsageLog).where(UsageLog.action == "resume_parse")
            )
            log = result.scalar_one_or_none()
            assert log is not None
            assert log.action == "resume_parse"


# ---------------------------------------------------------------------------
# LinkedIn OAuth Tests
# ---------------------------------------------------------------------------


class TestLinkedInOAuth:
    @pytest.mark.asyncio
    async def test_linkedin_authorize_returns_url(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/linkedin/authorize")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "url" in data
        assert "state" in data
        # In mock mode, URL points to localhost callback
        assert "callback" in data["url"]

    @pytest.mark.asyncio
    async def test_linkedin_callback_creates_new_user(self, client: AsyncClient):
        # First get a valid state token
        auth_resp = await client.get("/api/v1/auth/linkedin/authorize")
        state = auth_resp.json()["data"]["state"]

        resp = await client.post(
            "/api/v1/auth/linkedin/callback",
            json={"code": "mock_code", "state": state},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_new_user"] is True
        assert data["access_token"]
        assert data["profile"]["name"] == "Mock LinkedIn User"
        assert data["profile"]["email"] == "linkedin.user@example.com"

    @pytest.mark.asyncio
    async def test_linkedin_callback_login_existing_user(self, client: AsyncClient):
        # Create user via first OAuth flow
        auth_resp = await client.get("/api/v1/auth/linkedin/authorize")
        state = auth_resp.json()["data"]["state"]
        await client.post(
            "/api/v1/auth/linkedin/callback",
            json={"code": "mock_code", "state": state},
        )

        # Login again — should recognize existing user
        auth_resp2 = await client.get("/api/v1/auth/linkedin/authorize")
        state2 = auth_resp2.json()["data"]["state"]
        resp = await client.post(
            "/api/v1/auth/linkedin/callback",
            json={"code": "mock_code", "state": state2},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["is_new_user"] is False

    @pytest.mark.asyncio
    async def test_linkedin_callback_links_existing_email_account(self, client: AsyncClient):
        # Create user with email/password first (using the mock LinkedIn email)
        signup_resp = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "linkedin.user@example.com",
                "password": "Secret123",
                "full_name": "Existing User",
            },
        )
        assert signup_resp.status_code == 201

        # Now do LinkedIn OAuth with same email — should link, not create new
        auth_resp = await client.get("/api/v1/auth/linkedin/authorize")
        state = auth_resp.json()["data"]["state"]
        resp = await client.post(
            "/api/v1/auth/linkedin/callback",
            json={"code": "mock_code", "state": state},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_new_user"] is False

        # Verify the user has LinkedIn linked
        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            result = await session.execute(
                select(User).where(User.email == "linkedin.user@example.com")
            )
            user = result.scalar_one()
            assert user.oauth_provider == "linkedin"
            assert user.oauth_provider_id == "mock_linkedin_id_12345"
            # Password should still be set
            assert user.password_hash is not None

    @pytest.mark.asyncio
    async def test_linkedin_callback_awards_welcome_bonus(self, client: AsyncClient):
        auth_resp = await client.get("/api/v1/auth/linkedin/authorize")
        state = auth_resp.json()["data"]["state"]
        resp = await client.post(
            "/api/v1/auth/linkedin/callback",
            json={"code": "mock_code", "state": state},
        )
        assert resp.status_code == 200
        token = resp.json()["data"]["access_token"]

        # Check credit balance
        balance_resp = await client.get(
            "/api/v1/credits/balance",
            headers=_auth(token),
        )
        assert balance_resp.status_code == 200
        assert balance_resp.json()["data"]["balance"] == 50

    @pytest.mark.asyncio
    async def test_linkedin_callback_no_bonus_if_suppressed(self, client: AsyncClient):
        """Re-registration guard: user who deleted account doesn't get welcome bonus again."""
        import hashlib

        from app.models.privacy import SuppressionList
        from tests.conftest import TestSessionLocal

        # Add suppression entry for the mock LinkedIn email
        async with TestSessionLocal() as session:
            from datetime import datetime, timezone

            entry = SuppressionList(
                email_hash=hashlib.sha256(b"linkedin.user@example.com").hexdigest(),
                reason="account_deleted",
                requested_at=datetime.now(timezone.utc),
            )
            session.add(entry)
            await session.commit()

        auth_resp = await client.get("/api/v1/auth/linkedin/authorize")
        state = auth_resp.json()["data"]["state"]
        resp = await client.post(
            "/api/v1/auth/linkedin/callback",
            json={"code": "mock_code", "state": state},
        )
        assert resp.status_code == 200
        token = resp.json()["data"]["access_token"]

        balance_resp = await client.get(
            "/api/v1/credits/balance",
            headers=_auth(token),
        )
        assert balance_resp.status_code == 200
        assert balance_resp.json()["data"]["balance"] == 0

    @pytest.mark.asyncio
    async def test_linkedin_callback_invalid_state(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/linkedin/callback",
            json={"code": "mock_code", "state": "totally_invalid_state_token"},
        )
        assert resp.status_code == 400
        assert "state" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_linkedin_callback_expired_state(self, client: AsyncClient):
        """Expired state token should be rejected."""
        from datetime import datetime, timedelta, timezone

        from jose import jwt

        from app.config import settings

        expired_payload = {
            "nonce": "test",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
            "type": "linkedin_state",
        }
        expired_state = jwt.encode(
            expired_payload, settings.SECRET_KEY, algorithm="HS256"
        )

        resp = await client.post(
            "/api/v1/auth/linkedin/callback",
            json={"code": "mock_code", "state": expired_state},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_linkedin_callback_with_credentials(self, client: AsyncClient):
        """Signup via LinkedIn with name/email/password creates account with password."""
        auth_resp = await client.get("/api/v1/auth/linkedin/authorize")
        state = auth_resp.json()["data"]["state"]

        resp = await client.post(
            "/api/v1/auth/linkedin/callback",
            json={
                "code": "mock_code",
                "state": state,
                "full_name": "Custom Name",
                "email": "custom@test.com",
                "password": "StrongPass1",
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_new_user"] is True
        assert data["access_token"]

        # Verify the user has the custom email, password, and LinkedIn linked
        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            result = await session.execute(
                select(User).where(User.email == "custom@test.com")
            )
            user = result.scalar_one()
            assert user.full_name == "Custom Name"
            assert user.password_hash is not None  # Password was stored
            assert user.oauth_provider == "linkedin"
            assert user.email_verified is False  # Not auto-verified when password provided

    @pytest.mark.asyncio
    async def test_linkedin_callback_with_credentials_can_login(self, client: AsyncClient):
        """User created via LinkedIn+credentials can also log in with email/password."""
        auth_resp = await client.get("/api/v1/auth/linkedin/authorize")
        state = auth_resp.json()["data"]["state"]

        await client.post(
            "/api/v1/auth/linkedin/callback",
            json={
                "code": "mock_code",
                "state": state,
                "full_name": "Login Test",
                "email": "logintest@test.com",
                "password": "StrongPass1",
            },
        )

        # Should be able to login with email/password
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "logintest@test.com", "password": "StrongPass1"},
        )
        assert login_resp.status_code == 200
        assert login_resp.json()["data"]["access_token"]

    @pytest.mark.asyncio
    async def test_linkedin_callback_weak_password_rejected(self, client: AsyncClient):
        """Weak password in LinkedIn signup should be rejected."""
        auth_resp = await client.get("/api/v1/auth/linkedin/authorize")
        state = auth_resp.json()["data"]["state"]

        resp = await client.post(
            "/api/v1/auth/linkedin/callback",
            json={
                "code": "mock_code",
                "state": state,
                "full_name": "Weak Pass",
                "email": "weak@test.com",
                "password": "123",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_forgot_password_oauth_user(self, client: AsyncClient):
        """OAuth-only user gets helpful message instead of reset email."""
        # Create user via LinkedIn OAuth
        auth_resp = await client.get("/api/v1/auth/linkedin/authorize")
        state = auth_resp.json()["data"]["state"]
        await client.post(
            "/api/v1/auth/linkedin/callback",
            json={"code": "mock_code", "state": state},
        )

        # Try forgot-password
        resp = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "linkedin.user@example.com"},
        )
        assert resp.status_code == 200
        msg = resp.json()["data"]["message"]
        assert "LinkedIn" in msg
