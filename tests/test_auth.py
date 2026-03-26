"""Auth endpoint tests — Clerk JWT integration."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.user import User
from tests.conftest import (
    TestSessionLocal,
    create_test_user_in_db,
    create_test_clerk_token,
)


@pytest.mark.smoke
async def test_me_returns_profile_and_capabilities(client: AsyncClient):
    """GET /me returns user profile with capabilities for valid Clerk JWT."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="me@test.com", full_name="Me User"
        )
    resp = await client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["email"] == "me@test.com"
    assert body["data"]["full_name"] == "Me User"
    assert body["data"]["plan_tier"] == "free"
    assert "id" in body["data"]
    assert "capabilities" in body["data"]
    assert "meta" in body

    # No sensitive fields exposed
    data_str = str(body["data"]).lower()
    assert "password" not in data_str
    assert "clerk_user_id" not in body["data"]


@pytest.mark.smoke
async def test_me_includes_profile_completeness(client: AsyncClient):
    """GET /me returns profile_completeness with score and missing fields."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="completeness@test.com", full_name="Completeness User"
        )
    resp = await client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "profile_completeness" in data
    assert "score" in data["profile_completeness"]
    assert "missing" in data["profile_completeness"]
    assert "total_fields" in data["profile_completeness"]
    # New user with no profile should have score 0
    assert data["profile_completeness"]["score"] == 0
    assert data["profile_completeness"]["total_fields"] == 9


async def test_me_without_token_returns_401(client: AsyncClient):
    """GET /me without Authorization header returns 401/403."""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code in (401, 403)


async def test_me_with_invalid_token_returns_401(client: AsyncClient):
    """GET /me with garbage token returns 401."""
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert resp.status_code == 401


async def test_me_with_unknown_clerk_id_returns_401(client: AsyncClient):
    """GET /me with valid JWT but unknown clerk_user_id returns 401."""
    token = create_test_clerk_token("user_nonexistent_abc")
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
    assert "not found" in resp.json()["detail"].lower()


async def test_intent_update(client: AsyncClient):
    """PATCH /intent updates user onboarding intent."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="intent@test.com", full_name="Intent User"
        )
    resp = await client.patch(
        "/api/v1/auth/intent",
        json={"intent": "find_referrals"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["intent"] == "find_referrals"


async def test_intent_update_with_full_name(client: AsyncClient):
    """PATCH /intent with full_name syncs name to backend."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="intentname@test.com", full_name="Old Name"
        )
    resp = await client.patch(
        "/api/v1/auth/intent",
        json={"intent": "share_network", "full_name": "Jane Doe"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["intent"] == "share_network"

    # Verify name was updated
    me_resp = await client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.json()["data"]["full_name"] == "Jane Doe"


async def test_intent_update_without_full_name_leaves_name_unchanged(
    client: AsyncClient,
):
    """PATCH /intent without full_name does not change existing name."""
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="intentkeep@test.com", full_name="Keep Name"
        )
    resp = await client.patch(
        "/api/v1/auth/intent",
        json={"intent": "explore"},
        headers=headers,
    )
    assert resp.status_code == 200

    me_resp = await client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.json()["data"]["full_name"] == "Keep Name"


async def test_delete_account_requires_confirmation(client: AsyncClient):
    """DELETE account without confirm_deletion returns 422."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="nodelete@test.com", full_name="No Delete"
        )
    resp = await client.post(
        "/api/v1/auth/delete-account",
        json={"confirm_deletion": False},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_delete_account_success(client: AsyncClient):
    """DELETE account with confirmation deletes the user."""
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="delete@test.com", full_name="Delete Me"
        )
        user_id = user.id

    resp = await client.post(
        "/api/v1/auth/delete-account",
        json={"confirm_deletion": True},
        headers=headers,
    )
    assert resp.status_code == 200
    assert "deleted" in resp.json()["data"]["message"].lower()

    # Verify user is gone
    async with TestSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Onboarding completion
# ---------------------------------------------------------------------------


async def test_onboarding_complete_rejects_when_no_intent(client: AsyncClient):
    """POST /onboarding-complete fails if intent is not set."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="nosetup@test.com", full_name="No Setup"
        )
    resp = await client.post("/api/v1/auth/onboarding-complete", headers=headers)
    assert resp.status_code == 422
    body = resp.json()
    assert "intent" in body["detail"].lower()


async def test_onboarding_complete_rejects_when_no_preferences(client: AsyncClient):
    """POST /onboarding-complete fails if job preferences missing."""
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="nopref@test.com", full_name="No Pref"
        )
        user.intent = "find_referrals"
        await db.commit()
    resp = await client.post("/api/v1/auth/onboarding-complete", headers=headers)
    assert resp.status_code == 422
    body = resp.json()
    assert "preference" in body["detail"].lower()


async def test_onboarding_complete_rejects_when_no_contacts(client: AsyncClient):
    """POST /onboarding-complete fails if no contacts uploaded."""
    from app.models.job import UserJobPreferences

    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="nocontacts@test.com", full_name="No Contacts"
        )
        user.intent = "find_referrals"
        prefs = UserJobPreferences(
            user_id=user.id,
            target_role="Engineer",
            target_industries=[],
            target_locations=[],
        )
        db.add(prefs)
        await db.commit()
    resp = await client.post("/api/v1/auth/onboarding-complete", headers=headers)
    assert resp.status_code == 422
    body = resp.json()
    assert "contact" in body["detail"].lower()


async def test_onboarding_complete_rejects_when_no_work_history(client: AsyncClient):
    """POST /onboarding-complete fails if no connector profile with work history."""
    from app.models.contact import Contact
    from app.models.job import UserJobPreferences

    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="nowork@test.com", full_name="No Work"
        )
        user.intent = "find_referrals"
        prefs = UserJobPreferences(
            user_id=user.id,
            target_role="Engineer",
            target_industries=[],
            target_locations=[],
        )
        db.add(prefs)
        contact = Contact(
            user_id=user.id,
            full_name="Jane Doe",
            first_name="Jane",
            last_name="Doe",
            current_company="Acme",
            current_title="Engineer",
        )
        db.add(contact)
        await db.commit()
    resp = await client.post("/api/v1/auth/onboarding-complete", headers=headers)
    assert resp.status_code == 422
    body = resp.json()
    assert "work history" in body["detail"].lower()


@pytest.mark.smoke
async def test_onboarding_complete_succeeds_with_all_steps(client: AsyncClient):
    """POST /onboarding-complete stamps onboarding_completed_at when all steps done."""
    from app.models.contact import Contact
    from app.models.job import UserJobPreferences
    from app.models.user import ConnectorProfile

    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="allsteps@test.com", full_name="All Steps"
        )
        user.intent = "find_referrals"
        prefs = UserJobPreferences(
            user_id=user.id,
            target_role="Engineer",
            target_industries=[],
            target_locations=[],
        )
        db.add(prefs)
        contact = Contact(
            user_id=user.id,
            full_name="Jane Doe",
            first_name="Jane",
            last_name="Doe",
            current_company="Acme",
            current_title="Engineer",
        )
        db.add(contact)
        profile = ConnectorProfile(
            user_id=user.id,
            work_history=[{"company": "Acme", "title": "SWE"}],
        )
        db.add(profile)
        await db.commit()
    resp = await client.post("/api/v1/auth/onboarding-complete", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["onboarding_complete"] is True


@pytest.mark.smoke
async def test_onboarding_complete_succeeds_for_share_network_without_preferences(
    client: AsyncClient,
):
    """POST /onboarding-complete passes for share_network users without job preferences."""
    from app.models.contact import Contact
    from app.models.user import ConnectorProfile

    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="nhnoprefs@test.com", full_name="NH No Prefs"
        )
        user.intent = "share_network"
        # No UserJobPreferences created — NHs don't need them
        contact = Contact(
            user_id=user.id,
            full_name="Jane Doe",
            first_name="Jane",
            last_name="Doe",
            current_company="Acme",
            current_title="Engineer",
        )
        db.add(contact)
        profile = ConnectorProfile(
            user_id=user.id,
            work_history=[{"company": "Acme", "title": "SWE"}],
        )
        db.add(profile)
        await db.commit()
    resp = await client.post("/api/v1/auth/onboarding-complete", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["onboarding_complete"] is True
    assert body["data"]["intent"] == "share_network"


async def test_onboarding_complete_succeeds_with_csv_upload_but_no_contacts_yet(
    client: AsyncClient,
):
    """POST /onboarding-complete passes when CsvUpload exists but Celery
    hasn't created Contact rows yet (async processing race condition)."""
    from app.models.contact import CsvUpload
    from app.models.job import UserJobPreferences
    from app.models.user import ConnectorProfile

    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="asynccsv@test.com", full_name="Async CSV"
        )
        user.intent = "find_referrals"
        prefs = UserJobPreferences(
            user_id=user.id,
            target_role="Engineer",
            target_industries=[],
            target_locations=[],
        )
        db.add(prefs)
        # CsvUpload record exists (created immediately) but no Contact rows yet
        csv_upload = CsvUpload(
            user_id=user.id,
            filename="connections.csv",
            file_size_bytes=1024,
            status="queued",
        )
        db.add(csv_upload)
        profile = ConnectorProfile(
            user_id=user.id,
            work_history=[{"company": "Acme", "title": "SWE"}],
        )
        db.add(profile)
        await db.commit()
    resp = await client.post("/api/v1/auth/onboarding-complete", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["onboarding_complete"] is True


async def test_onboarding_complete_rejects_completed_csv_with_zero_contacts(
    client: AsyncClient,
):
    """POST /onboarding-complete fails when CsvUpload exists with status='completed'
    but 0 contacts were created (e.g. user uploaded a resume, not a LinkedIn CSV)."""
    from app.models.contact import CsvUpload
    from app.models.job import UserJobPreferences
    from app.models.user import ConnectorProfile

    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="badcsv@test.com", full_name="Bad CSV"
        )
        user.intent = "find_referrals"
        prefs = UserJobPreferences(
            user_id=user.id,
            target_role="Engineer",
            target_industries=[],
            target_locations=[],
        )
        db.add(prefs)
        csv_upload = CsvUpload(
            user_id=user.id,
            filename="CSV resume.csv",
            file_size_bytes=2048,
            status="completed",
            contacts_created=0,
        )
        db.add(csv_upload)
        profile = ConnectorProfile(
            user_id=user.id,
            work_history=[{"company": "Acme", "title": "SWE"}],
        )
        db.add(profile)
        await db.commit()
    resp = await client.post("/api/v1/auth/onboarding-complete", headers=headers)
    assert resp.status_code == 422
    body = resp.json()
    assert "contact" in body["detail"].lower()
    assert "linkedin" in body["detail"].lower()


