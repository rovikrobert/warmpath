import io
from datetime import date, timedelta

from httpx import AsyncClient

from app.services.intro_drafter import (
    LINKEDIN_CHAR_LIMIT,
    _mock_referral_drafts,
)


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
        "cultural_context": {
            "approach_style": "direct",
            "cultural_notes": "Based in San Francisco. Direct approach works well.",
            "warm_up_suggested": False,
            "message_sequence": ["direct_ask"],
        },
    }
    defaults.update(kwargs)
    return _Stub(**defaults)


def _job_opening(**kwargs):
    defaults = {
        "title": "Senior Engineer",
        "department": "Engineering",
        "location": "San Francisco",
        "is_remote": False,
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
        json={"email": email, "password": "Secret123", "full_name": "Intro User"},
    )
    return resp.json()["data"]["access_token"]


def _csv_file(content: str):
    return {
        "file": ("connections.csv", io.BytesIO(content.encode("utf-8")), "text/csv")
    }


# ---------------------------------------------------------------------------
# Unit tests — Direct Ask sequence (US-based, direct approach)
# ---------------------------------------------------------------------------


class TestDirectAskSequence:
    def test_generates_three_variants(self):
        drafts = _mock_referral_drafts(
            _contact(), _profile(), _match_result(), None, "linkedin"
        )
        assert len(drafts) == 3

    def test_all_step_one(self):
        drafts = _mock_referral_drafts(
            _contact(), _profile(), _match_result(), None, "linkedin"
        )
        assert all(d.sequence_step == 1 for d in drafts)

    def test_all_referral_ask_label(self):
        drafts = _mock_referral_drafts(
            _contact(), _profile(), _match_result(), None, "linkedin"
        )
        assert all(d.step_label == "referral_ask" for d in drafts)

    def test_variant_labels(self):
        drafts = _mock_referral_drafts(
            _contact(), _profile(), _match_result(), None, "linkedin"
        )
        labels = {d.variant_label for d in drafts}
        assert labels == {"confident", "value-led", "casual"}

    def test_all_send_after_zero(self):
        drafts = _mock_referral_drafts(
            _contact(), _profile(), _match_result(), None, "linkedin"
        )
        assert all(d.send_after_days == 0 for d in drafts)


# ---------------------------------------------------------------------------
# Unit tests — Reconnect + Ask sequence (Europe, formal-indirect)
# ---------------------------------------------------------------------------


class TestReconnectAskSequence:
    def _europe_match(self):
        return _match_result(
            cultural_context={
                "approach_style": "formal-indirect",
                "cultural_notes": "Based in Berlin. Professional, formal approach.",
                "warm_up_suggested": False,
                "message_sequence": ["reconnect", "ask"],
            }
        )

    def test_generates_two_messages(self):
        drafts = _mock_referral_drafts(
            _contact(), _profile(), self._europe_match(), None, "linkedin"
        )
        assert len(drafts) == 2

    def test_correct_steps(self):
        drafts = _mock_referral_drafts(
            _contact(), _profile(), self._europe_match(), None, "linkedin"
        )
        assert drafts[0].sequence_step == 1
        assert drafts[1].sequence_step == 2

    def test_correct_step_labels(self):
        drafts = _mock_referral_drafts(
            _contact(), _profile(), self._europe_match(), None, "linkedin"
        )
        assert drafts[0].step_label == "reconnect"
        assert drafts[1].step_label == "referral_ask"

    def test_correct_delays(self):
        drafts = _mock_referral_drafts(
            _contact(), _profile(), self._europe_match(), None, "linkedin"
        )
        assert drafts[0].send_after_days == 0
        assert drafts[1].send_after_days == 3

    def test_all_variant_only(self):
        drafts = _mock_referral_drafts(
            _contact(), _profile(), self._europe_match(), None, "linkedin"
        )
        assert all(d.variant_label == "only" for d in drafts)


# ---------------------------------------------------------------------------
# Unit tests — Relationship-First sequence (Asia, 3-step)
# ---------------------------------------------------------------------------


class TestRelationshipFirstSequence:
    def _asia_match(self):
        return _match_result(
            cultural_context={
                "approach_style": "relationship-first",
                "cultural_notes": "Based in Tokyo. Build relationship before asking.",
                "warm_up_suggested": True,
                "message_sequence": ["reconnect", "explore", "ask"],
            }
        )

    def test_generates_three_messages(self):
        drafts = _mock_referral_drafts(
            _contact(), _profile(), self._asia_match(), None, "linkedin"
        )
        assert len(drafts) == 3

    def test_correct_steps(self):
        drafts = _mock_referral_drafts(
            _contact(), _profile(), self._asia_match(), None, "linkedin"
        )
        assert [d.sequence_step for d in drafts] == [1, 2, 3]

    def test_correct_step_labels(self):
        drafts = _mock_referral_drafts(
            _contact(), _profile(), self._asia_match(), None, "linkedin"
        )
        assert [d.step_label for d in drafts] == [
            "reconnect",
            "explore",
            "referral_ask",
        ]

    def test_correct_delays(self):
        drafts = _mock_referral_drafts(
            _contact(), _profile(), self._asia_match(), None, "linkedin"
        )
        assert [d.send_after_days for d in drafts] == [0, 5, 10]

    def test_all_variant_only(self):
        drafts = _mock_referral_drafts(
            _contact(), _profile(), self._asia_match(), None, "linkedin"
        )
        assert all(d.variant_label == "only" for d in drafts)


