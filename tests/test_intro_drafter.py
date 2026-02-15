import io
from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.services.intro_drafter import (
    LINKEDIN_CHAR_LIMIT,
    _mock_drafts,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Stub:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _contact(**kwargs):
    defaults = {
        "first_name": "Alice",
        "last_name": "Smith",
        "full_name": "Alice Smith",
        "current_title": "VP of Engineering",
        "current_company": "Acme Corp",
        "location": "San Francisco",
    }
    defaults.update(kwargs)
    return _Stub(**defaults)


def _profile(**kwargs):
    defaults = {
        "current_title": "Founder",
        "current_company": "WarmPath",
        "industry": "SaaS",
        "location": "New York",
        "bio_summary": None,
    }
    defaults.update(kwargs)
    return _Stub(**defaults)


def _match_result(**kwargs):
    defaults = {
        "match_reasoning": "VP at target fintech company",
    }
    defaults.update(kwargs)
    return _Stub(**defaults)


SAMPLE_CSV = (
    "First Name,Last Name,Email Address,Company,Position,Connected On\n"
    "Alice,Smith,alice@example.com,Acme Corp,VP of Engineering,{recent}\n"
).format(
    recent=(date.today() - timedelta(days=30)).strftime("%d %b %Y"),
)


async def _signup_and_get_token(
    client: AsyncClient, email: str = "intro@example.com"
) -> str:
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "secret123", "full_name": "Intro User"},
    )
    return resp.json()["data"]["access_token"]


def _csv_file(content: str):
    return {
        "file": ("connections.csv", io.BytesIO(content.encode("utf-8")), "text/csv")
    }


# ---------------------------------------------------------------------------
# Unit tests — mock drafts
# ---------------------------------------------------------------------------


class TestMockDraftsLinkedIn:
    def test_generates_three_variants(self):
        drafts = _mock_drafts(_contact(), _profile(), None, "professional", "linkedin")
        assert len(drafts) == 3
        labels = [d.variant_label for d in drafts]
        assert "direct" in labels
        assert "mutual-interest" in labels
        assert "casual" in labels

    def test_linkedin_no_subject_line(self):
        drafts = _mock_drafts(_contact(), _profile(), None, "professional", "linkedin")
        for draft in drafts:
            assert draft.subject_line is None

    def test_linkedin_under_char_limit(self):
        drafts = _mock_drafts(_contact(), _profile(), None, "professional", "linkedin")
        for draft in drafts:
            assert len(draft.message_body) <= LINKEDIN_CHAR_LIMIT

    def test_includes_contact_name(self):
        drafts = _mock_drafts(_contact(), _profile(), None, "professional", "linkedin")
        for draft in drafts:
            assert "Alice" in draft.message_body

    def test_includes_contact_company(self):
        drafts = _mock_drafts(_contact(), _profile(), None, "professional", "linkedin")
        for draft in drafts:
            assert "Acme Corp" in draft.message_body

    def test_no_profile_still_works(self):
        drafts = _mock_drafts(_contact(), None, None, "professional", "linkedin")
        assert len(drafts) == 3
        for draft in drafts:
            assert len(draft.message_body) > 0

    def test_no_title_uses_fallback(self):
        contact = _contact(current_title=None)
        drafts = _mock_drafts(contact, _profile(), None, "professional", "linkedin")
        assert len(drafts) == 3
        # Should still generate messages without error
        assert all(len(d.message_body) > 0 for d in drafts)


