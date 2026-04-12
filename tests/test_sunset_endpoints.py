"""Tests for SUNSET_MODE — upload and intro endpoints return 410 Gone."""

from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.conftest import TestSessionLocal, create_test_user_in_db


@pytest_asyncio.fixture
async def sunset_client(truncate_tables):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def test_user(truncate_tables):
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(db, email="sunset@example.com")
    return user, headers


@pytest.mark.asyncio
async def test_upload_csv_returns_410_when_sunset_mode_enabled(
    sunset_client, test_user
):
    """CSV upload endpoint returns 410 Gone with sunset message when SUNSET_MODE=True."""
    _, headers = test_user
    csv_content = b"First Name,Last Name,Email Address,Company,Position,Connected On\nJane,Doe,jane@example.com,Acme,Engineer,01 Jan 2024"

    with patch("app.api.contacts.settings") as mock_settings:
        mock_settings.SUNSET_MODE = True
        # mirror other settings used in the endpoint
        mock_settings.RATE_LIMIT_CSV_UPLOADS_PER_DAY = 5
        mock_settings.CSV_MAX_FILE_SIZE = 10 * 1024 * 1024
        mock_settings.CSV_MAX_ROWS = 50_000
        mock_settings.CSV_ASYNC_PROCESSING = False
        mock_settings.CSV_PIPELINE_V2 = False

        response = await sunset_client.post(
            "/api/v1/contacts/upload",
            files={"file": ("connections.csv", csv_content, "text/csv")},
            headers=headers,
        )

    assert response.status_code == 410
    body = response.json()
    assert body["error"]["code"] == "GONE"
    assert "shutting down" in body["error"]["message"].lower()
    assert "csv uploads" in body["error"]["message"].lower()


@pytest.mark.asyncio
async def test_upload_csv_proceeds_normally_when_sunset_mode_disabled(
    sunset_client, test_user
):
    """CSV upload endpoint does NOT return 410 when SUNSET_MODE=False."""
    _, headers = test_user
    csv_content = b"First Name,Last Name,Email Address,Company,Position,Connected On\nJane,Doe,jane@example.com,Acme,Engineer,01 Jan 2024"

    with patch("app.api.contacts.settings") as mock_settings:
        mock_settings.SUNSET_MODE = False
        mock_settings.RATE_LIMIT_CSV_UPLOADS_PER_DAY = 5
        mock_settings.CSV_MAX_FILE_SIZE = 10 * 1024 * 1024
        mock_settings.CSV_MAX_ROWS = 50_000
        mock_settings.CSV_ASYNC_PROCESSING = False
        mock_settings.CSV_PIPELINE_V2 = False

        response = await sunset_client.post(
            "/api/v1/contacts/upload",
            files={"file": ("connections.csv", csv_content, "text/csv")},
            headers=headers,
        )

    assert response.status_code != 410


@pytest.mark.asyncio
async def test_create_intro_returns_410_when_sunset_mode_enabled(
    sunset_client, test_user
):
    """Create intro endpoint returns 410 Gone with sunset message when SUNSET_MODE=True."""
    _, headers = test_user

    with patch("app.api.matches.settings") as mock_settings:
        mock_settings.SUNSET_MODE = True

        response = await sunset_client.post(
            "/api/v1/matches/intros",
            json={
                "contact_id": "00000000-0000-0000-0000-000000000001",
                "match_result_id": "00000000-0000-0000-0000-000000000002",
                "context": "I'd like an intro",
                "tone": "professional",
                "channel": "linkedin",
            },
            headers=headers,
        )

    assert response.status_code == 410
    body = response.json()
    assert body["error"]["code"] == "GONE"
    assert "shutting down" in body["error"]["message"].lower()
    assert "intro requests" in body["error"]["message"].lower()
