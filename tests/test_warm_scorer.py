import io
from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.services.warm_scorer import (
    compute_recency_score,
    compute_role_score,
    compute_context_score,
    compute_tenu[RESEND_KEY_REDACTED],
    compute_warm_score,
    WEIGHT_RECENCY,
    WEIGHT_CONTEXT,
    WEIGHT_ROLE,
    WEIGHT_TENURE,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers for building stub objects
# ---------------------------------------------------------------------------


class _Stub:
    """Lightweight attribute bag for testing without touching the DB."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _contact(**kwargs):
    defaults = {
        "connected_on": None,
        "current_title": None,
        "current_company": None,
        "location": None,
    }
    defaults.update(kwargs)
    return _Stub(**defaults)


def _profile(**kwargs):
    defaults = {
        "current_company": None,
        "industry": None,
        "location": None,
    }
    defaults.update(kwargs)
    return _Stub(**defaults)


# ---------------------------------------------------------------------------
# Unit tests — Recency Score
# ---------------------------------------------------------------------------


class TestRecencyScore:
    def test_connected_recently(self):
        recent = date.today() - timedelta(days=30)
        assert compute_recency_score(recent) == 100.0

    def test_connected_6_months(self):
        d = date.today() - timedelta(days=200)
        assert compute_recency_score(d) == 80.0

    def test_connected_1_year(self):
        d = date.today() - timedelta(days=400)
        assert compute_recency_score(d) == 60.0

    def test_connected_3_years(self):
        d = date.today() - timedelta(days=1100)
        assert compute_recency_score(d) == 40.0

    def test_connected_6_years(self):
        d = date.today() - timedelta(days=2200)
        assert compute_recency_score(d) == 20.0

    def test_unknown_date(self):
        assert compute_recency_score(None) == 30.0


# ---------------------------------------------------------------------------
# Unit tests — Context Score
# ---------------------------------------------------------------------------


class TestContextScore:
    def test_same_company(self):
        contact = _contact(current_company="Acme Corp")
        profile = _profile(current_company="Acme Corp")
        score, factors = compute_context_score(contact, profile)
        assert score == 40.0
        assert factors["same_company"] is True

    def test_same_company_case_insensitive(self):
        contact = _contact(current_company="acme corp")
        profile = _profile(current_company="ACME CORP")
        score, _ = compute_context_score(contact, profile)
        assert score == 40.0

    def test_same_location(self):
        contact = _contact(location="San Francisco")
        profile = _profile(location="San Francisco")
        score, factors = compute_context_score(contact, profile)
        assert score == 20.0
        assert factors["same_location"] is True

    def test_same_company_and_location(self):
        contact = _contact(current_company="Acme", location="NYC")
        profile = _profile(current_company="Acme", location="NYC")
        score, _ = compute_context_score(contact, profile)
        assert score == 60.0  # 40 + 20

    def test_capped_at_100(self):
        # Even with all bonuses, should not exceed 100
        contact = _contact(current_company="Acme", location="NYC")
        profile = _profile(current_company="Acme", location="NYC")
        score, _ = compute_context_score(contact, profile)
        assert score <= 100.0

    def test_no_profile(self):
        contact = _contact(current_company="Acme")
        score, factors = compute_context_score(contact, None)
        assert score == 0.0
        assert "no connector profile" in factors.get("reason", "")

    def test_no_shared_context(self):
        contact = _contact(current_company="Foo", location="London")
        profile = _profile(current_company="Bar", location="Tokyo")
        score, _ = compute_context_score(contact, profile)
        assert score == 0.0


# ---------------------------------------------------------------------------
# Unit tests — Role Score
# ---------------------------------------------------------------------------


class TestRoleScore:
    def test_ceo(self):
        assert compute_role_score("CEO") == 100.0

    def test_cto(self):
        assert compute_role_score("CTO") == 100.0

    def test_cfo(self):
        assert compute_role_score("CFO") == 100.0

    def test_founder(self):
        assert compute_role_score("Co-Founder & CEO") == 100.0

    def test_chief_officer(self):
        assert compute_role_score("Chief Revenue Officer") == 100.0

    def test_president(self):
        assert compute_role_score("President") == 100.0

    def test_vp(self):
        assert compute_role_score("VP of Engineering") == 85.0

    def test_svp(self):
        assert compute_role_score("SVP, Sales") == 85.0

    def test_vice_president(self):
        assert compute_role_score("Vice President of Marketing") == 85.0

    def test_director(self):
        assert compute_role_score("Director of Product") == 70.0

    def test_manager(self):
        assert compute_role_score("Engineering Manager") == 55.0

    def test_head_of(self):
        assert compute_role_score("Head of Design") == 55.0

    def test_team_lead(self):
        assert compute_role_score("Team Lead") == 55.0

    def test_principal(self):
        assert compute_role_score("Principal Engineer") == 55.0

    def test_senior(self):
        assert compute_role_score("Senior Software Engineer") == 40.0

    def test_staff(self):
        assert compute_role_score("Staff Engineer") == 40.0

    def test_sr_abbreviation(self):
        assert compute_role_score("Sr. Analyst") == 40.0

    def test_ic(self):
        assert compute_role_score("Software Engineer") == 25.0

    def test_associate(self):
        assert compute_role_score("Associate") == 25.0

    def test_unknown_title(self):
        assert compute_role_score(None) == 30.0

    def test_empty_title(self):
        assert compute_role_score("") == 30.0


# ---------------------------------------------------------------------------
# Unit tests — Tenure Score
# ---------------------------------------------------------------------------


class TestTenureScore:
    def test_default(self):
        assert compute_tenu[RESEND_KEY_REDACTED]() == 50.0


# ---------------------------------------------------------------------------
# Unit tests — Composite warm_score
# ---------------------------------------------------------------------------


class TestComputeWarmScore:
    def test_weights_sum_to_one(self):
        assert (
            abs(WEIGHT_RECENCY + WEIGHT_CONTEXT + WEIGHT_ROLE + WEIGHT_TENURE - 1.0)
            < 0.001
        )

    def test_basic_computation(self):
        contact = _contact(
            connected_on=date.today() - timedelta(days=30),  # recency=100
            current_title="CEO",  # role=100
            current_company="Acme",
            location=None,
        )
        profile = _profile(current_company="Acme")  # context=40 (same company)
        result = compute_warm_score(contact, profile)

        expected = (100 * 0.30) + (40 * 0.30) + (100 * 0.25) + (50 * 0.15)
        assert result.total_score == round(expected, 2)
        assert result.recency_score == 100.0
        assert result.context_score == 40.0
        assert result.role_score == 100.0
        assert result.tenu[RESEND_KEY_REDACTED] == 50.0

    def test_high_sco[RESEND_KEY_REDACTED](self):
        """Recently-connected C-suite at same company should score high."""
        contact = _contact(
            connected_on=date.today() - timedelta(days=10),  # 100
            current_title="CEO",  # 100
            current_company="MyCompany",
            location="SF",
        )
        profile = _profile(current_company="MyCompany", location="SF")  # 40+20=60
        result = compute_warm_score(contact, profile)

        # (100*0.30) + (60*0.30) + (100*0.25) + (50*0.15) = 30+18+25+7.5 = 80.5
        assert result.total_score == 80.5

    def test_low_sco[RESEND_KEY_REDACTED](self):
        """5-year-old IC connection at unknown company should score low."""
        contact = _contact(
            connected_on=date.today() - timedelta(days=2000),  # 20
            current_title="Analyst",  # 25
            current_company="Unknown Corp",
            location="London",
        )
        profile = _profile(current_company="Different Co", location="Tokyo")  # 0
        result = compute_warm_score(contact, profile)

        # (20*0.30) + (0*0.30) + (25*0.25) + (50*0.15) = 6+0+6.25+7.5 = 19.75
        assert result.total_score == 19.75

    def test_high_beats_low(self):
        """Sanity check: the high-score scenario beats the low-score one."""
        high_contact = _contact(
            connected_on=date.today() - timedelta(days=10),
            current_title="CEO",
            current_company="MyCompany",
            location="SF",
        )
        low_contact = _contact(
            connected_on=date.today() - timedelta(days=2000),
            current_title="Analyst",
            current_company="Unknown",
            location="London",
        )
        profile = _profile(current_company="MyCompany", location="SF")

        high = compute_warm_score(high_contact, profile)
        low = compute_warm_score(low_contact, profile)
        assert high.total_score > low.total_score

    def test_no_profile_no_connected_on(self):
        """All defaults: no profile, no date, no title."""
        contact = _contact()
        result = compute_warm_score(contact, None)

        # (30*0.30) + (0*0.30) + (30*0.25) + (50*0.15) = 9+0+7.5+7.5 = 24.0
        assert result.total_score == 24.0

    def test_sco[RESEND_KEY_REDACTED](self):
        contact = _contact(connected_on=date.today(), current_title="VP Sales")
        result = compute_warm_score(contact, None)
        assert "recency" in result.factors
        assert "context" in result.factors
        assert "role" in result.factors
        assert "tenure" in result.factors
        assert result.factors["role"]["title"] == "VP Sales"

    def test_sco[RESEND_KEY_REDACTED](self):
        contact = _contact(
            connected_on=date.today(),
            current_title="CEO",
            current_company="Same",
            location="Same",
        )
        profile = _profile(current_company="Same", location="Same")
        result = compute_warm_score(contact, profile)
        assert result.total_score <= 100.0


# ---------------------------------------------------------------------------
# Integration tests — API endpoints
# ---------------------------------------------------------------------------

SAMPLE_CSV = (
    "First Name,Last Name,Email Address,Company,Position,Connected On\n"
    "Alice,Smith,alice@example.com,Acme Corp,CEO,{recent}\n"
    "Bob,Jones,bob@example.com,Other Inc,Analyst,{old}\n"
).format(
    recent=(date.today() - timedelta(days=30)).strftime("%d %b %Y"),
    old=(date.today() - timedelta(days=2000)).strftime("%d %b %Y"),
)


async def _signup_and_get_token(
    client: AsyncClient, email: str = "ws@example.com"
) -> str:
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "secret123", "full_name": "WS User"},
    )
    return resp.json()["data"]["access_token"]


def _csv_file(content: str):
    return {
        "file": ("connections.csv", io.BytesIO(content.encode("utf-8")), "text/csv")
    }


async def test_upload_auto_computes_scores(client: AsyncClient):
    token = await _signup_and_get_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )

    resp = await client.get("/api/v1/contacts", headers=headers)
    body = resp.json()
    scores = [c["warm_score"] for c in body["data"]]
    assert all(s is not None for s in scores)
    assert all(0 <= s <= 100 for s in scores)


async def test_compute_scores_endpoint(client: AsyncClient):
    token = await _signup_and_get_token(client, email="compute@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )

    resp = await client.post("/api/v1/contacts/compute-scores", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["scores_computed"] == 2


async def test_sort_by_warm_score(client: AsyncClient):
    token = await _signup_and_get_token(client, email="sort@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )

    # Sort desc — highest score first
    resp = await client.get(
        "/api/v1/contacts?sort_by=warm_score&sort_order=desc", headers=headers
    )
    body = resp.json()
    scores = [c["warm_score"] for c in body["data"]]
    assert scores == sorted(scores, reverse=True)

    # CEO with recent connection should be first
    assert body["data"][0]["current_title"] == "CEO"


async def test_single_contact_includes_warm_score(client: AsyncClient):
    token = await _signup_and_get_token(client, email="single@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )

    list_resp = await client.get("/api/v1/contacts", headers=headers)
    contact_id = list_resp.json()["data"][0]["id"]

    resp = await client.get(f"/api/v1/contacts/{contact_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["warm_score"] is not None


async def test_compute_scores_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/contacts/compute-scores")
    assert resp.status_code in (401, 403)