class TestMockDraftsEmail:
    def test_generates_three_variants(self):
        drafts = _mock_drafts(_contact(), _profile(), None, "professional", "email")
        assert len(drafts) == 3

    def test_email_has_subject_lines(self):
        drafts = _mock_drafts(_contact(), _profile(), None, "professional", "email")
        for draft in drafts:
            assert draft.subject_line is not None
            assert len(draft.subject_line) > 0

    def test_email_body_longer_than_linkedin(self):
        linkedin_drafts = _mock_drafts(
            _contact(), _profile(), None, "professional", "linkedin"
        )
        email_drafts = _mock_drafts(
            _contact(), _profile(), None, "professional", "email"
        )
        # Email bodies should generally be longer
        linkedin_total = sum(len(d.message_body) for d in linkedin_drafts)
        email_total = sum(len(d.message_body) for d in email_drafts)
        assert email_total > linkedin_total

    def test_email_includes_match_context(self):
        match = _match_result()
        drafts = _mock_drafts(_contact(), _profile(), match, "professional", "email")
        # At least one draft should reference the match reasoning
        bodies = " ".join(d.message_body for d in drafts)
        assert "VP at target fintech company" in bodies


class TestMockDraftsEdgeCases:
    def test_missing_first_name_uses_full_name(self):
        contact = _contact(first_name=None, full_name="Alice Smith")
        drafts = _mock_drafts(contact, _profile(), None, "professional", "linkedin")
        assert all("Alice" in d.message_body for d in drafts)

    def test_missing_company_uses_fallback(self):
        contact = _contact(current_company=None)
        drafts = _mock_drafts(contact, _profile(), None, "professional", "linkedin")
        assert len(drafts) == 3
        # Should use "your company" fallback
        assert any("your company" in d.message_body for d in drafts)


# ---------------------------------------------------------------------------
# Integration tests — API endpoints
# ---------------------------------------------------------------------------


async def _upload_and_get_contact_id(client: AsyncClient, headers: dict) -> str:
    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )
    resp = await client.get("/api/v1/contacts", headers=headers)
    return resp.json()["data"][0]["id"]


async def test_create_intro_linkedin(client: AsyncClient):
    token = await _signup_and_get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    contact_id = await _upload_and_get_contact_id(client, headers)

    resp = await client.post(
        "/api/v1/matches/intros",
        headers=headers,
        json={"contact_id": contact_id, "channel": "linkedin"},
    )
    assert resp.status_code == 201
    body = resp.json()["data"]

    assert body["status"] == "completed"
    assert body["channel"] == "linkedin"
    assert len(body["messages"]) == 3

    labels = [m["variant_label"] for m in body["messages"]]
    assert "direct" in labels
    assert "mutual-interest" in labels
    assert "casual" in labels

    # LinkedIn messages should have no subject line
    for msg in body["messages"]:
        assert msg["subject_line"] is None

    # All under char limit
    for msg in body["messages"]:
        assert len(msg["message_body"]) <= LINKEDIN_CHAR_LIMIT