async def test_onboarding_complete_rejects_failed_csv_with_zero_contacts(
    client: AsyncClient,
):
    """POST /onboarding-complete fails when CsvUpload has status='failed'
    and 0 contacts exist."""
    from app.models.contact import CsvUpload
    from app.models.job import UserJobPreferences
    from app.models.user import ConnectorProfile

    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="failedcsv@test.com", full_name="Failed CSV"
        )
        user.intent = "find_referrals"
        prefs = UserJobPreferences(
            user_id=user.id,
            target_role="Engineer",
            target_industries=[],
            target_locations=[],
        )
        db.add(prefs)
        csv_upload = CsvUpload(
            user_id=user.id,
            filename="connections.csv",
            file_size_bytes=512,
            status="failed",
            error_message="Parse error",
        )
        db.add(csv_upload)
        profile = ConnectorProfile(
            user_id=user.id,
            work_history=[{"company": "Acme", "title": "SWE"}],
        )
        db.add(profile)
        await db.commit()
    resp = await client.post("/api/v1/auth/onboarding-complete", headers=headers)
    assert resp.status_code == 422
    body = resp.json()
    assert "contact" in body["detail"].lower()


async def test_onboarding_complete_passes_with_processing_csv_and_zero_contacts(
    client: AsyncClient,
):
    """POST /onboarding-complete passes when CsvUpload has status='processing'
    and 0 contacts (upload still in progress, contacts will appear soon)."""
    from app.models.contact import CsvUpload
    from app.models.job import UserJobPreferences
    from app.models.user import ConnectorProfile

    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="processingcsv@test.com", full_name="Processing CSV"
        )
        user.intent = "find_referrals"
        prefs = UserJobPreferences(
            user_id=user.id,
            target_role="Engineer",
            target_industries=[],
            target_locations=[],
        )
        db.add(prefs)
        csv_upload = CsvUpload(
            user_id=user.id,
            filename="connections.csv",
            file_size_bytes=1024,
            status="processing",
        )
        db.add(csv_upload)
        profile = ConnectorProfile(
            user_id=user.id,
            work_history=[{"company": "Acme", "title": "SWE"}],
        )
        db.add(profile)
        await db.commit()
    resp = await client.post("/api/v1/auth/onboarding-complete", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["onboarding_complete"] is True


@pytest.mark.smoke
async def test_onboarding_complete_is_idempotent(client: AsyncClient):
    """POST /onboarding-complete twice returns 200 both times."""
    from app.models.contact import Contact
    from app.models.job import UserJobPreferences
    from app.models.user import ConnectorProfile

    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="idempotent@test.com", full_name="Idempotent"
        )
        user.intent = "explore"
        prefs = UserJobPreferences(
            user_id=user.id,
            target_role="PM",
            target_industries=[],
            target_locations=[],
        )
        db.add(prefs)
        contact = Contact(
            user_id=user.id,
            full_name="Bob Smith",
            first_name="Bob",
            last_name="Smith",
            current_company="BigCo",
            current_title="PM",
        )
        db.add(contact)
        profile = ConnectorProfile(
            user_id=user.id,
            work_history=[{"company": "BigCo", "title": "PM"}],
        )
        db.add(profile)
        await db.commit()
    resp1 = await client.post("/api/v1/auth/onboarding-complete", headers=headers)
    assert resp1.status_code == 200
    resp2 = await client.post("/api/v1/auth/onboarding-complete", headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["data"]["onboarding_complete"] is True


@pytest.mark.smoke
async def test_me_returns_onboarding_complete_false_for_new_user(client: AsyncClient):
    """GET /me returns onboarding_complete=false for new users."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="new@test.com", full_name="New User"
        )
    resp = await client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["onboarding_complete"] is False


async def test_upsert_profile_with_url_fields(client: AsyncClient):
    """Profile URL fields (github, portfolio, personal site) are accepted and persisted."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="urls@test.com", full_name="URL User"
        )
    resp = await client.post(
        "/api/v1/auth/profile",
        json={
            "current_title": "Engineer",
            "github_url": "https://github.com/janedoe",
            "portfolio_url": "https://janedoe.dev",
            "personal_site_url": "https://janedoe.com",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["github_url"] == "https://github.com/janedoe"
    assert data["portfolio_url"] == "https://janedoe.dev"
    assert data["personal_site_url"] == "https://janedoe.com"
    assert data["current_title"] == "Engineer"


async def test_onboarding_complete_seeds_feed_items(client: AsyncClient):
    """POST /onboarding-complete triggers feed generation for the new user."""
    from app.models.contact import Contact
    from app.models.feed import FeedItem
    from app.models.job import UserJobPreferences
    from app.models.user import ConnectorProfile

    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="feedseed@test.com", full_name="Feed Seed"
        )
        user.intent = "find_referrals"
        prefs = UserJobPreferences(
            user_id=user.id,
            target_role="Engineer",
            target_industries=[],
            target_locations=[],
        )
        db.add(prefs)
        contact = Contact(
            user_id=user.id,
            full_name="Jane Doe",
            first_name="Jane",
            last_name="Doe",
            current_company="Acme",
            current_title="Engineer",
        )
        db.add(contact)
        profile = ConnectorProfile(
            user_id=user.id,
            work_history=[{"company": "Acme", "title": "SWE"}],
        )
        db.add(profile)
        await db.commit()

    resp = await client.post("/api/v1/auth/onboarding-complete", headers=headers)
    assert resp.status_code == 200

    # Verify feed items were created
    async with TestSessionLocal() as db:
        from sqlalchemy import select

        result = await db.execute(select(FeedItem).where(FeedItem.user_id == user.id))
        items = result.scalars().all()
        assert len(items) >= 1, "Feed items should be seeded after onboarding"
