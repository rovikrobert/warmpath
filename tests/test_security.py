"""Tests for CSV hardening, security headers, Stripe webhook verification,
password strength validation, and audit log structure.

Note: Auth-specific security tests (JWT refresh, token versioning, lockout,
email verification, change password, forgot/reset password, account deletion)
were removed during Clerk migration — those flows are now handled by Clerk.
"""

import hashlib
import hmac
import io
import json
import time

from httpx import AsyncClient
from app.models.audit import AuditLog
from app.services.csv_parser import sanitize_cell
from tests.conftest import TestSessionLocal, create_test_user_in_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_csv(rows: list[list[str]]) -> bytes:
    """Build a CSV bytes from list of rows (first row = headers)."""
    buf = io.StringIO()
    for row in rows:
        buf.write(",".join(row) + "\n")
    return buf.getvalue().encode("utf-8")


async def _get_auth_token(
    client: AsyncClient, email: str = "csv@example.com"
) -> str:
    """Create a test user and return auth token."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email=email, full_name="CSV User"
        )
    return headers["Authorization"].split(" ")[1]


# ===========================================================================
# S2: CSV Upload Hardening
# ===========================================================================


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
# Audit Log Structure
# ===========================================================================


class TestAuditLogStructure:
    async def test_audit_log_append_only(self, client: AsyncClient):
        """Audit log entries cannot be updated or deleted via SQLAlchemy.

        We verify this by checking the table has no updated_at or deleted_at columns.
        """
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


