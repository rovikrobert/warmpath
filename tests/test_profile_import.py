"""Tests for resume PDF upload and LinkedIn OAuth features."""

import io

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.enrichment import UsageLog
from tests.conftest import TestSessionLocal, create_test_user_in_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _signup_and_get_token(
    client: AsyncClient, email: str = "import@test.com"
) -> str:
    """Create a test user and return auth token."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email=email, full_name="Import User"
        )
    return headers["Authorization"].split(" ")[1]


async def _signup(client: AsyncClient, email: str = "import@test.com") -> str:
    """Alias for _signup_and_get_token — used by TestResumeUpload."""
    return await _signup_and_get_token(client, email=email)


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
            files={
                "file": (
                    "resume.docx",
                    io.BytesIO(b"not a pdf"),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
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
            files={
                "file": ("resume.pdf", io.BytesIO(b"NOT_A_PDF_FILE"), "application/pdf")
            },
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


class TestLinkedInOAuthUnconfigured:
    """LinkedIn endpoints return 503 when credentials are not configured."""

    @pytest.mark.asyncio
    async def test_authorize_returns_503_when_unconfigured(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/linkedin/authorize")
        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_callback_returns_503_when_unconfigured(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/linkedin/callback",
            json={"code": "any_code", "state": "any_state"},
        )
        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"].lower()


class TestLinkedInOAuth:
    @pytest.fixture(autouse=True)
    def _enable_linkedin_mock(self, monkeypatch):
        """Set a test client ID so the endpoint guard passes, but service stays in mock mode."""
        from app.config import settings

        monkeypatch.setattr(settings, "LINKEDIN_CLIENT_ID", "test_client_id")
        monkeypatch.setattr(settings, "LINKEDIN_CLIENT_SECRET", "test_client_secret")
        monkeypatch.setattr(
            settings,
            "LINKEDIN_REDIRECT_URI",
            "http://localhost:3000/auth/linkedin/callback",
        )

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

