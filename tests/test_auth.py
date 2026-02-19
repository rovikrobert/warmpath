"""Auth endpoint tests — Clerk JWT integration."""

from httpx import AsyncClient
from sqlalchemy import select

from app.models.user import User
from tests.conftest import (
    TestSessionLocal,
    create_test_user_in_db,
    create_test_clerk_token,
)


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
        json={"intent": "sha[RESEND_KEY_REDACTED]", "full_name": "Jane Doe"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["intent"] == "sha[RESEND_KEY_REDACTED]"

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


async def test_me_returns_onboarding_complete_false_for_new_user(client: AsyncClient):
    """GET /me returns onboarding_complete=false for new users."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="new@test.com", full_name="New User"
        )
    resp = await client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["onboarding_complete"] is False
