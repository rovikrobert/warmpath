"""Tests for P14: relationship types, work history, manual contacts."""

import io
from datetime import date, timedelta
from types import SimpleNamespace

from httpx import AsyncClient

from app.services.csv_parser import classify_relationship
from app.services.warm_scorer import compute_warm_score

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_CSV = (
    "First Name,Last Name,Email Address,Company,Position,Connected On\n"
    "Alice,Smith,alice@example.com,Acme Corp,CEO,{recent}\n"
    "Bob,Recruiter,,TalentCo,Senior Recruiter,{recent}\n"
    "Carol,Colleague,,Stripe,Software Engineer,{recent}\n"
).format(recent=(date.today() - timedelta(days=30)).strftime("%d %b %Y"))


async def _signup(client: AsyncClient, email: str = "reltest@test.com") -> dict:
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Secret123", "full_name": "Rel User"},
    )
    token = resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get("/api/v1/auth/me", headers=headers)
    return {"headers": headers, "user_id": me.json()["data"]["id"]}


async def _signup_with_profile(
    client: AsyncClient,
    email: str,
    company: str,
    work_history: list[dict] | None = None,
) -> dict:
    auth = await _signup(client, email)
    profile_data = {"current_company": company}
    if work_history:
        profile_data["work_history"] = work_history
    await client.post(
        "/api/v1/auth/profile", headers=auth["headers"], json=profile_data
    )
    return auth


def _csv_file(content: str = SAMPLE_CSV):
    return {
        "file": ("connections.csv", io.BytesIO(content.encode("utf-8")), "text/csv")
    }


# ---------------------------------------------------------------------------
# classify_relationship() unit tests
# ---------------------------------------------------------------------------


class TestClassifyRelationship:
    def test_current_colleague(self):
        result = classify_relationship("Stripe", "Engineer", "Stripe", None)
        assert result == "current_colleague"

    def test_former_colleague(self):
        history = [{"company": "Google", "title": "PM"}]
        result = classify_relationship("Google", "Engineer", "Stripe", history)
        assert result == "former_colleague"

    def test_recruiter_by_title(self):
        result = classify_relationship("TalentCo", "Senior Recruiter", "Stripe", None)
        assert result == "recruiter"

    def test_recruiter_talent_acquisition(self):
        result = classify_relationship("", "Talent Acquisition Partner", None, None)
        assert result == "recruiter"

    def test_unknown_no_match(self):
        result = classify_relationship("RandomCo", "Engineer", "Stripe", None)
        assert result is None

    def test_no_company_no_title(self):
        result = classify_relationship(None, None, "Stripe", None)
        assert result is None

    def test_case_insensitive(self):
        result = classify_relationship("stripe", "Engineer", "Stripe", None)
        assert result == "current_colleague"


# ---------------------------------------------------------------------------
# Auto-classification during CSV import
# ---------------------------------------------------------------------------


async def test_auto_classify_during_upload(client: AsyncClient):
    """CSV import should auto-classify relationship types based on user profile."""
    auth = await _signup_with_profile(client, "autoclassify@test.com", "Stripe")

    await client.post(
        "/api/v1/contacts/upload", headers=auth["headers"], files=_csv_file()
    )

    resp = await client.get(
        "/api/v1/contacts",
        headers=auth["headers"],
        params={"per_page": 100},
    )
    contacts = resp.json()["data"]

    # Bob with "Senior Recruiter" title → recruiter
    bob = next(c for c in contacts if c["full_name"] == "Bob Recruiter")
    assert bob["relationship_type"] == "recruiter"

    # Carol at Stripe, user at Stripe → current_colleague
    carol = next(c for c in contacts if c["full_name"] == "Carol Colleague")
    assert carol["relationship_type"] == "current_colleague"


# ---------------------------------------------------------------------------
# PATCH /contacts/{id} — set relationship_type
# ---------------------------------------------------------------------------


