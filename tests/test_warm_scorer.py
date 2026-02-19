import io
from datetime import date, timedelta

from httpx import AsyncClient

from app.services.warm_scorer import (
    WEIGHT_RECENCY,
    WEIGHT_RELATIONSHIP,
    WEIGHT_ROLE,
    WEIGHT_TENURE,
    compute_recency_score,
    compute_referral_score,
    compute_relationship_score,
    compute_role_score,
    compute_tenu[RESEND_KEY_REDACTED],
    compute_warm_score,
)
from tests.conftest import TestSessionLocal, create_test_user_in_db


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
        "enriched_data": None,
        "company": None,
    }
    defaults.update(kwargs)
    return _Stub(**defaults)


def _profile(**kwargs):
    defaults = {
        "current_company": None,
        "industry": None,
        "location": None,
        "bio_summary": None,
    }
    defaults.update(kwargs)
    return _Stub(**defaults)


# ---------------------------------------------------------------------------
# Unit tests — Recency Score (weight: 35%)
# ---------------------------------------------------------------------------


class TestRecencyScore:
    def test_connected_recently(self):
        recent = date.today() - timedelta(days=30)
        assert compute_recency_score(recent) == 100.0

    def test_connected_6_to_12_months(self):
        d = date.today() - timedelta(days=200)
        assert compute_recency_score(d) == 85.0

    def test_connected_1_to_2_years(self):
        d = date.today() - timedelta(days=400)
        assert compute_recency_score(d) == 70.0

    def test_connected_2_to_3_years(self):
        d = date.today() - timedelta(days=900)
        assert compute_recency_score(d) == 55.0

    def test_connected_3_to_5_years(self):
        d = date.today() - timedelta(days=1400)
        assert compute_recency_score(d) == 35.0

    def test_connected_5_plus_years(self):
        d = date.today() - timedelta(days=2200)
        assert compute_recency_score(d) == 15.0

    def test_unknown_date(self):
        assert compute_recency_score(None) == 30.0


# ---------------------------------------------------------------------------
# Unit tests — Relationship Score (weight: 30%)
# ---------------------------------------------------------------------------


class TestRelationshipScore:
    def test_same_company(self):
        contact = _contact(current_company="Acme Corp")
        profile = _profile(current_company="Acme Corp")
        score, factors = compute_relationship_score(contact, profile)
        assert score == 35.0
        assert factors["same_company"] is True

    def test_same_company_case_insensitive(self):
        contact = _contact(current_company="acme corp")
        profile = _profile(current_company="ACME CORP")
        score, _ = compute_relationship_score(contact, profile)
        assert score == 35.0

    def test_same_location(self):
        contact = _contact(location="San Francisco")
        profile = _profile(location="San Francisco")
        score, factors = compute_relationship_score(contact, profile)
        assert score == 15.0
        assert factors["same_location"] is True

    def test_same_company_and_location(self):
        contact = _contact(current_company="Acme", location="NYC")
        profile = _profile(current_company="Acme", location="NYC")
        score, _ = compute_relationship_score(contact, profile)
        assert score == 50.0  # 35 + 15

    def test_former_colleague(self):
        contact = _contact(
            enriched_data={"work_history": [{"company": "Acme Corp"}]},
        )
        profile = _profile(current_company="Acme Corp")
        score, factors = compute_relationship_score(contact, profile)
        assert factors["former_colleague"] is True
        assert score >= 40.0

    def test_capped_at_100(self):
        contact = _contact(
            current_company="Acme",
            location="NYC",
            enriched_data={"work_history": [{"company": "Acme"}]},
        )
        profile = _profile(current_company="Acme", location="NYC")
        score, _ = compute_relationship_score(contact, profile)
        assert score <= 100.0

    def test_no_profile(self):
        contact = _contact(current_company="Acme")
        score, factors = compute_relationship_score(contact, None)
        assert score == 0.0
        assert "no connector profile" in factors.get("reason", "")

    def test_no_shared_context(self):
        contact = _contact(current_company="Foo", location="London")
        profile = _profile(current_company="Bar", location="Tokyo")
        score, _ = compute_relationship_score(contact, profile)
        assert score == 0.0


# ---------------------------------------------------------------------------
# Unit tests — Role Score (weight: 20%)
# ---------------------------------------------------------------------------