async def test_create_intro_email(client: AsyncClient):
    token = await _signup_and_get_token(client, email="email_intro@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    contact_id = await _upload_and_get_contact_id(client, headers)

    resp = await client.post(
        "/api/v1/matches/intros",
        headers=headers,
        json={"contact_id": contact_id, "channel": "email"},
    )
    assert resp.status_code == 201
    body = resp.json()["data"]

    assert len(body["messages"]) == 3
    for msg in body["messages"]:
        assert msg["subject_line"] is not None


async def test_get_intro(client: AsyncClient):
    token = await _signup_and_get_token(client, email="get_intro@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    contact_id = await _upload_and_get_contact_id(client, headers)

    create_resp = await client.post(
        "/api/v1/matches/intros",
        headers=headers,
        json={"contact_id": contact_id},
    )
    intro_id = create_resp.json()["data"]["id"]

    resp = await client.get(f"/api/v1/matches/intros/{intro_id}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["id"] == intro_id
    assert len(body["messages"]) == 3


async def test_get_nonexistent_intro(client: AsyncClient):
    token = await _signup_and_get_token(client, email="no_intro@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(
        "/api/v1/matches/intros/00000000-0000-0000-0000-000000000000",
        headers=headers,
    )
    assert resp.status_code == 404


async def test_select_message(client: AsyncClient):
    token = await _signup_and_get_token(client, email="select@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    contact_id = await _upload_and_get_contact_id(client, headers)

    create_resp = await client.post(
        "/api/v1/matches/intros",
        headers=headers,
        json={"contact_id": contact_id},
    )
    intro_id = create_resp.json()["data"]["id"]
    message_id = create_resp.json()["data"]["messages"][0]["id"]

    resp = await client.patch(
        f"/api/v1/matches/intros/{intro_id}/messages/{message_id}",
        headers=headers,
        json={"is_selected": True},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["is_selected"] is True


async def test_edit_message_body(client: AsyncClient):
    token = await _signup_and_get_token(client, email="edit@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    contact_id = await _upload_and_get_contact_id(client, headers)

    create_resp = await client.post(
        "/api/v1/matches/intros",
        headers=headers,
        json={"contact_id": contact_id},
    )
    intro_id = create_resp.json()["data"]["id"]
    message_id = create_resp.json()["data"]["messages"][0]["id"]

    custom_body = "Hey Alice, I edited this message myself!"
    resp = await client.patch(
        f"/api/v1/matches/intros/{intro_id}/messages/{message_id}",
        headers=headers,
        json={"user_edited_body": custom_body, "is_selected": True},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["user_edited_body"] == custom_body
    assert resp.json()["data"]["is_selected"] is True


async def test_select_and_edit_persists(client: AsyncClient):
    """Changes should be visible when re-fetching the intro."""
    token = await _signup_and_get_token(client, email="persist@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    contact_id = await _upload_and_get_contact_id(client, headers)

    create_resp = await client.post(
        "/api/v1/matches/intros",
        headers=headers,
        json={"contact_id": contact_id},
    )
    intro_id = create_resp.json()["data"]["id"]
    message_id = create_resp.json()["data"]["messages"][1]["id"]

    await client.patch(
        f"/api/v1/matches/intros/{intro_id}/messages/{message_id}",
        headers=headers,
        json={"is_selected": True, "user_edited_body": "Custom text"},
    )

    # Re-fetch the intro and check
    resp = await client.get(f"/api/v1/matches/intros/{intro_id}", headers=headers)
    messages = resp.json()["data"]["messages"]
    selected = [m for m in messages if m["is_selected"]]
    assert len(selected) == 1
    assert selected[0]["user_edited_body"] == "Custom text"


async def test_intro_for_nonexistent_contact(client: AsyncClient):
    token = await _signup_and_get_token(client, email="nocontact@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/v1/matches/intros",
        headers=headers,
        json={"contact_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 404


async def test_intro_user_scoped(client: AsyncClient):
    """User B cannot view User A's intros."""
    token_a = await _signup_and_get_token(client, email="ia@example.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    contact_id = await _upload_and_get_contact_id(client, headers_a)

    create_resp = await client.post(
        "/api/v1/matches/intros",
        headers=headers_a,
        json={"contact_id": contact_id},
    )
    intro_id = create_resp.json()["data"]["id"]

    token_b = await _signup_and_get_token(client, email="ib@example.com")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    resp = await client.get(f"/api/v1/matches/intros/{intro_id}", headers=headers_b)
    assert resp.status_code == 404


async def test_intro_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/matches/intros",
        json={"contact_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code in (401, 403)


async def test_patch_nonexistent_message(client: AsyncClient):
    token = await _signup_and_get_token(client, email="nomsg@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    contact_id = await _upload_and_get_contact_id(client, headers)

    create_resp = await client.post(
        "/api/v1/matches/intros",
        headers=headers,
        json={"contact_id": contact_id},
    )
    intro_id = create_resp.json()["data"]["id"]

    resp = await client.patch(
        f"/api/v1/matches/intros/{intro_id}/messages/00000000-0000-0000-0000-000000000000",
        headers=headers,
        json={"is_selected": True},
    )
    assert resp.status_code == 404
