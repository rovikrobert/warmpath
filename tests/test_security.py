"""Tests for S1-S3: JWT refresh tokens, CSV hardening, security headers."""

import io

from httpx import AsyncClient

from app.services.csv_parser import sanitize_cell


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _signup(client: AsyncClient, email: str = "sec@example.com") -> dict:
    """Signup and return full response (including cookies)."""
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "secret123", "full_name": "Sec User"},
    )
    assert resp.status_code == 201
    return resp


async def _login(
    client: AsyncClient, email: str = "sec@example.com", password: str = "secret123"
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
        refresh = _get_refresh_cookie(resp)
        assert refresh is not None

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

    async def test_refresh_with_access_token_rejects(self, client: AsyncClient):
        """An access token should not work as a refresh token."""
        resp = await _signup(client)
        access = resp.json()["data"]["access_token"]

        client.cookies.set("warmpath_refresh_token", access)
        resp2 = await client.post("/api/v1/auth/refresh")
        assert resp2.status_code == 401

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

    async def test_login_after_logout_all_works(self, client: AsyncClient):
        """After logout-all, user can still log in and get valid tokens."""
        await _signup(client)
        resp = await _login(client)
        access = resp.json()["data"]["access_token"]

        # logout-all
        await client.post(
            "/api/v1/auth/logout-all",
            headers={"Authorization": f"Bearer {access}"},
        )

        # Fresh login should work
        resp2 = await _login(client)
        assert resp2.status_code == 200
        new_token = resp2.json()["data"]["access_token"]

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
            json={"old_password": "secret123", "new_password": "newsecret456"},
        )
        assert resp2.status_code == 200
        new_token = resp2.json()["data"]["access_token"]
        assert new_token != token  # Fresh token with new version

    async def test_change_password_wrong_old_password(self, client: AsyncClient):
        resp = await _signup(client)
        token = resp.json()["data"]["access_token"]

        resp2 = await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": "wrongpassword", "new_password": "newsecret456"},
        )
        assert resp2.status_code == 401

    async def test_change_password_invalidates_old_tokens(self, client: AsyncClient):
        resp = await _signup(client)
        old_token = resp.json()["data"]["access_token"]

        resp2 = await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {old_token}"},
            json={"old_password": "secret123", "new_password": "newsecret456"},
        )
        assert resp2.status_code == 200

        # Old token should now be invalid (token_version incremented)
        resp3 = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {old_token}"},
        )
        assert resp3.status_code == 401

    async def test_change_password_can_login_with_new(self, client: AsyncClient):
        resp = await _signup(client)
        token = resp.json()["data"]["access_token"]

        await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": "secret123", "new_password": "newsecret456"},
        )

        # Login with new password
        resp2 = await _login(client, password="newsecret456")
        assert resp2.status_code == 200

    async def test_change_password_old_password_fails(self, client: AsyncClient):
        resp = await _signup(client)
        token = resp.json()["data"]["access_token"]

        await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": "secret123", "new_password": "newsecret456"},
        )

        # Login with old password should fail
        resp2 = await _login(client, password="secret123")
        assert resp2.status_code == 401


# ---------------------------------------------------------------------------
# S1f: Token type enforcement
# ---------------------------------------------------------------------------


class TestTokenTypeEnforcement:
    async def test_refresh_token_cannot_access_api(self, client: AsyncClient):
        """A refresh token should not be accepted as a Bearer token."""
        resp = await _signup(client)
        refresh = _get_refresh_cookie(resp)

        resp2 = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {refresh}"},
        )
        assert resp2.status_code == 401


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
        json={"email": email, "password": "secret123", "full_name": "CSV User"},
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
        assert resp.headers.get("content-security-policy") == "default-src 'self'"

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
        """Security headers should be on ALL responses, not just health."""
        resp = await client.get("/api/v1/auth/me")
        # Even though this returns 403/401, headers should still be present
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"

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