class TestRoleScore:
    # --- Without target_role (fallback seniority scoring) ---
    def test_manager_no_target(self):
        assert compute_role_score("Engineering Manager") == 60.0

    def test_director_no_target(self):
        assert compute_role_score("Director of Product") == 60.0

    def test_senior_no_target(self):
        assert compute_role_score("Senior Software Engineer") == 55.0

    def test_vp_no_target(self):
        assert compute_role_score("VP of Engineering") == 50.0

    def test_csuite_no_target(self):
        """C-suite scores LOW for referrals — they won't bother."""
        assert compute_role_score("CEO") == 40.0

    def test_cto_no_target(self):
        assert compute_role_score("CTO") == 40.0

    def test_founder_no_target(self):
        assert compute_role_score("Co-Founder & CEO") == 40.0

    def test_ic_no_target(self):
        assert compute_role_score("Software Engineer") == 20.0

    def test_unknown_title(self):
        assert compute_role_score(None) == 30.0

    def test_empty_title(self):
        assert compute_role_score("") == 30.0

    # --- With target_role (department-aware scoring) ---
    def test_same_dept_senior_ic(self):
        """Senior IC in same dept is the best referrer."""
        assert (
            compute_role_score(
                "Senior Software Engineer", target_role="Software Engineer"
            )
            == 100.0
        )

    def test_same_dept_manager(self):
        assert (
            compute_role_score("Engineering Manager", target_role="Software Engineer")
            == 100.0
        )

    def test_same_dept_director(self):
        assert (
            compute_role_score(
                "Director of Engineering", target_role="Software Engineer"
            )
            == 95.0
        )

    def test_same_dept_ic(self):
        """Regular IC in same dept still scores well."""
        assert (
            compute_role_score("Software Developer", target_role="Software Engineer")
            == 80.0
        )

    def test_adjacent_dept(self):
        """Product Manager referring for an eng role."""
        assert (
            compute_role_score("Product Manager", target_role="Software Engineer")
            == 70.0
        )

    def test_csuite_still_low_with_target(self):
        """CEO doesn't get boosted even with a target role (no dept match)."""
        assert compute_role_score("CEO", target_role="Software Engineer") == 40.0


# ---------------------------------------------------------------------------
# Unit tests — Tenure Score (weight: 15%)
# ---------------------------------------------------------------------------


class TestTenureScore:
    def test_unknown_tenure(self):
        assert compute_tenu[RESEND_KEY_REDACTED](None) == 50.0

    def test_new_hire(self):
        assert compute_tenu[RESEND_KEY_REDACTED](3) == 40.0

    def test_6_to_12_months(self):
        assert compute_tenu[RESEND_KEY_REDACTED](9) == 70.0

    def test_sweet_spot_1_to_3_years(self):
        assert compute_tenu[RESEND_KEY_REDACTED](24) == 100.0

    def test_3_to_5_years(self):
        assert compute_tenu[RESEND_KEY_REDACTED](48) == 85.0

    def test_5_plus_years(self):
        assert compute_tenu[RESEND_KEY_REDACTED](72) == 70.0


# ---------------------------------------------------------------------------
# Unit tests — Composite warm_score
# ---------------------------------------------------------------------------