async def test_patch_contact_relationship_type(client: AsyncClient):
    """PATCH should update relationship_type."""
    auth = await _signup(client, "patch_rel@test.com")

    # Upload a contact first
    await client.post(
        "/api/v1/contacts/upload", headers=auth["headers"], files=_csv_file()
    )
    contacts_resp = await client.get(
        "/api/v1/contacts", headers=auth["headers"], params={"per_page": 100}
    )
    contact_id = contacts_resp.json()["data"][0]["id"]

    # Patch it
    resp = await client.patch(
        f"/api/v1/contacts/{contact_id}",
        headers=auth["headers"],
        json={"relationship_type": "friend"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["relationship_type"] == "friend"


async def test_patch_invalid_relationship_type(client: AsyncClient):
    """PATCH with invalid relationship_type should return 422."""
    auth = await _signup(client, "patch_invalid@test.com")

    await client.post(
        "/api/v1/contacts/upload", headers=auth["headers"], files=_csv_file()
    )
    contacts_resp = await client.get(
        "/api/v1/contacts", headers=auth["headers"], params={"per_page": 100}
    )
    contact_id = contacts_resp.json()["data"][0]["id"]

    resp = await client.patch(
        f"/api/v1/contacts/{contact_id}",
        headers=auth["headers"],
        json={"relationship_type": "bestie"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /contacts?relationship_type=... filter
# ---------------------------------------------------------------------------


async def test_filter_by_relationship_type(client: AsyncClient):
    """GET /contacts with relationship_type filter should narrow results."""
    auth = await _signup_with_profile(client, "filter_rel@test.com", "Stripe")

    await client.post(
        "/api/v1/contacts/upload", headers=auth["headers"], files=_csv_file()
    )

    # Filter for recruiters
    resp = await client.get(
        "/api/v1/contacts",
        headers=auth["headers"],
        params={"relationship_type": "recruiter"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) >= 1
    assert all(c["relationship_type"] == "recruiter" for c in data)


# ---------------------------------------------------------------------------
# Warm score bonuses for relationship types
# ---------------------------------------------------------------------------


def _mock_contact(**kwargs):
    """Create a minimal Contact-like object for scoring."""
    return SimpleNamespace(
        connected_on=kwargs.get("connected_on", date.today() - timedelta(days=30)),
        current_company=kwargs.get("current_company", "TestCo"),
        current_title=kwargs.get("current_title", "Engineer"),
        location=kwargs.get("location"),
        enriched_data=kwargs.get("enriched_data"),
        relationship_type=kwargs.get("relationship_type"),
        company=None,
    )


def _mock_profile(**kwargs):
    """Create a minimal ConnectorProfile-like object."""
    return SimpleNamespace(
        current_company=kwargs.get("current_company", "OtherCo"),
        current_title=kwargs.get("current_title"),
        industry=kwargs.get("industry"),
        location=kwargs.get("location"),
        bio_summary=kwargs.get("bio_summary"),
        work_history=kwargs.get("work_history"),
    )


class TestWarmScoreRelationshipBonuses:
    def test_manager_bonus(self):
        contact = _mock_contact(relationship_type="manager")
        profile = _mock_profile()
        result = compute_warm_score(contact, profile)
        # Manager bonus should be reflected in relationship score
        assert result.relationship_score >= 20

    def test_former_colleague_bonus(self):
        contact = _mock_contact(relationship_type="former_colleague")
        profile = _mock_profile()
        result = compute_warm_score(contact, profile)
        assert result.relationship_score >= 15

    def test_recruiter_penalty(self):
        contact = _mock_contact(relationship_type="recruiter")
        profile = _mock_profile()
        result = compute_warm_score(contact, profile)
        # Recruiter penalty should bring relationship score to 0
        assert result.relationship_score == 0.0

    def test_current_colleague_bonus(self):
        contact = _mock_contact(relationship_type="current_colleague")
        profile = _mock_profile()
        result = compute_warm_score(contact, profile)
        assert result.relationship_score >= 10

    def test_no_relationship_type_no_bonus(self):
        contact_with = _mock_contact(relationship_type="manager")
        contact_without = _mock_contact(relationship_type=None)
        profile = _mock_profile()
        sco[RESEND_KEY_REDACTED] = compute_warm_score(contact_with, profile)
        sco[RESEND_KEY_REDACTED] = compute_warm_score(contact_without, profile)
        assert sco[RESEND_KEY_REDACTED].total_score > sco[RESEND_KEY_REDACTED].total_score


# ---------------------------------------------------------------------------
# Work history overlap scoring
# ---------------------------------------------------------------------------


class TestWorkHistoryOverlapScoring:
    def test_contact_at_user_former_company_gets_boost(self):
        """Contact at company in user's work_history should score higher."""
        contact = _mock_contact(current_company="Stripe")
        profile = _mock_profile(work_history=[{"company": "Stripe", "title": "PM"}])
        result = compute_warm_score(contact, profile)
        assert result.factors["relationship"]["work_history_overlap"] is True
        assert result.relationship_score >= 35

    def test_no_overlap_no_boost(self):
        contact = _mock_contact(current_company="Stripe")
        profile = _mock_profile(work_history=[{"company": "Google", "title": "PM"}])
        result = compute_warm_score(contact, profile)
        assert result.factors["relationship"]["work_history_overlap"] is False

    def test_empty_work_history(self):
        contact = _mock_contact(current_company="Stripe")
        profile = _mock_profile(work_history=[])
        result = compute_warm_score(contact, profile)
        assert result.factors["relationship"]["work_history_overlap"] is False


# ---------------------------------------------------------------------------
# Manual contact creation
# ---------------------------------------------------------------------------


async def test_create_manual_contact(client: AsyncClient):
    """POST /contacts/manual should create a contact with source='manual'."""
    auth = await _signup(client, "manual@test.com")

    resp = await client.post(
        "/api/v1/contacts/manual",
        headers=auth["headers"],
        json={
            "first_name": "Jane",
            "last_name": "Doe",
            "company": "BigCorp",
            "position": "Product Manager",
            "email": "jane@bigcorp.com",
            "relationship_type": "friend",
            "how_you_know": "College roommate",
            "last_interaction_date": "2025-12-01",
        },
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["full_name"] == "Jane Doe"
    assert data["source"] == "manual"
    assert data["relationship_type"] == "friend"
    assert data["how_you_know"] == "College roommate"


async def test_manual_contact_scoring(client: AsyncClient):
    """Manual contacts should get warm scores computed."""
    auth = await _signup(client, "manual_score@test.com")

    resp = await client.post(
        "/api/v1/contacts/manual",
        headers=auth["headers"],
        json={
            "first_name": "Scored",
            "last_name": "Contact",
            "company": "TestCo",
            "position": "VP Engineering",
            "last_interaction_date": "2026-01-15",
        },
    )
    assert resp.status_code == 201
    contact_id = resp.json()["data"]["id"]

    # Fetch the contact — should have warm_score
    get_resp = await client.get(
        f"/api/v1/contacts/{contact_id}", headers=auth["headers"]
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["warm_score"] is not None


async def test_manual_contact_duplicate_rejected(client: AsyncClient):
    """Creating a duplicate manual contact should return 409."""
    auth = await _signup(client, "manual_dup@test.com")

    body = {
        "first_name": "Dup",
        "last_name": "Person",
        "company": "DupCo",
        "position": "Dev",
    }

    resp1 = await client.post(
        "/api/v1/contacts/manual", headers=auth["headers"], json=body
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        "/api/v1/contacts/manual", headers=auth["headers"], json=body
    )
    assert resp2.status_code == 409


# ---------------------------------------------------------------------------
# Bulk manual import
# ---------------------------------------------------------------------------


async def test_bulk_import(client: AsyncClient):
    """POST /contacts/manual/bulk should create multiple contacts."""
    auth = await _signup(client, "bulk@test.com")

    contacts = [
        {"first_name": f"Bulk{i}", "last_name": "Person", "company": f"Co{i}"}
        for i in range(5)
    ]

    resp = await client.post(
        "/api/v1/contacts/manual/bulk",
        headers=auth["headers"],
        json={"contacts": contacts},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["created"] == 5
    assert data["errors"] == []


async def test_bulk_import_over_50_rejected(client: AsyncClient):
    """Bulk import of >50 contacts should return 422."""
    auth = await _signup(client, "bulk51@test.com")

    contacts = [
        {"first_name": f"Over{i}", "last_name": "Limit", "company": f"Co{i}"}
        for i in range(51)
    ]

    resp = await client.post(
        "/api/v1/contacts/manual/bulk",
        headers=auth["headers"],
        json={"contacts": contacts},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Profile work_history
# ---------------------------------------------------------------------------


async def test_profile_work_history(client: AsyncClient):
    """POST /auth/profile should accept and return work_history."""
    auth = await _signup(client, "workhist@test.com")

    resp = await client.post(
        "/api/v1/auth/profile",
        headers=auth["headers"],
        json={
            "current_company": "CurrentCo",
            "work_history": [
                {
                    "company": "PrevCo",
                    "title": "Engineer",
                    "start_date": "2020-01",
                    "end_date": "2023-06",
                },
                {"company": "OldCo", "title": "Intern"},
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["work_history"] is not None
    assert len(data["work_history"]) == 2
    assert data["work_history"][0]["company"] == "PrevCo"


# ---------------------------------------------------------------------------
# Auto-detect manual CSV format
# ---------------------------------------------------------------------------


async def test_manual_csv_format_auto_detected(client: AsyncClient):
    """CSV upload with manual format headers should be auto-detected."""
    auth = await _signup(client, "manualcsv@test.com")

    manual_csv = (
        "Name,Company,Title,Relationship,How You Know,Last Contact Date\n"
        "John Smith,TechCo,Engineer,friend,College buddy,2025-11-15\n"
        "Jane Doe,BigCorp,VP Product,former_colleague,Worked together at Google,2025-10-01\n"
    )

    resp = await client.post(
        "/api/v1/contacts/upload",
        headers=auth["headers"],
        files={"file": ("contacts.csv", io.BytesIO(manual_csv.encode()), "text/csv")},
    )
    assert resp.status_code == 201

    contacts_resp = await client.get(
        "/api/v1/contacts",
        headers=auth["headers"],
        params={"per_page": 100},
    )
    contacts = contacts_resp.json()["data"]
    assert len(contacts) == 2

    john = next(c for c in contacts if "John" in c["full_name"])
    assert john["source"] == "manual"
    assert john["relationship_type"] == "friend"

    jane = next(c for c in contacts if "Jane" in c["full_name"])
    assert jane["relationship_type"] == "former_colleague"
