"""Error-path tests for 6 API modules: companies, contacts, jobs, matches,
preferences, webhooks.

Covers 401 Unauthorized, 404 Not Found, and 422 Invalid Input for each module.
"""

import uuid

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_UUID = "00000000-0000-0000-0000-000000000000"

_user_counter = 0


async def _auth_headers(client: AsyncClient) -> dict:
    """Sign up a unique user and return Authorization headers."""
    global _user_counter
    _user_counter += 1
    email = f"error-test-{_user_counter}@example.com"
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "TestPass123!",
            "full_name": "Error Tester",
        },
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "TestPass123!"},
    )
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# 1. COMPANIES — /api/v1/companies
# ===========================================================================


class TestCompaniesErrors:
    """Error paths for the companies module."""

    @pytest.mark.asyncio
    async def test_list_companies_no_auth(self, client: AsyncClient):
        """GET /api/v1/companies without token returns 401."""
        resp = await client.get("/api/v1/companies")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_companies_bad_token(self, client: AsyncClient):
        """GET /api/v1/companies with invalid token returns 401."""
        headers = {"Authorization": "Bearer totally-invalid-token"}
        resp = await client.get("/api/v1/companies", headers=headers)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_companies_invalid_page_param(self, client: AsyncClient):
        """GET /api/v1/companies?page=0 violates ge=1, returns 422."""
        headers = await _auth_headers(client)
        resp = await client.get("/api/v1/companies?page=0", headers=headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list_companies_invalid_per_page_param(self, client: AsyncClient):
        """GET /api/v1/companies?per_page=999 violates le=100, returns 422."""
        headers = await _auth_headers(client)
        resp = await client.get("/api/v1/companies?per_page=999", headers=headers)
        assert resp.status_code == 422


# ===========================================================================
# 2. CONTACTS — /api/v1/contacts
# ===========================================================================


class TestContactsErrors:
    """Error paths for the contacts module."""

    @pytest.mark.asyncio
    async def test_get_contact_no_auth(self, client: AsyncClient):
        """GET /api/v1/contacts/{id} without token returns 401."""
        resp = await client.get(f"/api/v1/contacts/{FAKE_UUID}")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_contact_not_found(self, client: AsyncClient):
        """GET /api/v1/contacts/{id} for nonexistent contact returns 404."""
        headers = await _auth_headers(client)
        resp = await client.get(f"/api/v1/contacts/{FAKE_UUID}", headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_contact_not_found(self, client: AsyncClient):
        """PATCH /api/v1/contacts/{id} for nonexistent contact returns 404."""
        headers = await _auth_headers(client)
        resp = await client.patch(
            f"/api/v1/contacts/{FAKE_UUID}",
            headers=headers,
            json={"relationship_type": "friend"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_contact_not_found(self, client: AsyncClient):
        """DELETE /api/v1/contacts/{id} for nonexistent contact returns 404."""
        headers = await _auth_headers(client)
        resp = await client.delete(f"/api/v1/contacts/{FAKE_UUID}", headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_manual_contact_invalid_payload(self, client: AsyncClient):
        """POST /api/v1/contacts/manual with missing required fields returns 422."""
        headers = await _auth_headers(client)
        # ManualContactCreate requires first_name and last_name
        resp = await client.post(
            "/api/v1/contacts/manual",
            headers=headers,
            json={"company": "Acme"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_upload_status_not_found(self, client: AsyncClient):
        """GET /api/v1/contacts/uploads/{id} for nonexistent upload returns 404."""
        headers = await _auth_headers(client)
        resp = await client.get(
            f"/api/v1/contacts/uploads/{FAKE_UUID}", headers=headers
        )
        assert resp.status_code == 404


# ===========================================================================
# 3. JOBS — /api/v1/jobs
# ===========================================================================


class TestJobsErrors:
    """Error paths for the jobs module."""

    @pytest.mark.asyncio
    async def test_scan_jobs_no_auth(self, client: AsyncClient):
        """GET /api/v1/jobs/scan/{company} without token returns 401."""
        resp = await client.get("/api/v1/jobs/scan/google")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_openings_no_auth(self, client: AsyncClient):
        """GET /api/v1/jobs/openings without token returns 401."""
        resp = await client.get("/api/v1/jobs/openings")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_scan_unknown_company_not_found(self, client: AsyncClient):
        """GET /api/v1/jobs/scan/{company} for unknown company returns 404."""
        headers = await _auth_headers(client)
        resp = await client.get(
            "/api/v1/jobs/scan/zzz_nonexistent_company_xyz_999",
            headers=headers,
        )
        assert resp.status_code == 404


# ===========================================================================
# 4. MATCHES — /api/v1/matches
# ===========================================================================


class TestMatchesErrors:
    """Error paths for the matches (intro) module."""

    @pytest.mark.asyncio
    async def test_create_intro_no_auth(self, client: AsyncClient):
        """POST /api/v1/matches/intros without token returns 401."""
        resp = await client.post(
            "/api/v1/matches/intros",
            json={"contact_id": FAKE_UUID},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_intro_contact_not_found(self, client: AsyncClient):
        """POST /api/v1/matches/intros with nonexistent contact returns 404."""
        headers = await _auth_headers(client)
        resp = await client.post(
            "/api/v1/matches/intros",
            headers=headers,
            json={"contact_id": FAKE_UUID},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_intro_invalid_payload(self, client: AsyncClient):
        """POST /api/v1/matches/intros with missing contact_id returns 422."""
        headers = await _auth_headers(client)
        resp = await client.post(
            "/api/v1/matches/intros",
            headers=headers,
            json={},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_intro_not_found(self, client: AsyncClient):
        """GET /api/v1/matches/intros/{id} for nonexistent intro returns 404."""
        headers = await _auth_headers(client)
        resp = await client.get(f"/api/v1/matches/intros/{FAKE_UUID}", headers=headers)
        assert resp.status_code == 404


# ===========================================================================
# 5. PREFERENCES — /api/v1/preferences
# ===========================================================================


class TestPreferencesErrors:
    """Error paths for the preferences module."""

    @pytest.mark.asyncio
    async def test_get_job_prefs_no_auth(self, client: AsyncClient):
        """GET /api/v1/preferences/job without token returns 401."""
        resp = await client.get("/api/v1/preferences/job")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_job_prefs_not_set(self, client: AsyncClient):
        """GET /api/v1/preferences/job when user has no prefs returns 404."""
        headers = await _auth_headers(client)
        resp = await client.get("/api/v1/preferences/job", headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_job_prefs_not_set(self, client: AsyncClient):
        """DELETE /api/v1/preferences/job when user has no prefs returns 404."""
        headers = await _auth_headers(client)
        resp = await client.delete("/api/v1/preferences/job", headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_upsert_job_prefs_invalid_payload(self, client: AsyncClient):
        """PUT /api/v1/preferences/job with missing required field returns 422."""
        headers = await _auth_headers(client)
        # JobPreferencesCreate requires target_role
        resp = await client.put(
            "/api/v1/preferences/job",
            headers=headers,
            json={"target_seniority": "senior"},
        )
        assert resp.status_code == 422


# ===========================================================================
# 6. WEBHOOKS — /api/v1/webhooks/stripe
# ===========================================================================


class TestWebhooksErrors:
    """Error paths for the Stripe webhook module."""

    @pytest.mark.asyncio
    async def test_webhook_invalid_json(self, client: AsyncClient):
        """POST /api/v1/webhooks/stripe with non-JSON body returns 400."""
        resp = await client.post(
            "/api/v1/webhooks/stripe",
            content=b"this is not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400
        assert "Invalid JSON" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_webhook_missing_signature_when_secret_set(self, client: AsyncClient):
        """POST /api/v1/webhooks/stripe without Stripe-Signature when
        STRIPE_WEBHOOK_SECRET is configured returns 400."""
        from app.config import settings

        original = settings.STRIPE_WEBHOOK_SECRET
        settings.STRIPE_WEBHOOK_SECRET = "whsec_test_secret_for_error_tests"

        try:
            resp = await client.post(
                "/api/v1/webhooks/stripe",
                json={"type": "checkout.session.completed"},
            )
            assert resp.status_code == 400
            assert "Missing Stripe-Signature" in resp.json()["detail"]
        finally:
            settings.STRIPE_WEBHOOK_SECRET = original

    @pytest.mark.asyncio
    async def test_webhook_invalid_signature(self, client: AsyncClient):
        """POST /api/v1/webhooks/stripe with wrong signature returns 400."""
        from app.config import settings

        original = settings.STRIPE_WEBHOOK_SECRET
        settings.STRIPE_WEBHOOK_SECRET = "whsec_test_secret_for_error_tests"

        try:
            resp = await client.post(
                "/api/v1/webhooks/stripe",
                json={"type": "checkout.session.completed"},
                headers={"stripe-signature": "t=123,v1=badsignature"},
            )
            assert resp.status_code == 400
            assert "Invalid webhook signature" in resp.json()["detail"]
        finally:
            settings.STRIPE_WEBHOOK_SECRET = original