# ---------------------------------------------------------------------------
# Unit tests — Referral-focused content
# ---------------------------------------------------------------------------


class TestReferralContent:
    def test_mentions_referral_keyword(self):
        """Messages should use referral language, not generic networking."""
        drafts = _mock_referral_drafts(
            _contact(), _profile(), _match_result(), None, "linkedin"
        )
        all_bodies = " ".join(d.message_body.lower() for d in drafts)
        assert "refer" in all_bodies

    def test_mentions_job_title_when_provided(self):
        job = _job_opening(title="Senior Engineer")
        drafts = _mock_referral_drafts(
            _contact(), _profile(), _match_result(), job, "linkedin"
        )
        all_bodies = " ".join(d.message_body for d in drafts)
        assert "Senior Engineer" in all_bodies

    def test_mentions_contact_company(self):
        drafts = _mock_referral_drafts(
            _contact(), _profile(), _match_result(), None, "linkedin"
        )
        all_bodies = " ".join(d.message_body for d in drafts)
        assert "Acme Corp" in all_bodies

    def test_mentions_contact_name(self):
        drafts = _mock_referral_drafts(
            _contact(), _profile(), _match_result(), None, "linkedin"
        )
        assert all("Alice" in d.message_body for d in drafts)

    def test_no_generic_lets_connect(self):
        """Should NOT use generic networking language."""
        drafts = _mock_referral_drafts(
            _contact(), _profile(), _match_result(), None, "linkedin"
        )
        all_bodies = " ".join(d.message_body.lower() for d in drafts)
        assert "let's connect" not in all_bodies
        assert "pick your brain" not in all_bodies


# ---------------------------------------------------------------------------
# Unit tests — LinkedIn character limit
# ---------------------------------------------------------------------------


class TestLinkedInCharLimit:
    def test_direct_ask_under_limit(self):
        drafts = _mock_referral_drafts(
            _contact(), _profile(), _match_result(), None, "linkedin"
        )
        for draft in drafts:
            assert len(draft.message_body) <= LINKEDIN_CHAR_LIMIT

    def test_reconnect_ask_under_limit(self):
        match = _match_result(
            cultural_context={
                "approach_style": "formal-indirect",
                "cultural_notes": "Professional approach.",
                "warm_up_suggested": False,
                "message_sequence": ["reconnect", "ask"],
            }
        )
        drafts = _mock_referral_drafts(_contact(), _profile(), match, None, "linkedin")
        for draft in drafts:
            assert len(draft.message_body) <= LINKEDIN_CHAR_LIMIT

    def test_relationship_first_under_limit(self):
        match = _match_result(
            cultural_context={
                "approach_style": "relationship-first",
                "cultural_notes": "Build relationship first.",
                "warm_up_suggested": True,
                "message_sequence": ["reconnect", "explore", "ask"],
            }
        )
        drafts = _mock_referral_drafts(_contact(), _profile(), match, None, "linkedin")
        for draft in drafts:
            assert len(draft.message_body) <= LINKEDIN_CHAR_LIMIT

    def test_linkedin_no_subject_line(self):
        drafts = _mock_referral_drafts(
            _contact(), _profile(), _match_result(), None, "linkedin"
        )
        for draft in drafts:
            assert draft.subject_line is None


# ---------------------------------------------------------------------------
# Unit tests — Email has subject lines
# ---------------------------------------------------------------------------


class TestEmailHasSubjectLines:
    def test_direct_ask_email_subjects(self):
        drafts = _mock_referral_drafts(
            _contact(), _profile(), _match_result(), None, "email"
        )
        for draft in drafts:
            assert draft.subject_line is not None
            assert len(draft.subject_line) > 0

    def test_reconnect_ask_email_subjects(self):
        match = _match_result(
            cultural_context={
                "approach_style": "formal-indirect",
                "cultural_notes": "Formal approach.",
                "warm_up_suggested": False,
                "message_sequence": ["reconnect", "ask"],
            }
        )
        drafts = _mock_referral_drafts(_contact(), _profile(), match, None, "email")
        for draft in drafts:
            assert draft.subject_line is not None