class TestComputeWarmScore:
    def test_weights_sum_to_one(self):
        assert (
            abs(
                WEIGHT_RECENCY + WEIGHT_RELATIONSHIP + WEIGHT_ROLE + WEIGHT_TENURE - 1.0
            )
            < 0.001
        )

    def test_basic_computation(self):
        contact = _contact(
            connected_on=date.today() - timedelta(days=30),  # recency=100
            current_title="Engineering Manager",  # role=60 (no target)
            current_company="Acme",
            location=None,
        )
        profile = _profile(current_company="Acme")  # relationship=35 (same company)
        result = compute_warm_score(contact, profile)

        expected = (100 * 0.35) + (35 * 0.30) + (60 * 0.20) + (50 * 0.15)
        assert result.total_score == round(expected, 2)
        assert result.recency_score == 100.0
        assert result.relationship_score == 35.0
        assert result.role_score == 60.0
        assert result.tenu[RESEND_KEY_REDACTED] == 50.0

    def test_high_sco[RESEND_KEY_REDACTED](self):
        """Recently-connected senior peer at same company should score high."""
        contact = _contact(
            connected_on=date.today() - timedelta(days=10),  # 100
            current_title="Senior Software Engineer",  # 55 (no target), 100 (with target)
            current_company="MyCompany",
            location="SF",
        )
        profile = _profile(current_company="MyCompany", location="SF")  # 35+15=50
        result = compute_warm_score(contact, profile, target_role="Software Engineer")

        # recency=100, relationship=50, role=100 (same dept senior), tenure=50
        # (100*0.35)+(50*0.30)+(100*0.20)+(50*0.15) = 35+15+20+7.5 = 77.5
        assert result.total_score == 77.5

    def test_low_sco[RESEND_KEY_REDACTED](self):
        """5-year-old IC connection at unknown company should score low."""
        contact = _contact(
            connected_on=date.today() - timedelta(days=2200),  # 15
            current_title="Analyst",  # 20 (IC unrelated)
            current_company="Unknown Corp",
            location="London",
        )
        profile = _profile(current_company="Different Co", location="Tokyo")  # 0
        result = compute_warm_score(contact, profile)

        # (15*0.35)+(0*0.30)+(20*0.20)+(50*0.15) = 5.25+0+4+7.5 = 16.75
        assert result.total_score == 16.75

    def test_high_beats_low(self):
        """Sanity check: the high-score scenario beats the low-score one."""
        high_contact = _contact(
            connected_on=date.today() - timedelta(days=10),
            current_title="Senior Software Engineer",
            current_company="MyCompany",
            location="SF",
        )
        low_contact = _contact(
            connected_on=date.today() - timedelta(days=2200),
            current_title="Analyst",
            current_company="Unknown",
            location="London",
        )
        profile = _profile(current_company="MyCompany", location="SF")

        high = compute_warm_score(
            high_contact, profile, target_role="Software Engineer"
        )
        low = compute_warm_score(low_contact, profile)
        assert high.total_score > low.total_score

    def test_no_profile_no_connected_on(self):
        """All defaults: no profile, no date, no title."""
        contact = _contact()
        result = compute_warm_score(contact, None)

        # (30*0.35)+(0*0.30)+(30*0.20)+(50*0.15) = 10.5+0+6+7.5 = 24.0
        assert result.total_score == 24.0

    def test_sco[RESEND_KEY_REDACTED](self):
        contact = _contact(connected_on=date.today(), current_title="VP Sales")
        result = compute_warm_score(contact, None)
        assert "recency" in result.factors
        assert "relationship" in result.factors
        assert "role" in result.factors
        assert "tenure" in result.factors
        assert result.factors["role"]["title"] == "VP Sales"

    def test_sco[RESEND_KEY_REDACTED](self):
        contact = _contact(
            connected_on=date.today(),
            current_title="Senior Software Engineer",
            current_company="Same",
            location="Same",
        )
        profile = _profile(current_company="Same", location="Same")
        result = compute_warm_score(contact, profile, target_role="Software Engineer")
        assert result.total_score <= 100.0


# ---------------------------------------------------------------------------
# Unit tests — Referral Score
# ---------------------------------------------------------------------------


class TestReferralScore:
    def test_high_likelihood(self):
        contact = _contact(
            connected_on=date.today() - timedelta(days=10),
            current_title="Senior Software Engineer",
            current_company="TargetCo",
            location="SF",
        )
        profile = _profile(current_company="TargetCo", location="SF")
        result = compute_referral_score(
            contact, profile, target_role="Software Engineer"
        )
        assert result.referral_likelihood == "high"
        assert result.total_score >= 70

    def test_low_likelihood(self):
        contact = _contact(
            connected_on=date.today() - timedelta(days=2200),
            current_title="Analyst",
            current_company="Unknown",
        )
        profile = _profile(current_company="Different")
        result = compute_referral_score(contact, profile)
        assert result.referral_likelihood == "low"
        assert result.total_score < 45

    def test_medium_likelihood(self):
        contact = _contact(
            connected_on=date.today() - timedelta(days=400),  # 70
            current_title="Engineering Manager",  # 60
            current_company="Other",
            location="SF",
        )
        profile = _profile(current_company="Different", location="SF")  # 15
        result = compute_referral_score(contact, profile)
        assert result.referral_likelihood == "medium"


# ---------------------------------------------------------------------------
# NEW referral-specific tests
# ---------------------------------------------------------------------------


