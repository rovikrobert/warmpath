import io
from datetime import date, timedelta

from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_CSV = (
    "First Name,Last Name,Email Address,Company,Position,Connected On\n"
    "Alice,Smith,alice@example.com,Acme Corp,CEO,{recent}\n"
).format(
    recent=(date.today() - timedelta(days=30)).strftime("%d %b %Y"),
)


async def _signup_and_get_token(
    client: AsyncClient, email: str = "usage@example.com"
) -> str:
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Secret123", "full_name": "Usage User"},
    )
    return resp.json()["data"]["access_token"]


def _csv_file(content: str = SAMPLE_CSV):
    return {
        "file": ("connections.csv", io.BytesIO(content.encode("utf-8")), "text/csv")
    }


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


async def test_health_check(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "healthy"
    # Celery field present (unavailable in tests since no broker)
    assert resp.json()["data"]["celery"] in ("connected", "unavailable")


# ---------------------------------------------------------------------------
# Usage stats
# ---------------------------------------------------------------------------


async def test_usage_stats_empty(client: AsyncClient):
    """New user with no activity should have zero counts."""
    token = await _signup_and_get_token(client, email="empty_usage@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/usage/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["counts"]["csv_upload"] == 0
    assert body["counts"]["smart_search"] == 0
    assert body["counts"]["intro_draft"] == 0


async def test_usage_stats_tracks_uploads(client: AsyncClient):
    """After a CSV upload, the usage count should increment."""
    token = await _signup_and_get_token(client, email="upload_usage@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Do an upload (which the middleware logs)
    await client.post("/api/v1/contacts/upload", headers=headers, files=_csv_file())

    resp = await client.get("/api/v1/usage/me", headers=headers)
    body = resp.json()["data"]
    # At minimum, total_metered_calls should be > 0 from the metering middleware
    assert body["total_metered_calls"] >= 1


async def test_usage_stats_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/usage/me")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Error handling — consistent format
# ---------------------------------------------------------------------------


async def test_not_found_error_format(client: AsyncClient):
    """404 errors should return consistent error envelope."""
    token = await _signup_and_get_token(client, email="err404@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(
        "/api/v1/contacts/00000000-0000-0000-0000-000000000000",
        headers=headers,
    )
    assert resp.status_code == 404
    # FastAPI's HTTPException returns {"detail": "..."} — our global handler
    # catches AppError subclasses with {"error": {...}} format
    body = resp.json()
    assert "detail" in body or "error" in body


async def test_validation_error_on_bad_input(client: AsyncClient):
    """Pydantic validation errors should return 422."""
    token = await _signup_and_get_token(client, email="err422@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Missing required field 'name' for search creation
    resp = await client.post(
        "/api/v1/search",
        headers=headers,
        json={},
    )
    assert resp.status_code == 422


async def test_auth_error_no_token(client: AsyncClient):
    """Requests without auth should get 401/403."""
    resp = await client.get("/api/v1/contacts")
    assert resp.status_code in (401, 403)


async def test_auth_error_bad_token(client: AsyncClient):
    """Requests with invalid token should get 401."""
    headers = {"Authorization": "Bearer invalid-token-here"}
    resp = await client.get("/api/v1/contacts", headers=headers)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


async def test_csv_upload_rate_limit(client: AsyncClient):
    """Exceeding the CSV upload rate limit should return 429."""
    # We'll set a very low limit via monkeypatch
    from app.config import settings

    original = settings.RATE_LIMIT_CSV_UPLOADS_PER_DAY
    settings.RATE_LIMIT_CSV_UPLOADS_PER_DAY = 2

    try:
        token = await _signup_and_get_token(client, email="ratelimit@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        # Upload #1 — should succeed
        resp1 = await client.post(
            "/api/v1/contacts/upload", headers=headers, files=_csv_file()
        )
        assert resp1.status_code == 201

        # Upload #2 — should succeed
        resp2 = await client.post(
            "/api/v1/contacts/upload", headers=headers, files=_csv_file()
        )
        assert resp2.status_code == 201

        # Upload #3 — should be rate limited
        resp3 = await client.post(
            "/api/v1/contacts/upload", headers=headers, files=_csv_file()
        )
        assert resp3.status_code == 429
        body = resp3.json()
        assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    finally:
        settings.RATE_LIMIT_CSV_UPLOADS_PER_DAY = original


async def test_search_run_rate_limit(client: AsyncClient):
    """Exceeding the search run rate limit should return 429."""
    from app.config import settings

    original = settings.RATE_LIMIT_SEARCH_RUNS_PER_DAY
    settings.RATE_LIMIT_SEARCH_RUNS_PER_DAY = 1

    try:
        token = await _signup_and_get_token(client, email="searchlimit@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        # Create a search
        create_resp = await client.post(
            "/api/v1/search",
            headers=headers,
            json={"name": "Rate limit test", "target_role": "Engineer"},
        )
        search_id = create_resp.json()["data"]["id"]

        # Run #1 — should succeed
        resp1 = await client.post(f"/api/v1/search/{search_id}/run", headers=headers)
        assert resp1.status_code == 200

        # Run #2 — should be rate limited
        resp2 = await client.post(f"/api/v1/search/{search_id}/run", headers=headers)
        assert resp2.status_code == 429
        assert resp2.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    finally:
        settings.RATE_LIMIT_SEARCH_RUNS_PER_DAY = original


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


async def test_cors_headers_present(client: AsyncClient):
    """CORS headers should be present for configured origins."""
    resp = await client.options(
        "/api/v1/contacts",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    # CORS middleware should respond
    assert resp.status_code in (200, 204)
    assert "access-control-allow-origin" in resp.headers


async def test_cors_blocks_unknown_origin(client: AsyncClient):
    """Requests from non-configured origins should not get CORS headers."""
    resp = await client.options(
        "/api/v1/contacts",
        headers={
            "Origin": "http://evil.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # The origin should not be reflected back
    allow_origin = resp.headers.get("access-control-allow-origin", "")
    assert "evil.com" not in allow_origin


# ---------------------------------------------------------------------------
# Custom exception classes
# ---------------------------------------------------------------------------


class TestCustomExceptions:
    def test_rate_limit_error_format(self):
        from app.utils.exceptions import RateLimitError

        err = RateLimitError("Too many requests")
        assert err.status_code == 429
        assert err.code == "RATE_LIMIT_EXCEEDED"
        assert err.message == "Too many requests"

    def test_not_found_error_format(self):
        from app.utils.exceptions import NotFoundError

        err = NotFoundError("Contact not found")
        assert err.status_code == 404
        assert err.code == "NOT_FOUND"

    def test_unauthorized_error_format(self):
        from app.utils.exceptions import UnauthorizedError

        err = UnauthorizedError()
        assert err.status_code == 401
        assert err.code == "UNAUTHORIZED"

    def test_forbidden_error_format(self):
        from app.utils.exceptions import ForbiddenError

        err = ForbiddenError()
        assert err.status_code == 403
        assert err.code == "FORBIDDEN"

    def test_validation_error_format(self):
        from app.utils.exceptions import ValidationError

        err = ValidationError("Bad field")
        assert err.status_code == 422
        assert err.code == "VALIDATION_ERROR"

    def test_app_error_is_base(self):
        from app.utils.exceptions import AppError, NotFoundError

        assert issubclass(NotFoundError, AppError)
        assert issubclass(NotFoundError, Exception)