# ---------------------------------------------------------------------------
# Unit tests — Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_no_match_result_defaults_to_direct_ask(self):
        """Without a match result, should default to direct_ask sequence."""
        drafts = _mock_referral_drafts(_contact(), _profile(), None, None, "linkedin")
        assert len(drafts) == 3
        assert all(d.step_label == "referral_ask" for d in drafts)

    def test_no_job_opening_still_works(self):
        drafts = _mock_referral_drafts(
            _contact(), _profile(), _match_result(), None, "linkedin"
        )
        assert len(drafts) == 3
        all_bodies = " ".join(d.message_body for d in drafts)
        assert "a role at Acme Corp" in all_bodies

    def test_no_profile_still_works(self):
        drafts = _mock_referral_drafts(
            _contact(), None, _match_result(), None, "linkedin"
        )
        assert len(drafts) == 3
        assert all(len(d.message_body) > 0 for d in drafts)

    def test_missing_first_name_uses_full_name(self):
        contact = _contact(first_name=None, full_name="Alice Smith")
        drafts = _mock_referral_drafts(
            contact, _profile(), _match_result(), None, "linkedin"
        )
        assert all("Alice" in d.message_body for d in drafts)

    def test_missing_company_uses_fallback(self):
        contact = _contact(current_company=None)
        drafts = _mock_referral_drafts(
            contact, _profile(), _match_result(), None, "linkedin"
        )
        assert len(drafts) == 3

    def test_match_result_without_cultural_context(self):
        match = _match_result(cultural_context=None)
        drafts = _mock_referral_drafts(_contact(), _profile(), match, None, "linkedin")
        # Should default to direct_ask
        assert len(drafts) == 3
        assert all(d.step_label == "referral_ask" for d in drafts)


# ---------------------------------------------------------------------------
# Unit tests — Coaching notes
# ---------------------------------------------------------------------------


class TestCoachingNotes:
    def test_coaching_notes_populated(self):
        drafts = _mock_referral_drafts(
            _contact(), _profile(), _match_result(), None, "linkedin"
        )
        for draft in drafts:
            assert draft.coaching_notes is not None
            assert len(draft.coaching_notes) > 0

    def test_coaching_notes_include_cultural_context(self):
        match = _match_result(
            cultural_context={
                "approach_style": "direct",
                "cultural_notes": "Based in San Francisco. Direct approach works well.",
                "warm_up_suggested": False,
                "message_sequence": ["direct_ask"],
            }
        )
        drafts = _mock_referral_drafts(_contact(), _profile(), match, None, "linkedin")
        all_coaching = " ".join(d.coaching_notes for d in drafts)
        assert "San Francisco" in all_coaching

    def test_multi_step_has_distinct_coaching(self):
        match = _match_result(
            cultural_context={
                "approach_style": "relationship-first",
                "cultural_notes": "Build relationship first.",
                "warm_up_suggested": True,
                "message_sequence": ["reconnect", "explore", "ask"],
            }
        )
        drafts = _mock_referral_drafts(_contact(), _profile(), match, None, "linkedin")
        # Each step should have different coaching
        coaching_set = {d.coaching_notes for d in drafts}
        assert len(coaching_set) == 3


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
    assert "confident" in labels
    assert "value-led" in labels
    assert "casual" in labels

    # New fields present
    for msg in body["messages"]:
        assert msg["sequence_step"] == 1
        assert msg["step_label"] == "referral_ask"
        assert msg["send_after_days"] == 0
        assert msg["coaching_notes"] is not None

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
        assert msg["sequence_step"] is not None
        assert msg["step_label"] is not None


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
    # New fields in response
    assert body["job_opening_id"] is None
    for msg in body["messages"]:
        assert "sequence_step" in msg
        assert "step_label" in msg
        assert "send_after_days" in msg
        assert "coaching_notes" in msg


async def test_get_pending_intros(client: AsyncClient):
    token = await _signup_and_get_token(client, email="pending@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    contact_id = await _upload_and_get_contact_id(client, headers)

    # Create an intro (direct_ask — all send_after_days=0, so all are immediately due)
    await client.post(
        "/api/v1/matches/intros",
        headers=headers,
        json={"contact_id": contact_id},
    )

    resp = await client.get("/api/v1/matches/intros/pending", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["count"] == 3
    assert len(body["data"]) == 3
    for msg in body["data"]:
        assert "intro_request_id" in msg
        assert "contact_id" in msg
        assert "due_date" in msg


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
    # New fields should be present in PATCH response too
    assert resp.json()["data"]["sequence_step"] is not None


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
    assert create_resp.status_code == 201
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
    assert create_resp.status_code == 201
    intro_id = create_resp.json()["data"]["id"]

    resp = await client.patch(
        f"/api/v1/matches/intros/{intro_id}/messages/00000000-0000-0000-0000-000000000000",
        headers=headers,
        json={"is_selected": True},
    )
    assert resp.status_code == 404


async def test_pending_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/matches/intros/pending")
    assert resp.status_code in (401, 403)