class TestReferralPriorities:
    def test_recent_peer_beats_old_csuite(self):
        """A recently-connected peer in the same department scores higher
        than a 5-year-old C-suite contact."""
        recent_peer = _contact(
            connected_on=date.today() - timedelta(days=60),  # recency=100
            current_title="Senior Software Engineer",  # same dept → 100
            current_company="TargetCo",
            location="SF",
        )
        old_csuite = _contact(
            connected_on=date.today() - timedelta(days=2000),  # recency=15
            current_title="CEO",  # 40
            current_company="TargetCo",
            location="SF",
        )
        profile = _profile(current_company="TargetCo", location="SF")

        peer_score = compute_warm_score(
            recent_peer, profile, target_role="Software Engineer"
        )
        csuite_score = compute_warm_score(
            old_csuite, profile, target_role="Software Engineer"
        )

        assert peer_score.total_score > csuite_score.total_score

    def test_former_colleague_scores_high(self):
        """Former colleague from 2 years ago at same company scores high."""
        contact = _contact(
            connected_on=date.today() - timedelta(days=730),  # 2 years → 55
            current_title="Senior Product Manager",
            current_company="NewCo",
            enriched_data={"work_history": [{"company": "Acme Corp"}]},
        )
        profile = _profile(current_company="Acme Corp")

        result = compute_referral_score(contact, profile)
        # former_colleague (+40) + relationship is strong
        assert result.total_score >= 45
        assert result.factors["relationship"]["former_colleague"] is True

    def test_new_hi[RESEND_KEY_REDACTED](self):
        """New hire (<6 months) scores lower on tenure than 2-year employee."""
        new_hi[RESEND_KEY_REDACTED] = compute_tenu[RESEND_KEY_REDACTED](3)
        veteran_tenure = compute_tenu[RESEND_KEY_REDACTED](24)
        assert new_hi[RESEND_KEY_REDACTED] < veteran_tenure
        assert new_hi[RESEND_KEY_REDACTED] == 40.0
        assert veteran_tenure == 100.0

    def test_same_dept_senior_ic_beats_diff_dept_vp(self):
        """Same-department Senior IC beats different-department VP."""
        senior_ic = compute_role_score(
            "Senior Software Engineer", target_role="Software Engineer"
        )
        diff_dept_vp = compute_role_score(
            "VP of Marketing", target_role="Software Engineer"
        )
        assert senior_ic > diff_dept_vp
        assert senior_ic == 100.0
        assert diff_dept_vp == 50.0  # VP fallback

    def test_csuite_low_for_referrals(self):
        """IMPORTANT: C-suite should score LOW for referrals, not HIGH."""
        ceo = compute_role_score("CEO")
        senior_eng = compute_role_score("Senior Software Engineer")
        manager = compute_role_score("Engineering Manager")

        assert ceo < senior_eng
        assert ceo < manager
        assert ceo == 40.0

    def test_tenu[RESEND_KEY_REDACTED](self):
        """1-3 year tenure is the referral sweet spot."""
        scores = {
            3: compute_tenu[RESEND_KEY_REDACTED](3),  # new hire
            9: compute_tenu[RESEND_KEY_REDACTED](9),  # 9 months
            24: compute_tenu[RESEND_KEY_REDACTED](24),  # 2 years (sweet spot)
            48: compute_tenu[RESEND_KEY_REDACTED](48),  # 4 years
            72: compute_tenu[RESEND_KEY_REDACTED](72),  # 6 years
        }
        # Sweet spot should be highest
        assert scores[24] == 100.0
        assert scores[24] > scores[3]
        assert scores[24] > scores[9]
        assert scores[24] > scores[48]
        assert scores[24] > scores[72]


# ---------------------------------------------------------------------------
# Integration tests — API endpoints
# ---------------------------------------------------------------------------

SAMPLE_CSV = (
    "First Name,Last Name,Email Address,Company,Position,Connected On\n"
    "Alice,Smith,alice@example.com,Acme Corp,Senior Software Engineer,{recent}\n"
    "Bob,Jones,bob@example.com,Other Inc,Analyst,{old}\n"
).format(
    recent=(date.today() - timedelta(days=30)).strftime("%d %b %Y"),
    old=(date.today() - timedelta(days=2000)).strftime("%d %b %Y"),
)


async def _signup_and_get_token(
    client: AsyncClient, email: str = "ws@example.com"
) -> str:
    """Create a test user and return auth token."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(db, email=email, full_name="WS User")
    return headers["Authorization"].split(" ")[1]


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

    # Senior eng with recent connection should be first
    assert body["data"][0]["current_title"] == "Senior Software Engineer"


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
