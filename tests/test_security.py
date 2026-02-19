"""Tests for S1-S6: JWT refresh, CSV hardening, headers, CORS, email verification,
lockout, audit log, Stripe webhook verification."""

import hashlib
import hmac
import io
import json
import time

from httpx import AsyncClient
from sqlalchemy import select

from app.models.audit import AuditLog
from app.services.csv_parser import sanitize_cell


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _signup(client: AsyncClient, email: str = "sec@example.com") -> dict:
    """Signup and return full response (including cookies)."""
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Secret123", "full_name": "Sec User"},
    )
    assert resp.status_code == 201
    return resp


async def _login(
    client: AsyncClient, email: str = "sec@example.com", password: str = "Secret123"
) -> dict:
    """Login and return full response."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    return resp


def _get_refresh_cookie(resp) -> str | None:
    """Extract refresh token value from set-cookie header."""
    for cookie_header in resp.headers.get_list("set-cookie"):
        if "warmpath_refresh_token=" in cookie_header:
            # Parse value from "warmpath_refresh_token=<value>; ..."
            parts = cookie_header.split(";")[0]
            return parts.split("=", 1)[1]
    return None


# ---------------------------------------------------------------------------
# S1a: Login returns access token in body + refresh token in cookie
# ---------------------------------------------------------------------------


class TestLoginTokens:
    async def test_signup_returns_access_and_refresh(self, client: AsyncClient):
        resp = await _signup(client)
        body = resp.json()
        assert body["data"]["access_token"]
        assert body["data"]["token_type"] == "bearer"
        refresh = _get_refresh_cookie(resp)
        assert refresh is not None

    async def test_login_returns_access_and_refresh(self, client: AsyncClient):
        await _signup(client)
        resp = await _login(client)
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["access_token"]
        assert body["data"]["token_type"] == "bearer"
        refresh = _get_refresh_cookie(resp)
        assert refresh is not None

        # Decode the access token and verify JWT claims
        from jose import jwt
        from app.config import settings

        payload = jwt.decode(
            body["data"]["access_token"], settings.SECRET_KEY, algorithms=["HS256"]
        )
        assert payload["type"] == "access"
        assert "sub" in payload  # user ID
        assert "ver" in payload  # token version
        assert "exp" in payload  # expiration

    async def test_refresh_cookie_is_httponly(self, client: AsyncClient):
        resp = await _signup(client)
        cookie_headers = resp.headers.get_list("set-cookie")
        refresh_header = [h for h in cookie_headers if "warmpath_refresh_token" in h]
        assert len(refresh_header) == 1
        assert "httponly" in refresh_header[0].lower()

    async def test_refresh_cookie_samesite_strict(self, client: AsyncClient):
        resp = await _signup(client)
        cookie_headers = resp.headers.get_list("set-cookie")
        refresh_header = [h for h in cookie_headers if "warmpath_refresh_token" in h][0]
        assert "samesite=strict" in refresh_header.lower()


# ---------------------------------------------------------------------------
# S1b: Refresh token endpoint
# ---------------------------------------------------------------------------


class TestRefreshToken:
    async def test_refresh_returns_new_access_token(self, client: AsyncClient):
        resp = await _signup(client)
        refresh = _get_refresh_cookie(resp)

        client.cookies.set("warmpath_refresh_token", refresh)
        resp2 = await client.post("/api/v1/auth/refresh")
        assert resp2.status_code == 200
        body = resp2.json()
        assert body["data"]["access_token"]
        # Should also get a rotated refresh token cookie
        new_refresh = _get_refresh_cookie(resp2)
        assert new_refresh is not None

    async def test_refresh_without_cookie_returns_401(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/refresh")
        assert resp.status_code == 401
        body = resp.json()
        assert "detail" in body
        # Should not leak any internal info about the expected cookie name
        assert "warmpath_refresh_token" not in body.get("detail", "").lower()

    async def test_refresh_with_access_token_rejects(self, client: AsyncClient):
        """An access token should not work as a refresh token."""
        resp = await _signup(client)
        access = resp.json()["data"]["access_token"]

        client.cookies.set("warmpath_refresh_token", access)
        resp2 = await client.post("/api/v1/auth/refresh")
        assert resp2.status_code == 401
        # Verify the rejection is due to token type mismatch
        detail = resp2.json().get("detail", "")
        assert "refresh" in detail.lower() or "token" in detail.lower()

    async def test_refresh_rotates_token(self, client: AsyncClient):
        """Each refresh should issue a new, different refresh token."""
        resp = await _signup(client)
        refresh1 = _get_refresh_cookie(resp)

        client.cookies.set("warmpath_refresh_token", refresh1)
        resp2 = await client.post("/api/v1/auth/refresh")
        refresh2 = _get_refresh_cookie(resp2)
        assert refresh2 is not None
        assert refresh2 != refresh1


# ---------------------------------------------------------------------------
# S1c: Token version invalidation
# ---------------------------------------------------------------------------


class TestTokenVersioning:
    async def test_old_access_token_rejected_after_version_bump(
        self, client: AsyncClient
    ):
        """After logout-all (token_version++), old tokens should be rejected."""
        resp = await _signup(client)
        old_token = resp.json()["data"]["access_token"]

        # logout-all increments token_version
        resp2 = await client.post(
            "/api/v1/auth/logout-all",
            headers={"Authorization": f"Bearer {old_token}"},
        )
        assert resp2.status_code == 200

        # Old token should now be rejected
        resp3 = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {old_token}"},
        )
        assert resp3.status_code == 401
        assert "revoked" in resp3.json()["detail"].lower()

    async def test_old_refresh_token_rejected_after_version_bump(
        self, client: AsyncClient
    ):
        """After logout-all, old refresh token should be rejected."""
        resp = await _signup(client)
        old_refresh = _get_refresh_cookie(resp)
        access = resp.json()["data"]["access_token"]

        # logout-all
        await client.post(
            "/api/v1/auth/logout-all",
            headers={"Authorization": f"Bearer {access}"},
        )

        # Old refresh token should be rejected
        client.cookies.set("warmpath_refresh_token", old_refresh)
        resp2 = await client.post("/api/v1/auth/refresh")
        assert resp2.status_code == 401
        detail = resp2.json().get("detail", "")
        assert (
            "revoked" in detail.lower()
            or "invalid" in detail.lower()
            or "token" in detail.lower()
        )

    async def test_login_after_logout_all_works(self, client: AsyncClient):
        """After logout-all, user can still log in and get valid tokens."""
        await _signup(client)
        resp = await _login(client)
        access = resp.json()["data"]["access_token"]

        # Decode old token to get its version
        from jose import jwt
        from app.config import settings

        old_payload = jwt.decode(access, settings.SECRET_KEY, algorithms=["HS256"])
        old_ver = old_payload["ver"]

        # logout-all
        await client.post(
            "/api/v1/auth/logout-all",
            headers={"Authorization": f"Bearer {access}"},
        )

        # Fresh login should work
        resp2 = await _login(client)
        assert resp2.status_code == 200
        new_token = resp2.json()["data"]["access_token"]

        # New token should have incremented token_version
        new_payload = jwt.decode(new_token, settings.SECRET_KEY, algorithms=["HS256"])
        assert new_payload["ver"] == old_ver + 1

        resp3 = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {new_token}"},
        )
        assert resp3.status_code == 200


# ---------------------------------------------------------------------------
# S1d: Logout
# ---------------------------------------------------------------------------


class TestLogout:
    async def test_logout_clears_cookie(self, client: AsyncClient):
        await _signup(client)
        resp = await client.post("/api/v1/auth/logout")
        assert resp.status_code == 200
        # Should have set-cookie that clears the refresh token
        cookie_headers = resp.headers.get_list("set-cookie")
        clear_headers = [h for h in cookie_headers if "warmpath_refresh_token" in h]
        assert len(clear_headers) == 1
        # The cookie value should be cleared (max-age=0 or empty value)
        header = clear_headers[0].lower()
        assert "max-age=0" in header or '=""' in header or '=""' in header


# ---------------------------------------------------------------------------
# S1e: Change password
# ---------------------------------------------------------------------------


class TestChangePassword:
    async def test_change_password_success(self, client: AsyncClient):
        resp = await _signup(client)
        token = resp.json()["data"]["access_token"]

        resp2 = await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": "Secret123", "new_password": "Newsecret456"},
        )
        assert resp2.status_code == 200
        new_token = resp2.json()["data"]["access_token"]
        assert new_token != token  # Fresh token with new version

        # Decode both tokens and verify the new token has incremented version
        from jose import jwt
        from app.config import settings

        old_payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        new_payload = jwt.decode(new_token, settings.SECRET_KEY, algorithms=["HS256"])
        assert new_payload["ver"] == old_payload["ver"] + 1
        assert new_payload["sub"] == old_payload["sub"]  # Same user
        assert new_payload["type"] == "access"

    async def test_change_password_wrong_old_password(self, client: AsyncClient):
        resp = await _signup(client)
        token = resp.json()["data"]["access_token"]

        resp2 = await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": "wrongpassword", "new_password": "Newsecret456"},
        )
        assert resp2.status_code == 401
        detail = resp2.json().get("detail", "")
        assert "password" in detail.lower()  # Error mentions password issue

    async def test_change_password_invalidates_old_tokens(self, client: AsyncClient):
        resp = await _signup(client)
        old_token = resp.json()["data"]["access_token"]

        resp2 = await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {old_token}"},
            json={"old_password": "Secret123", "new_password": "Newsecret456"},
        )
        assert resp2.status_code == 200

        # Old token should now be invalid (token_version incremented)
        resp3 = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {old_token}"},
        )
        assert resp3.status_code == 401
        assert "revoked" in resp3.json()["detail"].lower()

        # Verify token_version was incremented in DB
        import uuid as uuid_mod
        from tests.conftest import TestSessionLocal
        from app.models.user import User
        from jose import jwt
        from app.config import settings

        old_payload = jwt.decode(old_token, settings.SECRET_KEY, algorithms=["HS256"])
        async with TestSessionLocal() as session:
            result = await session.execute(
                select(User).where(User.id == uuid_mod.UUID(old_payload["sub"]))
            )
            user = result.scalar_one()
            assert user.token_version == old_payload["ver"] + 1

    async def test_change_password_can_login_with_new(self, client: AsyncClient):
        resp = await _signup(client)
        token = resp.json()["data"]["access_token"]

        change_resp = await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": "Secret123", "new_password": "Newsecret456"},
        )
        assert change_resp.status_code == 200

        # Login with new password
        resp2 = await _login(client, password="Newsecret456")
        assert resp2.status_code == 200
        assert "access_token" in resp2.json()["data"]

    async def test_change_password_old_password_fails(self, client: AsyncClient):
        resp = await _signup(client)
        token = resp.json()["data"]["access_token"]

        change_resp = await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": "Secret123", "new_password": "Newsecret456"},
        )
        assert change_resp.status_code == 200

        # Login with old password should fail
        resp2 = await _login(client, password="Secret123")
        assert resp2.status_code == 401


# ---------------------------------------------------------------------------
# S1f: Token type enforcement
# ---------------------------------------------------------------------------


class TestTokenTypeEnforcement:
    async def test_refresh_token_cannot_access_api(self, client: AsyncClient):
        """A refresh token should not be accepted as a Bearer token."""
        resp = await _signup(client)
        refresh = _get_refresh_cookie(resp)

        # Verify the refresh token actually is a refresh type
        from jose import jwt
        from app.config import settings

        refresh_payload = jwt.decode(refresh, settings.SECRET_KEY, algorithms=["HS256"])
        assert refresh_payload["type"] == "refresh"

        resp2 = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {refresh}"},
        )
        assert resp2.status_code == 401
        detail = resp2.json().get("detail", "")
        assert "access" in detail.lower() or "token" in detail.lower()


# ===========================================================================
# S2: CSV Upload Hardening
# ===========================================================================


def _make_csv(rows: list[list[str]]) -> bytes:
    """Build a CSV bytes from list of rows (first row = headers)."""
    buf = io.StringIO()
    for row in rows:
        buf.write(",".join(row) + "\n")
    return buf.getvalue().encode("utf-8")


async def _get_auth_token(client: AsyncClient, email: str = "csv@example.com") -> str:
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Secret123", "full_name": "CSV User"},
    )
    return resp.json()["data"]["access_token"]


class TestCSVFormulaInjection:
    def test_sanitize_equals(self):
        assert sanitize_cell("=SUM(A1:A10)") == "'=SUM(A1:A10)"

    def test_sanitize_plus(self):
        assert sanitize_cell("+cmd|' /C calc'!A0") == "'+cmd|' /C calc'!A0"

    def test_sanitize_minus(self):
        assert sanitize_cell("-1+1") == "'-1+1"

    def test_sanitize_at(self):
        assert sanitize_cell("@SUM(A1)") == "'@SUM(A1)"

    def test_sanitize_tab(self):
        assert sanitize_cell("\tcmd") == "'\tcmd"

    def test_sanitize_cr(self):
        assert sanitize_cell("\rcmd") == "'\rcmd"

    def test_sanitize_normal_unchanged(self):
        assert sanitize_cell("John Smith") == "John Smith"

    def test_sanitize_none(self):
        assert sanitize_cell(None) is None

    def test_sanitize_empty(self):
        assert sanitize_cell("") == ""

    async def test_formula_cells_sanitized_during_parse(self, client: AsyncClient):
        """Upload a CSV with formula-injection cells, verify they get sanitized."""
        token = await _get_auth_token(client)
        csv_bytes = _make_csv(
            [
                ["First Name", "Last Name", "Company", "Position", "Connected On"],
                ["=SUM(A1)", "Smith", "Acme", "Engineer", "01 Jan 2024"],
                ["John", "+cmd", "=HYPERLINK()", "Engineer", "01 Jan 2024"],
            ]
        )
        resp = await client.post(
            "/api/v1/contacts/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_bytes, "text/csv")},
        )
        assert resp.status_code == 201

        # Fetch contacts to verify sanitization happened
        resp2 = await client.get(
            "/api/v1/contacts",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.status_code == 200
        contacts = resp2.json()["data"]
        assert len(contacts) == 2

        # Find contact with sanitized first name
        names = {c["first_name"] for c in contacts}
        # "=SUM(A1)" should have been title-cased then sanitized: "=Sum(A1)" -> "'=Sum(A1)"
        assert any(n.startswith("'") for n in names)


class TestCSVFileSizeLimit:
    async def test_over_10mb_rejected(self, client: AsyncClient):
        token = await _get_auth_token(client)
        # Create a CSV that exceeds 10 MB
        header = "First Name,Last Name,Company,Position,Connected On\n"
        # Each row ~50 bytes, need ~200K rows for ~10MB, but we can be more efficient
        row = "A" * 200 + "," + "B" * 200 + ",Acme,Engineer,01 Jan 2024\n"
        big_csv = header.encode("utf-8") + (row.encode("utf-8") * 25_000)
        assert len(big_csv) > 10 * 1024 * 1024

        resp = await client.post(
            "/api/v1/contacts/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("big.csv", big_csv, "text/csv")},
        )
        assert resp.status_code == 413
        detail = resp.json().get("detail", "")
        assert "10" in detail or "size" in detail.lower()  # Mentions the limit


class TestCSVRowLimit:
    async def test_over_50k_rows_rejected(self, client: AsyncClient):
        token = await _get_auth_token(client)
        header = "First Name,Last Name,Company,Position,Connected On\n"
        row = "John,Smith,Acme,Engineer,01 Jan 2024\n"
        # 50,001 data rows + header
        csv_bytes = header.encode("utf-8") + (row.encode("utf-8") * 50_001)

        resp = await client.post(
            "/api/v1/contacts/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("big.csv", csv_bytes, "text/csv")},
        )
        assert resp.status_code == 400
        assert "50,000" in resp.json()["detail"]


class TestCSVContentType:
    async def test_wrong_content_type_rejected(self, client: AsyncClient):
        token = await _get_auth_token(client)
        csv_bytes = _make_csv(
            [
                ["First Name", "Last Name", "Company", "Position", "Connected On"],
                ["John", "Smith", "Acme", "Engineer", "01 Jan 2024"],
            ]
        )
        resp = await client.post(
            "/api/v1/contacts/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_bytes, "application/json")},
        )
        assert resp.status_code == 415
        detail = resp.json().get("detail", "")
        assert (
            "csv" in detail.lower() or "content" in detail.lower()
        )  # Explains the rejection

    async def test_text_csv_accepted(self, client: AsyncClient):
        token = await _get_auth_token(client)
        csv_bytes = _make_csv(
            [
                ["First Name", "Last Name", "Company", "Position", "Connected On"],
                ["John", "Smith", "Acme", "Engineer", "01 Jan 2024"],
            ]
        )
        resp = await client.post(
            "/api/v1/contacts/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_bytes, "text/csv")},
        )
        assert resp.status_code == 201

    async def test_octet_stream_accepted(self, client: AsyncClient):
        token = await _get_auth_token(client)
        csv_bytes = _make_csv(
            [
                ["First Name", "Last Name", "Company", "Position", "Connected On"],
                ["Jane", "Doe", "BigCo", "PM", "01 Jan 2024"],
            ]
        )
        resp = await client.post(
            "/api/v1/contacts/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 201


class TestCSVEncoding:
    async def test_non_utf8_rejected(self, client: AsyncClient):
        token = await _get_auth_token(client)
        # Create bytes that are not valid UTF-8
        bad_bytes = b"First Name,Last Name\nJos\xe9,Garc\xeda\n"
        resp = await client.post(
            "/api/v1/contacts/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", bad_bytes, "text/csv")},
        )
        assert resp.status_code == 400
        assert "UTF-8" in resp.json()["detail"]


# ===========================================================================
# S3: Security Headers Middleware
# ===========================================================================


class TestSecurityHeaders:
    async def test_x_content_type_options(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    async def test_x_frame_options(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.headers.get("x-frame-options") == "DENY"

    async def test_csp(self, client: AsyncClient):
        resp = await client.get("/health")
        csp = resp.headers.get("content-security-policy")
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp

    async def test_referrer_policy(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    async def test_permissions_policy(self, client: AsyncClient):
        resp = await client.get("/health")
        assert (
            resp.headers.get("permissions-policy")
            == "camera=(), microphone=(), geolocation=()"
        )

    async def test_headers_on_api_endpoints(self, client: AsyncClient):
        """Security headers should be on ALL responses, not just health — including error responses."""
        resp = await client.get("/api/v1/auth/me")
        # Even though this returns 403/401, headers should still be present
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
        # Also verify CSP, referrer-policy, and permissions-policy on error responses
        assert "default-src 'self'" in resp.headers.get("content-security-policy", "")
        assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
        assert (
            resp.headers.get("permissions-policy")
            == "camera=(), microphone=(), geolocation=()"
        )

    async def test_no_hsts_by_default(self, client: AsyncClient):
        """HSTS should NOT be present when SECURE_HEADERS is false (default)."""
        resp = await client.get("/health")
        assert "strict-transport-security" not in resp.headers

    async def test_hsts_when_enabled(self, client: AsyncClient):
        """HSTS should appear when SECURE_HEADERS=true."""
        from app.config import settings

        original = settings.SECURE_HEADERS
        settings.SECURE_HEADERS = True
        try:
            resp = await client.get("/health")
            hsts = resp.headers.get("strict-transport-security")
            assert hsts is not None
            assert "max-age=31536000" in hsts
            assert "includeSubDomains" in hsts
        finally:
            settings.SECURE_HEADERS = original


# ===========================================================================
# S6a: Account Lockout
# ===========================================================================


class TestAccountLockout:
    async def test_5_failures_locks_account(self, client: AsyncClient):
        """After 5 failed logins, the 6th returns 429."""
        await _signup(client, email="lock@example.com")

        # Fail 5 times
        for _ in range(5):
            resp = await _login(client, email="lock@example.com", password="wrong")
            assert resp.status_code == 401

        # 6th attempt should be locked
        resp = await _login(client, email="lock@example.com", password="wrong")
        assert resp.status_code == 429
        assert "locked" in resp.json()["detail"].lower()

    async def test_lockout_blocks_correct_password(self, client: AsyncClient):
        """Even the correct password is rejected during lockout."""
        await _signup(client, email="lock2@example.com")

        for _ in range(5):
            await _login(client, email="lock2@example.com", password="wrong")

        # Correct password during lockout → still 429
        resp = await _login(client, email="lock2@example.com", password="Secret123")
        assert resp.status_code == 429
        assert "locked" in resp.json()["detail"].lower()
        # Verify no token is returned during lockout
        assert "access_token" not in resp.json().get("data", {})

    async def test_lockout_expires(self, client: AsyncClient):
        """Lockout expires after the window passes — simulate by resetting locked_until."""
        await _signup(client, email="lock3@example.com")

        for _ in range(5):
            await _login(client, email="lock3@example.com", password="wrong")

        # Simulate lockout expiry by clearing locked_until via DB
        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            from app.models.user import User

            result = await session.execute(
                select(User).where(User.email == "lock3@example.com")
            )
            user = result.scalar_one()
            user.locked_until = None
            user.failed_login_attempts = 0
            await session.commit()

        # Should be able to log in now
        resp = await _login(client, email="lock3@example.com", password="Secret123")
        assert resp.status_code == 200
        assert "access_token" in resp.json()["data"]

    async def test_successful_login_resets_counter(self, client: AsyncClient):
        """Successful login after failures resets the counter."""
        await _signup(client, email="lock4@example.com")

        # Fail 3 times (not enough to lock)
        for _ in range(3):
            await _login(client, email="lock4@example.com", password="wrong")

        # Successful login
        resp = await _login(client, email="lock4@example.com", password="Secret123")
        assert resp.status_code == 200

        # Fail 3 more times (counter was reset, so still under threshold)
        for _ in range(3):
            await _login(client, email="lock4@example.com", password="wrong")

        # Should NOT be locked (only 3 since reset, not 5)
        resp = await _login(client, email="lock4@example.com", password="wrong")
        assert resp.status_code == 401  # fails but not locked


# ===========================================================================
# S5: Email Verification
# ===========================================================================


class TestEmailVerification:
    async def test_signup_creates_verification_token(self, client: AsyncClient):
        """Signup should create a verification token on the user."""
        await _signup(client, email="verify@example.com")

        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            from app.models.user import User

            result = await session.execute(
                select(User).where(User.email == "verify@example.com")
            )
            user = result.scalar_one()
            assert user.email_verification_token is not None
            assert user.email_verification_sent_at is not None
            assert user.email_verified is False

    async def test_verify_email_endpoint(self, client: AsyncClient):
        """GET /verify-email with valid token marks email as verified."""
        await _signup(client, email="verify2@example.com")

        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            from app.models.user import User

            result = await session.execute(
                select(User).where(User.email == "verify2@example.com")
            )
            user = result.scalar_one()
            token = user.email_verification_token

        resp = await client.get(f"/api/v1/auth/verify-email?token={token}")
        assert resp.status_code == 200
        assert "verified" in resp.json()["data"]["message"].lower()

        # Confirm user is now verified in DB
        async with TestSessionLocal() as session:
            result = await session.execute(
                select(User).where(User.email == "verify2@example.com")
            )
            user = result.scalar_one()
            assert user.email_verified is True
            assert user.email_verification_token is None

    async def test_verify_email_invalid_token(self, client: AsyncClient):
        """Invalid token returns 400 with descriptive error."""
        resp = await client.get("/api/v1/auth/verify-email?token=bogus-token-xyz")
        assert resp.status_code == 400
        detail = resp.json().get("detail", "")
        assert "token" in detail.lower() or "invalid" in detail.lower()

    async def test_verify_email_expired_token(self, client: AsyncClient):
        """Token older than 24 hours is rejected."""
        await _signup(client, email="verify3@example.com")

        from datetime import datetime, timedelta, timezone

        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            from app.models.user import User

            result = await session.execute(
                select(User).where(User.email == "verify3@example.com")
            )
            user = result.scalar_one()
            token = user.email_verification_token
            # Set sent_at to 25 hours ago
            user.email_verification_sent_at = datetime.now(timezone.utc) - timedelta(
                hours=25
            )
            await session.commit()

        resp = await client.get(f"/api/v1/auth/verify-email?token={token}")
        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"].lower()

    async def test_unverified_blocked_from_marketplace_search(
        self, client: AsyncClient
    ):
        """Unverified user cannot access marketplace search."""
        resp = await _signup(client, email="unver@example.com")
        token = resp.json()["data"]["access_token"]

        resp2 = await client.post(
            "/api/v1/marketplace/search",
            headers={"Authorization": f"Bearer {token}"},
            json={"company_names": ["Stripe"]},
        )
        assert resp2.status_code == 403
        assert "verify" in resp2.json()["detail"].lower()

    async def test_unverified_can_upload_csv(self, client: AsyncClient):
        """Unverified user CAN upload CSV (own-network feature)."""
        resp = await _signup(client, email="unver2@example.com")
        token = resp.json()["data"]["access_token"]

        csv_bytes = b"First Name,Last Name,Company,Position,Connected On\nJohn,Doe,Acme,Engineer,01 Jan 2024\n"
        resp2 = await client.post(
            "/api/v1/contacts/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_bytes, "text/csv")},
        )
        assert resp2.status_code == 201
        assert "status" in resp2.json()["data"]

    async def test_unverified_can_view_own_contacts(self, client: AsyncClient):
        """Unverified user CAN view their own contacts."""
        resp = await _signup(client, email="unver3@example.com")
        token = resp.json()["data"]["access_token"]

        resp2 = await client.get(
            "/api/v1/contacts",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.status_code == 200

    async def test_resend_verification(self, client: AsyncClient):
        """Resend verification endpoint works and updates token."""
        resp = await _signup(client, email="resend@example.com")
        token = resp.json()["data"]["access_token"]

        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            from app.models.user import User

            result = await session.execute(
                select(User).where(User.email == "resend@example.com")
            )
            user = result.scalar_one()
            old_token = user.email_verification_token
            # Clear sent_at so rate limit doesn't block
            user.email_verification_sent_at = None
            await session.commit()

        resp2 = await client.post(
            "/api/v1/auth/resend-verification",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.status_code == 200

        async with TestSessionLocal() as session:
            result = await session.execute(
                select(User).where(User.email == "resend@example.com")
            )
            user = result.scalar_one()
            assert user.email_verification_token is not None
            assert user.email_verification_token != old_token

    async def test_resend_rate_limited(self, client: AsyncClient):
        """Resend within 5 minutes returns 429."""
        resp = await _signup(client, email="resend2@example.com")
        token = resp.json()["data"]["access_token"]

        # Immediately try to resend (sent_at was just set by signup)
        resp2 = await client.post(
            "/api/v1/auth/resend-verification",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.status_code == 429


# ===========================================================================
# S6b: Audit Log
# ===========================================================================


class TestAuditLog:
    async def test_login_creates_audit_entry(self, client: AsyncClient):
        """Successful login writes to audit_logs with user_id and timestamp."""
        await _signup(client, email="audit@example.com")
        await _login(client, email="audit@example.com")

        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            result = await session.execute(
                select(AuditLog).where(AuditLog.action == "login_success")
            )
            entries = list(result.scalars())
            assert len(entries) >= 1
            entry = entries[-1]
            assert entry.user_id is not None  # Must be tied to a user
            assert entry.created_at is not None

    async def test_failed_login_creates_audit_entry(self, client: AsyncClient):
        """Failed login writes to audit_logs with user_id."""
        await _signup(client, email="audit2@example.com")
        await _login(client, email="audit2@example.com", password="wrong")

        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            result = await session.execute(
                select(AuditLog).where(AuditLog.action == "login_failure")
            )
            entries = list(result.scalars())
            assert len(entries) >= 1
            entry = entries[-1]
            assert entry.user_id is not None  # Must reference the failed user
            assert entry.created_at is not None

    async def test_lockout_creates_audit_entry(self, client: AsyncClient):
        """Account lockout writes to audit_logs with user_id."""
        await _signup(client, email="audit3@example.com")
        for _ in range(5):
            await _login(client, email="audit3@example.com", password="wrong")

        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            result = await session.execute(
                select(AuditLog).where(AuditLog.action == "login_lockout")
            )
            entries = list(result.scalars())
            assert len(entries) >= 1
            entry = entries[-1]
            assert entry.user_id is not None  # Lockout must be tied to a user
            assert entry.created_at is not None

    async def test_password_change_creates_audit_entry(self, client: AsyncClient):
        """Password change writes to audit_logs."""
        resp = await _signup(client, email="audit4@example.com")
        token = resp.json()["data"]["access_token"]

        await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": "Secret123", "new_password": "Newpass456"},
        )

        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            result = await session.execute(
                select(AuditLog).where(AuditLog.action == "password_change")
            )
            entries = list(result.scalars())
            assert len(entries) >= 1

    async def test_email_verified_creates_audit_entry(self, client: AsyncClient):
        """Email verification writes to audit_logs."""
        await _signup(client, email="audit5@example.com")

        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            from app.models.user import User

            result = await session.execute(
                select(User).where(User.email == "audit5@example.com")
            )
            user = result.scalar_one()
            token = user.email_verification_token

        await client.get(f"/api/v1/auth/verify-email?token={token}")

        async with TestSessionLocal() as session:
            result = await session.execute(
                select(AuditLog).where(AuditLog.action == "email_verified")
            )
            entries = list(result.scalars())
            assert len(entries) >= 1

    async def test_audit_log_append_only(self, client: AsyncClient):
        """Audit log entries cannot be updated or deleted via SQLAlchemy.

        We verify this by checking the table has no updated_at or deleted_at columns.
        """
        from app.models.audit import AuditLog

        column_names = {c.name for c in AuditLog.__table__.columns}
        assert "updated_at" not in column_names
        assert "deleted_at" not in column_names


# ===========================================================================
# Stripe Webhook Verification
# ===========================================================================


class TestStripeWebhook:
    def _make_signature(self, payload: bytes, secret: str) -> str:
        """Build a valid Stripe-Signature header."""
        ts = str(int(time.time()))
        signed_payload = f"{ts}.".encode() + payload
        sig = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        return f"t={ts},v1={sig}"

    async def test_webhook_accepted_without_secret(self, client: AsyncClient):
        """When STRIPE_WEBHOOK_SECRET is empty, webhooks are accepted."""
        from app.config import settings

        original = settings.STRIPE_WEBHOOK_SECRET
        settings.STRIPE_WEBHOOK_SECRET = ""
        try:
            resp = await client.post(
                "/api/v1/webhooks/stripe",
                content=json.dumps({"type": "checkout.session.completed"}),
                headers={"content-type": "application/json"},
            )
            assert resp.status_code == 200
            assert resp.json()["data"]["received"] is True
        finally:
            settings.STRIPE_WEBHOOK_SECRET = original

    async def test_webhook_valid_signatu[RESEND_KEY_REDACTED](self, client: AsyncClient):
        """Valid signature is accepted."""
        from app.config import settings

        secret = "[STRIPE_WEBHOOK_SECRET_REDACTED]"
        original = settings.STRIPE_WEBHOOK_SECRET
        settings.STRIPE_WEBHOOK_SECRET = secret
        try:
            payload = json.dumps({"type": "invoice.paid"}).encode()
            sig = self._make_signature(payload, secret)
            resp = await client.post(
                "/api/v1/webhooks/stripe",
                content=payload,
                headers={
                    "content-type": "application/json",
                    "stripe-signature": sig,
                },
            )
            assert resp.status_code == 200
            assert resp.json()["data"]["type"] == "invoice.paid"
        finally:
            settings.STRIPE_WEBHOOK_SECRET = original

    async def test_webhook_invalid_signatu[RESEND_KEY_REDACTED](self, client: AsyncClient):
        """Invalid signature returns 400 with an error detail."""
        from app.config import settings

        original = settings.STRIPE_WEBHOOK_SECRET
        settings.STRIPE_WEBHOOK_SECRET = "[STRIPE_WEBHOOK_SECRET_REDACTED]"
        try:
            payload = json.dumps({"type": "checkout.session.completed"}).encode()
            resp = await client.post(
                "/api/v1/webhooks/stripe",
                content=payload,
                headers={
                    "content-type": "application/json",
                    "stripe-signature": "t=123,v1=invalidsignature",
                },
            )
            assert resp.status_code == 400
            detail = resp.json().get("detail", "")
            assert "signature" in detail.lower() or "invalid" in detail.lower()
        finally:
            settings.STRIPE_WEBHOOK_SECRET = original

    async def test_webhook_missing_signatu[RESEND_KEY_REDACTED](self, client: AsyncClient):
        """Missing Stripe-Signature header returns 400 when secret is set."""
        from app.config import settings

        original = settings.STRIPE_WEBHOOK_SECRET
        settings.STRIPE_WEBHOOK_SECRET = "[STRIPE_WEBHOOK_SECRET_REDACTED]"
        try:
            resp = await client.post(
                "/api/v1/webhooks/stripe",
                content=json.dumps({"type": "test"}).encode(),
                headers={"content-type": "application/json"},
            )
            assert resp.status_code == 400
            assert "Missing" in resp.json()["detail"]
        finally:
            settings.STRIPE_WEBHOOK_SECRET = original


# ===========================================================================
# Password Strength Validation
# ===========================================================================


class TestPasswordStrength:
    def test_too_short(self):
        from app.utils.security import validate_password_strength

        try:
            validate_password_strength("Ab1")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "8 characters" in str(e)

    def test_no_uppercase(self):
        from app.utils.security import validate_password_strength

        try:
            validate_password_strength("abcdefg1")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "uppercase" in str(e)

    def test_no_lowercase(self):
        from app.utils.security import validate_password_strength

        try:
            validate_password_strength("ABCDEFG1")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "lowercase" in str(e)

    def test_no_number(self):
        from app.utils.security import validate_password_strength

        try:
            validate_password_strength("Abcdefgh")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "number" in str(e)

    def test_valid_password(self):
        from app.utils.security import validate_password_strength

        result = validate_password_strength("Secret123")  # Should not raise
        assert result is None

    async def test_signup_weak_password_rejected(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/signup",
            json={"email": "weak@test.com", "password": "weak", "full_name": "Weak"},
        )
        assert resp.status_code == 422
        assert "Password must contain" in resp.json()["detail"]

    async def test_change_password_weak_rejected(self, client: AsyncClient):
        resp = await _signup(client, email="chgweak@test.com")
        token = resp.json()["data"]["access_token"]

        resp2 = await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": "Secret123", "new_password": "weak"},
        )
        assert resp2.status_code == 422
        assert "Password must contain" in resp2.json()["detail"]


# ===========================================================================
# Forgot / Reset Password
# ===========================================================================


class TestForgotPassword:
    async def test_creates_token(self, client: AsyncClient):
        await _signup(client, email="forgot@test.com")

        resp = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "forgot@test.com"},
        )
        assert resp.status_code == 200

        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            from app.models.user import User

            result = await session.execute(
                select(User).where(User.email == "forgot@test.com")
            )
            user = result.scalar_one()
            assert user.password_reset_token is not None
            assert user.password_reset_sent_at is not None

    async def test_unknown_email_succeeds(self, client: AsyncClient):
        """No email enumeration — always returns success."""
        resp = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "nobody@nowhere.com"},
        )
        assert resp.status_code == 200

    async def test_rate_limited_no_enumeration(self, client: AsyncClient):
        """Rate-limited requests return 200 to prevent email enumeration."""
        await _signup(client, email="ratelimit@test.com")

        resp1 = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "ratelimit@test.com"},
        )
        assert resp1.status_code == 200

        # Second request within rate window still returns 200
        # (silently skips sending to prevent leaking account existence)
        resp2 = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "ratelimit@test.com"},
        )
        assert resp2.status_code == 200
        assert "If that email" in resp2.json()["data"]["message"]


class TestResetPassword:
    async def test_valid_token(self, client: AsyncClient):
        await _signup(client, email="reset@test.com")

        await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "reset@test.com"},
        )

        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            from app.models.user import User

            result = await session.execute(
                select(User).where(User.email == "reset@test.com")
            )
            user = result.scalar_one()
            token = user.password_reset_token
            old_version = user.token_version

        resp = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": "NewPass789"},
        )
        assert resp.status_code == 200

        # Verify password was updated and token_version bumped
        async with TestSessionLocal() as session:
            result = await session.execute(
                select(User).where(User.email == "reset@test.com")
            )
            user = result.scalar_one()
            assert user.password_reset_token is None
            assert user.token_version == old_version + 1

        # Login with new password works
        resp2 = await _login(client, email="reset@test.com", password="NewPass789")
        assert resp2.status_code == 200

    async def test_expired_token(self, client: AsyncClient):
        await _signup(client, email="expired@test.com")
        await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "expired@test.com"},
        )

        from datetime import datetime, timedelta, timezone

        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            from app.models.user import User

            result = await session.execute(
                select(User).where(User.email == "expired@test.com")
            )
            user = result.scalar_one()
            token = user.password_reset_token
            user.password_reset_sent_at = datetime.now(timezone.utc) - timedelta(
                hours=2
            )
            await session.commit()

        resp = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": "NewPass789"},
        )
        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"].lower()

    async def test_invalid_token(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": "bogus-token", "new_password": "NewPass789"},
        )
        assert resp.status_code == 400

    async def test_weak_password(self, client: AsyncClient):
        await _signup(client, email="resetweak@test.com")
        await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "resetweak@test.com"},
        )

        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            from app.models.user import User

            result = await session.execute(
                select(User).where(User.email == "resetweak@test.com")
            )
            user = result.scalar_one()
            token = user.password_reset_token

        resp = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": "weak"},
        )
        assert resp.status_code == 422
        assert "Password must contain" in resp.json()["detail"]


# ===========================================================================
# Account Deletion
# ===========================================================================


async def _signup_and_get_token(
    client: AsyncClient, email: str = "del@example.com"
) -> str:
    """Signup and return access token."""
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Secret123", "full_name": "Del User"},
    )
    assert resp.status_code == 201
    return resp.json()["data"]["access_token"]


class TestDeleteAccount:
    async def test_delete_account_success(self, client: AsyncClient):
        """Password confirmed, user removed from DB."""
        token = await _signup_and_get_token(client, "del1@example.com")

        resp = await client.post(
            "/api/v1/auth/delete-account",
            headers={"Authorization": f"Bearer {token}"},
            json={"password": "Secret123", "confirm_deletion": True},
        )
        assert resp.status_code == 200
        assert "deleted" in resp.json()["data"]["message"].lower()

        # User should not exist anymore
        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            from app.models.user import User

            result = await session.execute(
                select(User).where(User.email == "del1@example.com")
            )
            assert result.scalar_one_or_none() is None

    async def test_delete_account_wrong_password(self, client: AsyncClient):
        """Wrong password returns 401 and does not delete the account."""
        token = await _signup_and_get_token(client, "del2@example.com")

        resp = await client.post(
            "/api/v1/auth/delete-account",
            headers={"Authorization": f"Bearer {token}"},
            json={"password": "WrongPass1", "confirm_deletion": True},
        )
        assert resp.status_code == 401

        # Verify account still exists after failed deletion attempt
        resp2 = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["data"]["email"] == "del2@example.com"

    async def test_delete_account_without_confirmation(self, client: AsyncClient):
        """confirm_deletion=false returns 422 and does not delete the account."""
        token = await _signup_and_get_token(client, "del3@example.com")

        resp = await client.post(
            "/api/v1/auth/delete-account",
            headers={"Authorization": f"Bearer {token}"},
            json={"password": "Secret123", "confirm_deletion": False},
        )
        assert resp.status_code == 422

        # Verify account still exists
        resp2 = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.status_code == 200

    async def test_delete_account_creates_audit_entry(self, client: AsyncClient):
        """audit_logs has action='account_deleted' after deletion."""
        token = await _signup_and_get_token(client, "del4@example.com")

        await client.post(
            "/api/v1/auth/delete-account",
            headers={"Authorization": f"Bearer {token}"},
            json={"password": "Secret123", "confirm_deletion": True},
        )

        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            result = await session.execute(
                select(AuditLog).where(AuditLog.action == "account_deleted")
            )
            entries = list(result.scalars())
            assert len(entries) >= 1
            # user_id should be SET NULL (user was deleted)
            assert any(e.metadata_.get("email") == "del4@example.com" for e in entries)

    async def test_delete_account_cascades_contacts(self, client: AsyncClient):
        """User with contacts can be deleted; user row is removed.

        Note: DB-level CASCADE (ondelete='CASCADE') deletes child rows in
        production PostgreSQL. SQLite in tests doesn't enforce FK CASCADE
        by default, so we verify the user row is gone and the FK definitions
        are correct in the model layer.
        """
        token = await _signup_and_get_token(client, "del5@example.com")

        # Upload a CSV to create contacts
        csv_bytes = b"First Name,Last Name,Company,Position,Connected On\nJohn,Doe,Acme,Engineer,01 Jan 2024\n"
        resp = await client.post(
            "/api/v1/contacts/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_bytes, "text/csv")},
        )
        assert resp.status_code == 201

        # Verify contact exists before deletion
        resp2 = await client.get(
            "/api/v1/contacts",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert len(resp2.json()["data"]) > 0

        # Delete account — should succeed even with child records
        resp3 = await client.post(
            "/api/v1/auth/delete-account",
            headers={"Authorization": f"Bearer {token}"},
            json={"password": "Secret123", "confirm_deletion": True},
        )
        assert resp3.status_code == 200

        # User should be gone from DB
        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            from app.models.user import User

            result = await session.execute(
                select(User).where(User.email == "del5@example.com")
            )
            assert result.scalar_one_or_none() is None

        # Verify FK definitions are set up for CASCADE
        from app.models.contact import Contact

        fk = next(
            fk
            for fk in Contact.__table__.foreign_keys
            if fk.column.name == "id" and fk.column.table.name == "users"
        )
        assert fk.ondelete == "CASCADE"

    async def test_delete_account_adds_suppression_entry(self, client: AsyncClient):
        """suppression_list gets an email hash with reason='account_deleted'."""
        token = await _signup_and_get_token(client, "del6@example.com")

        await client.post(
            "/api/v1/auth/delete-account",
            headers={"Authorization": f"Bearer {token}"},
            json={"password": "Secret123", "confirm_deletion": True},
        )

        import hashlib

        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            from app.models.privacy import SuppressionList

            email_hash = hashlib.sha256("del6@example.com".encode()).hexdigest()
            result = await session.execute(
                select(SuppressionList).where(
                    SuppressionList.email_hash == email_hash,
                    SuppressionList.reason == "account_deleted",
                )
            )
            entry = result.scalar_one_or_none()
            assert entry is not None

    async def test_reregistration_after_deletion_no_welcome_bonus(
        self, client: AsyncClient
    ):
        """Signup after delete creates account but awards 0 credits."""
        token = await _signup_and_get_token(client, "del7@example.com")

        # Delete account
        await client.post(
            "/api/v1/auth/delete-account",
            headers={"Authorization": f"Bearer {token}"},
            json={"password": "Secret123", "confirm_deletion": True},
        )

        # Re-register with same email
        resp = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "del7@example.com",
                "password": "Secret123",
                "full_name": "Del User 2",
            },
        )
        assert resp.status_code == 201
        new_token = resp.json()["data"]["access_token"]

        # Check credits balance — should be 0 (no welcome bonus)
        resp2 = await client.get(
            "/api/v1/credits/balance",
            headers={"Authorization": f"Bearer {new_token}"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["data"]["balance"] == 0

    async def test_delete_account_blocked_if_paid_plan(self, client: AsyncClient):
        """400 if plan_tier != 'free'."""
        token = await _signup_and_get_token(client, "del8@example.com")

        # Set plan_tier to a paid plan
        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            from app.models.user import User

            result = await session.execute(
                select(User).where(User.email == "del8@example.com")
            )
            user = result.scalar_one()
            user.plan_tier = "pro"
            await session.commit()

        resp = await client.post(
            "/api/v1/auth/delete-account",
            headers={"Authorization": f"Bearer {token}"},
            json={"password": "Secret123", "confirm_deletion": True},
        )
        assert resp.status_code == 400
        assert "subscription" in resp.json()["detail"].lower()
