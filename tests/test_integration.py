"""End-to-end integration tests — full user journey + marketplace + privacy.

Sections:
  1. Original journey (signup → CSV → search → intro → usage)
  2. Enhanced solo journey (CSV → prefs → smart search → app pipeline → usage)
  3. Marketplace two-user flow (network holder → job seeker → intro → approval)
  4. Privacy compliance (suppression, anonymization, consent gate, unverified)
  5. Existing unit-ish helpers (dedup, isolation, scoring)
"""

import io
from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.models.privacy import SuppressionList
from app.services.credits import earn_credits
from app.utils.hashing import hash_for_suppression
from tests.conftest import TestSessionLocal, create_test_user_in_db

# ---------------------------------------------------------------------------
# Realistic 20-row LinkedIn CSV fixture
# ---------------------------------------------------------------------------

_recent = (date.today() - timedelta(days=30)).strftime("%d %b %Y")
_six_months = (date.today() - timedelta(days=180)).strftime("%d %b %Y")
_one_year = (date.today() - timedelta(days=365)).strftime("%d %b %Y")
_two_years = (date.today() - timedelta(days=730)).strftime("%d %b %Y")

# Include:
#  - 1 duplicate (row 4 = same fingerprint as row 1)
#  - mix of fintech companies (Stripe, Plaid, Brex, Square)
#  - VP Engineering titles that should score high
#  - variety of seniority levels
TWENTY_ROW_CSV = (
    "First Name,Last Name,Email Address,Company,Position,Connected On\n"
    # 1 — VP Eng at Stripe (fintech, should be top match)
    f"Sarah,Chen,sarah.chen@stripe.com,Stripe,VP Engineering,{_recent}\n"
    # 2 — CTO at Plaid (fintech, C-suite)
    f"James,Rodriguez,james@plaid.com,Plaid,CTO,{_six_months}\n"
    # 3 — Director Eng at Brex (fintech)
    f"Priya,Patel,priya@brex.com,Brex,Director of Engineering,{_one_year}\n"
    # 4 — DUPLICATE of row 1 (same name+company, should be deduped)
    f"Sarah,Chen,sarah.c@personal.com,Stripe,VP Engineering,{_recent}\n"
    # 5 — Senior SWE at Square (fintech, lower seniority)
    f"Marcus,Johnson,,Square,Senior Software Engineer,{_two_years}\n"
    # 6 — VP Product at Robinhood (fintech)
    f"Emily,Watson,emily@robinhood.com,Robinhood,VP Product,{_recent}\n"
    # 7 — Head of Eng at Affirm (fintech)
    f"David,Kim,david.kim@affirm.com,Affirm,Head of Engineering,{_six_months}\n"
    # 8 — CEO at a random startup (not fintech)
    f"Lisa,Thompson,lisa@acmecorp.com,Acme Corp,CEO,{_one_year}\n"
    # 9 — Software Engineer at Google (big tech, not fintech)
    f"Alex,Brown,,Google,Software Engineer,{_two_years}\n"
    # 10 — VP Engineering at Chime (fintech)
    f"Rachel,Garcia,rachel@chime.com,Chime,VP Engineering,{_six_months}\n"
    # 11 — Product Manager at Meta (not fintech)
    f"Kevin,Lee,,Meta,Product Manager,{_one_year}\n"
    # 12 — Founder at fintech startup
    f"Nina,Sharma,nina@payflow.io,PayFlow,Founder & CEO,{_recent}\n"
    # 13 — Account Executive at Salesforce (sales role, not eng)
    f"Tom,Williams,,Salesforce,Account Executive,{_two_years}\n"
    # 14 — VP Engineering at Marqeta (fintech)
    f"Yuki,Tanaka,yuki@marqeta.com,Marqeta,VP Engineering,{_one_year}\n"
    # 15 — Data Scientist at Stripe (fintech, not eng leadership)
    f"Omar,Hassan,,Stripe,Data Scientist,{_six_months}\n"
    # 16 — Engineering Manager at SoFi (fintech)
    f"Anna,Kowalski,anna@sofi.com,SoFi,Engineering Manager,{_recent}\n"
    # 17 — Principal Engineer at Coinbase (fintech-adjacent)
    f"Chris,Nguyen,,Coinbase,Principal Engineer,{_one_year}\n"
    # 18 — VP Sales at HubSpot (VP but not eng, not fintech)
    f"Maria,Lopez,maria@hubspot.com,HubSpot,VP Sales,{_six_months}\n"
    # 19 — Intern at a bank (junior)
    f"Jake,Miller,,JPMorgan Chase,Software Engineering Intern,{_two_years}\n"
    # 20 — Director of Platform at Adyen (fintech)
    f"Fatima,Al-Rashid,fatima@adyen.com,Adyen,Director of Platform Engineering,{_recent}\n"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _csv_file(content: str = TWENTY_ROW_CSV):
    return {
        "file": ("connections.csv", io.BytesIO(content.encode("utf-8")), "text/csv")
    }


async def _signup(client: AsyncClient, email: str = "journey@example.com") -> dict:
    """Create a test user in DB, return headers dict."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email=email, full_name="Journey User"
        )
    return headers


async def _signup_verified(
    client: AsyncClient,
    email: str,
    full_name: str = "Test User",
) -> dict:
    """Create a verified test user with welcome bonus, return headers dict."""
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db,
            email=email,
            full_name=full_name,
            email_verified=True,
        )
        # Award welcome bonus (normally done by Clerk webhook)
        await earn_credits(user.id, 50, "welcome_bonus", db)
        await db.commit()
    return headers


# ===========================================================================
# Section 1 — Original journey (unchanged from earlier sessions)
# ===========================================================================


async def test_full_user_journey(client: AsyncClient):
    """Walk through the entire WarmPath user flow end-to-end."""

    # -----------------------------------------------------------------------
    # Step 1: Create user
    # -----------------------------------------------------------------------
    headers = await _signup(client)

    # -----------------------------------------------------------------------
    # Step 2: Upload the 20-row CSV
    # -----------------------------------------------------------------------
    upload_resp = await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file()
    )
    assert upload_resp.status_code == 201
    upload_data = upload_resp.json()["data"]
    assert upload_data["status"] == "completed"
    assert upload_data["row_count"] == 20  # 20 CSV data rows
    assert upload_data["contacts_created"] == 19  # 1 duplicate deduped
    assert upload_data["duplicates_skipped"] == 1
    assert upload_data["completed_at"] is not None

    # Poll the upload status endpoint
    upload_id = upload_data["id"]
    poll_resp = await client.get(
        f"/api/v1/contacts/uploads/{upload_id}", headers=headers
    )
    assert poll_resp.status_code == 200
    assert poll_resp.json()["data"]["status"] == "completed"

    # -----------------------------------------------------------------------
    # Step 3: Verify contacts — 19 created (1 duplicate deduped)
    # -----------------------------------------------------------------------
    contacts_resp = await client.get(
        "/api/v1/contacts", headers=headers, params={"per_page": 100}
    )
    assert contacts_resp.status_code == 200
    contacts = contacts_resp.json()["data"]
    contact_names = [c["full_name"] for c in contacts]

    # Row 4 (Sarah Chen duplicate) should have been deduped
    assert contact_names.count("Sarah Chen") == 1
    # Total unique contacts = 19
    assert len(contacts) == 19

    # -----------------------------------------------------------------------
    # Step 4: Verify companies were normalized
    # -----------------------------------------------------------------------
    companies_resp = await client.get("/api/v1/companies", headers=headers)
    assert companies_resp.status_code == 200
    companies = companies_resp.json()["data"]
    company_names = [c["name"].lower() for c in companies]

    # Spot-check a few companies exist in the normalized table
    assert "stripe" in company_names
    assert "plaid" in company_names
    assert "brex" in company_names

    # -----------------------------------------------------------------------
    # Step 5: Verify warm scores were computed for all contacts
    # -----------------------------------------------------------------------
    # Warm scores are auto-computed after CSV upload.
    # Every contact should have a warm_score in the list response.
    for contact in contacts:
        assert contact["warm_score"] is not None, (
            f"Missing warm_score for {contact['full_name']}"
        )

    # VP/C-suite titles should score higher on the role component
    sarah = next(c for c in contacts if c["full_name"] == "Sarah Chen")
    alex = next(c for c in contacts if c["full_name"] == "Alex Brown")
    # Sarah (VP Eng, recent connection) should outscore Alex (SWE, old connection)
    assert sarah["warm_score"] > alex["warm_score"]

    # -----------------------------------------------------------------------
    # Step 6: Create a search request
    # -----------------------------------------------------------------------
    search_resp = await client.post(
        "/api/v1/search",
        headers=headers,
        json={
            "name": "VP Engineering at fintech companies",
            "description": "Find VP/Director-level engineering leaders at fintech companies",
            "target_titles": [
                "VP Engineering",
                "VP of Engineering",
                "Director of Engineering",
            ],
            "target_companies": [
                "Stripe",
                "Plaid",
                "Brex",
                "Chime",
                "Marqeta",
                "Affirm",
            ],
            "target_industries": ["fintech", "financial technology"],
            "target_keywords": ["engineering", "fintech"],
            "target_role": "VP Engineering",
            "target_seniority": "VP",
        },
    )
    assert search_resp.status_code == 201
    search_data = search_resp.json()["data"]
    search_id = search_data["id"]
    assert search_data["name"] == "VP Engineering at fintech companies"
    assert search_data["status"] == "active"

    # -----------------------------------------------------------------------
    # Step 7: Run the search (mock AI scorer)
    # -----------------------------------------------------------------------
    run_resp = await client.post(f"/api/v1/search/{search_id}/run", headers=headers)
    assert run_resp.status_code == 200
    run_data = run_resp.json()["data"]
    # Only contacts scoring >= 20 are persisted (7 of 19 in mock mode)
    assert run_data["matches_found"] == 7

    # -----------------------------------------------------------------------
    # Step 8: Get results sorted by combined score
    # -----------------------------------------------------------------------
    # Use min_score=0 to get all persisted results (scores >= 20)
    results_resp = await client.get(
        f"/api/v1/search/{search_id}/results",
        headers=headers,
        params={"per_page": 50, "min_score": 0},
    )
    assert results_resp.status_code == 200
    results = results_resp.json()["data"]
    assert len(results) == 7  # only contacts scoring >= 20 were persisted

    # Results should be sorted descending by combined_score
    scores = [r["combined_score"] for r in results]
    assert scores == sorted(scores, reverse=True)

    # Top result should be someone with high title + company match
    top = results[0]
    assert top["combined_score"] > 0
    assert top["relevance_score"] > 0
    assert top["match_type"] in ("direct", "adjacent", "senior_advocate", "alumni")
    assert top["contact_name"] is not None

    # Sarah Chen (VP Eng @ Stripe) should be near the top — title + company match
    sarah_result = next(r for r in results if r["contact_name"] == "Sarah Chen")
    assert sarah_result["match_type"] == "direct"
    assert sarah_result["relevance_score"] >= 50  # title + company match

    # Every result should have cultural_context
    for r in results:
        assert r.get("cultural_context") is not None
        ctx = r["cultural_context"]
        assert "approach_style" in ctx
        assert "recommended_channel" in ctx
        assert "message_sequence" in ctx

    # Low-relevance contacts (e.g. Alex Brown, score 5) are not persisted at all
    alex_names = [r for r in results if r["contact_name"] == "Alex Brown"]
    assert len(alex_names) == 0

    # -----------------------------------------------------------------------
    # Step 9: Request an intro message for the top result
    # -----------------------------------------------------------------------
    top_contact_id = top["contact_id"]
    top_match_id = top["id"]

    intro_resp = await client.post(
        "/api/v1/matches/intros",
        headers=headers,
        json={
            "contact_id": top_contact_id,
            "match_result_id": top_match_id,
            "context": "Looking for engineering partnership opportunities",
            "tone": "professional",
            "channel": "linkedin",
        },
    )
    assert intro_resp.status_code == 201
    intro_data = intro_resp.json()["data"]
    assert intro_data["status"] == "completed"
    # Message count depends on cultural context:
    # direct_ask → 3, reconnect+ask → 2, reconnect+explore+ask → 3
    assert len(intro_data["messages"]) >= 2

    # New sequence fields present on every message
    for msg in intro_data["messages"]:
        assert msg["sequence_step"] is not None
        assert msg["step_label"] in ("referral_ask", "reconnect", "explore")
        assert msg["send_after_days"] is not None
        assert msg["coaching_notes"] is not None

    # LinkedIn messages should have no subject line and be under 300 chars
    for msg in intro_data["messages"]:
        assert msg["subject_line"] is None
        assert len(msg["message_body"]) <= 300

    # Verify we can fetch the intro by ID
    intro_id = intro_data["id"]
    get_intro_resp = await client.get(
        f"/api/v1/matches/intros/{intro_id}", headers=headers
    )
    assert get_intro_resp.status_code == 200
    assert get_intro_resp.json()["data"]["id"] == intro_id

    # -----------------------------------------------------------------------
    # Step 10: Check usage stats reflect all actions
    # -----------------------------------------------------------------------
    usage_resp = await client.get("/api/v1/usage/me", headers=headers)
    assert usage_resp.status_code == 200
    usage = usage_resp.json()["data"]

    # The metering middleware should have logged:
    #  - csv_upload (1 upload)
    #  - intro_draft (1 intro created)
    # total_metered_calls covers only the 7 metered actions
    assert usage["total_metered_calls"] >= 1
    assert usage["counts"]["csv_upload"] >= 1
    assert usage["counts"]["intro_draft"] >= 1


# ===========================================================================
# Section 2 — Enhanced solo journey (CSV → prefs → smart search →
#              application pipeline → stats → usage)
# ===========================================================================


@pytest.mark.slow
async def test_complete_solo_journey(client: AsyncClient):
    """Full job-seeker lifecycle: CSV upload, preferences, smart search,
    application tracking, and usage stats."""

    # -- a) Create verified user -------------------------------------------
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db,
            email="solo@example.com",
            full_name="Solo User",
            email_verified=True,
        )

    me_resp = await client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.json()["data"]["email_verified"] is True

    # -- b) Upload CSV ---------------------------------------------------
    upload_resp = await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file()
    )
    assert upload_resp.status_code == 201
    assert upload_resp.json()["data"]["contacts_created"] == 19

    # -- c) Set job preferences ------------------------------------------
    prefs_resp = await client.put(
        "/api/v1/preferences/job",
        headers=headers,
        json={
            "target_role": "VP Engineering",
            "target_seniority": "VP",
            "target_industries": ["fintech"],
            "target_locations": ["San Francisco"],
            "open_to_remote": True,
        },
    )
    assert prefs_resp.status_code == 200
    assert prefs_resp.json()["data"]["target_role"] == "VP Engineering"

    get_prefs = await client.get("/api/v1/preferences/job", headers=headers)
    assert get_prefs.status_code == 200
    assert get_prefs.json()["data"]["target_role"] == "VP Engineering"

    # -- d) Smart search (own network) -----------------------------------
    smart_resp = await client.post(
        "/api/v1/search/smart",
        headers=headers,
        json={"company_names": ["Stripe", "Plaid"], "scope": "own_network"},
    )
    assert smart_resp.status_code == 201
    smart_data = smart_resp.json()["data"]
    assert smart_data["status"] == "completed"
    assert "companies" in smart_data
    assert smart_data["summary"]["companies_searched"] == 2

    # -- e) Pick a match, draft referral message -------------------------
    # Use a manual search+run to guarantee persisted MatchResult rows
    search_resp = await client.post(
        "/api/v1/search",
        headers=headers,
        json={
            "name": "Solo VP Eng",
            "target_titles": ["VP Engineering"],
            "target_companies": ["Stripe"],
            "target_role": "VP Engineering",
        },
    )
    search_id = search_resp.json()["data"]["id"]
    await client.post(f"/api/v1/search/{search_id}/run", headers=headers)

    results_resp = await client.get(
        f"/api/v1/search/{search_id}/results",
        headers=headers,
        params={"min_score": 0},
    )
    results = results_resp.json()["data"]
    assert len(results) > 0

    top = results[0]
    intro_resp = await client.post(
        "/api/v1/matches/intros",
        headers=headers,
        json={
            "contact_id": top["contact_id"],
            "match_result_id": top["id"],
            "context": "Referral ask",
            "tone": "professional",
            "channel": "linkedin",
        },
    )
    assert intro_resp.status_code == 201
    intro_id = intro_resp.json()["data"]["id"]

    # -- f) Create application from intro → pipeline ---------------------
    app_resp = await client.post(
        f"/api/v1/applications/from-intro/{intro_id}", headers=headers
    )
    assert app_resp.status_code == 201
    app_data = app_resp.json()["data"]
    app_id = app_data["id"]
    assert app_data["status"] == "draft"

    for next_status in [
        "message_sent",
        "responded",
        "interview_scheduled",
        "offer_received",
    ]:
        patch_resp = await client.patch(
            f"/api/v1/applications/{app_id}",
            headers=headers,
            json={"status": next_status},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["data"]["status"] == next_status

    # Verify auto-set timestamps
    get_app = await client.get(f"/api/v1/applications/{app_id}", headers=headers)
    assert get_app.json()["data"]["sent_at"] is not None
    assert get_app.json()["data"]["responded_at"] is not None

    # -- g) Application stats --------------------------------------------
    stats_resp = await client.get("/api/v1/applications/stats", headers=headers)
    assert stats_resp.status_code == 200
    stats = stats_resp.json()["data"]
    assert stats["total"] >= 1
    assert "offer_received" in stats["by_status"]

    # -- h) Usage stats --------------------------------------------------
    usage_resp = await client.get("/api/v1/usage/me", headers=headers)
    assert usage_resp.status_code == 200
    assert usage_resp.json()["data"]["total_metered_calls"] >= 1

    history_resp = await client.get("/api/v1/usage/me/history", headers=headers)
    assert history_resp.status_code == 200
    assert history_resp.json()["meta"]["total"] >= 1


# ===========================================================================
# Section 3 — Marketplace two-user flow
# ===========================================================================


async def test_marketplace_two_user_flow(client: AsyncClient):
    """Network holder uploads → job seeker searches marketplace → intro
    facilitation → approval → credit settlement."""

    # -- a) User A (network holder) — verified with welcome bonus ----------
    holder_headers = await _signup_verified(
        client, "holder@example.com", full_name="Network Holder"
    )

    await client.patch(
        "/api/v1/auth/intent",
        headers=holder_headers,
        json={"intent": "share_network"},
    )

    # -- b) Upload CSV with Stripe / Google contacts ---------------------
    upload_resp = await client.post(
        "/api/v1/contacts/upload", headers=holder_headers, files=_csv_file()
    )
    assert upload_resp.status_code == 201
    assert upload_resp.json()["data"]["contacts_created"] == 19

    # Holder balance: 50 welcome + 100 csv_upload = 150
    holder_bal = await client.get("/api/v1/credits/balance", headers=holder_headers)
    assert holder_bal.json()["data"]["balance"] == 150

    # -- c) Opt into marketplace -----------------------------------------
    share_resp = await client.put(
        "/api/v1/marketplace/sharing-preferences",
        headers=holder_headers,
        json={"opt_in_marketplace": True, "is_paused": False},
    )
    assert share_resp.status_code == 200

    # -- d) Verify anonymized listings -----------------------------------
    listings_resp = await client.get(
        "/api/v1/marketplace/my-listings", headers=holder_headers
    )
    assert listings_resp.status_code == 200
    listings = listings_resp.json()["data"]
    assert len(listings) > 0

    # Holder sees their own PII on their listings (their data)
    assert any(item.get("contact_name") for item in listings)

    # -- e) User B (job seeker) — verified with welcome bonus --------------
    seeker_headers = await _signup_verified(
        client, "seeker@example.com", full_name="Job Seeker"
    )

    await client.patch(
        "/api/v1/auth/intent",
        headers=seeker_headers,
        json={"intent": "find_referrals"},
    )

    seeker_bal = await client.get("/api/v1/credits/balance", headers=seeker_headers)
    assert seeker_bal.json()["data"]["balance"] == 50  # welcome bonus only

    # -- f) Search marketplace for Stripe contacts -----------------------
    search_resp = await client.post(
        "/api/v1/marketplace/search",
        headers=seeker_headers,
        json={"company_names": ["Stripe"]},
    )
    assert search_resp.status_code == 200
    mkt_results = search_resp.json()["data"]
    assert len(mkt_results) > 0

    # Anonymized: no names or emails leak through
    for r in mkt_results:
        assert "contact_name" not in r
        assert "contact_email" not in r
        assert r["company_name"]
        assert r["role_level"]

    # -- g) Request intro (costs 20 credits) -----------------------------
    listing_id = mkt_results[0]["listing_id"]
    intro_req_resp = await client.post(
        "/api/v1/marketplace/request-intro",
        headers=seeker_headers,
        json={
            "marketplace_listing_id": listing_id,
            "message_to_holder": "Interested in referral for SWE role",
            "profile_visibility": "summary",
        },
    )
    assert intro_req_resp.status_code == 201
    facilitation = intro_req_resp.json()["data"]
    facilitation_id = facilitation["id"]
    assert facilitation["status"] == "requested"

    # -- h) User A reviews incoming requests -----------------------------
    incoming_resp = await client.get(
        "/api/v1/marketplace/incoming-requests", headers=holder_headers
    )
    assert incoming_resp.status_code == 200
    incoming = incoming_resp.json()["data"]
    assert len(incoming) >= 1

    # Holder sees their own contact details
    req_item = incoming[0]
    assert req_item.get("contact_name") is not None
    assert req_item.get("contact_company") is not None

    # -- i) User A approves → holder earns credits -----------------------
    approve_resp = await client.patch(
        f"/api/v1/marketplace/requests/{facilitation_id}",
        headers=holder_headers,
        json={"action": "approve", "notes": "Happy to refer!"},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["data"]["status"] == "approved"

    # -- j) User B checks status — sees approved ------------------------
    my_reqs = await client.get(
        "/api/v1/marketplace/my-requests", headers=seeker_headers
    )
    assert my_reqs.status_code == 200
    seeker_reqs = my_reqs.json()["data"]
    assert any(r["status"] == "approved" for r in seeker_reqs)

    # -- k) User B creates + tracks application --------------------------
    app_resp = await client.post(
        "/api/v1/applications",
        headers=seeker_headers,
        json={
            "company_name": "Stripe",
            "role_title": "Software Engineer",
            "channel": "referral",
        },
    )
    assert app_resp.status_code == 201

    # -- l) Verify User A credits — facilitation credits deferred to delivery
    holder_bal2 = await client.get("/api/v1/credits/balance", headers=holder_headers)
    # 50 welcome + 100 csv = 150 (facilitation credits awarded on delivery, not on approve)
    assert holder_bal2.json()["data"]["balance"] == 150

    # -- m) Verify User B credits deducted -------------------------------
    seeker_bal2 = await client.get("/api/v1/credits/balance", headers=seeker_headers)
    # 50 welcome − 5 search − 20 intro = 25
    assert seeker_bal2.json()["data"]["balance"] == 25


# ===========================================================================
# Section 4 — Privacy compliance
# ===========================================================================


async def test_suppression_blocks_csv_import(client: AsyncClient):
    """A person on the suppression list should be skipped during CSV import."""

    # Add Sarah Chen to the suppression list before upload
    async with TestSessionLocal() as db:
        entry = SuppressionList(
            email_hash=hash_for_suppression("sarah.chen@stripe.com"),
            name_company_hash=hash_for_suppression("SarahChenStripe"),
            reason="self_request",
        )
        db.add(entry)
        await db.commit()

    headers = await _signup(client, email="supptest@example.com")

    upload_resp = await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file()
    )
    assert upload_resp.status_code == 201
    data = upload_resp.json()["data"]
    # Suppressed contacts reduce the created count
    assert data["contacts_created"] < 19  # at least Sarah Chen was skipped

    # Verify Sarah Chen was NOT imported
    contacts_resp = await client.get(
        "/api/v1/contacts", headers=headers, params={"per_page": 100}
    )
    names = [c["full_name"] for c in contacts_resp.json()["data"]]
    assert "Sarah Chen" not in names


async def test_marketplace_anonymization_no_pii(client: AsyncClient):
    """Marketplace search results must never contain PII (names, emails)."""

    # Holder: upload + opt in
    holder_headers = await _signup_verified(
        client, "anon_holder@example.com", full_name="Anon Holder"
    )
    await client.post(
        "/api/v1/contacts/upload", headers=holder_headers, files=_csv_file()
    )
    await client.put(
        "/api/v1/marketplace/sharing-preferences",
        headers=holder_headers,
        json={"opt_in_marketplace": True, "is_paused": False},
    )

    # Seeker: search
    seeker_headers = await _signup_verified(
        client, "anon_seeker@example.com", full_name="Anon Seeker"
    )
    resp = await client.post(
        "/api/v1/marketplace/search",
        headers=seeker_headers,
        json={"company_names": ["Stripe"]},
    )
    assert resp.status_code == 200
    for r in resp.json()["data"]:
        # MarketplaceSearchResult schema has no PII fields
        assert "contact_name" not in r
        assert "contact_email" not in r
        assert "contact_title" not in r
        # Only anonymized categorical fields
        assert r["role_level"] in (
            "junior",
            "mid",
            "senior",
            "lead",
            "director",
            "vp",
            "c_suite",
        )


async def test_consent_gate_hides_identity_until_approval(client: AsyncClient):
    """Job seeker should never see contact PII — even after approval,
    identity is only revealed on the network-holder side."""

    holder_headers = await _signup_verified(
        client, "gate_holder@example.com", full_name="Gate Holder"
    )
    await client.post(
        "/api/v1/contacts/upload", headers=holder_headers, files=_csv_file()
    )
    await client.put(
        "/api/v1/marketplace/sharing-preferences",
        headers=holder_headers,
        json={"opt_in_marketplace": True, "is_paused": False},
    )

    seeker_headers = await _signup_verified(
        client, "gate_seeker@example.com", full_name="Gate Seeker"
    )

    # Search → request intro
    search_resp = await client.post(
        "/api/v1/marketplace/search",
        headers=seeker_headers,
        json={"company_names": ["Stripe"]},
    )
    listing_id = search_resp.json()["data"][0]["listing_id"]

    await client.post(
        "/api/v1/marketplace/request-intro",
        headers=seeker_headers,
        json={
            "marketplace_listing_id": listing_id,
            "profile_visibility": "summary",
        },
    )

    # Seeker's my-requests: no contact PII
    my_reqs = await client.get(
        "/api/v1/marketplace/my-requests", headers=seeker_headers
    )
    for r in my_reqs.json()["data"]:
        assert r.get("contact_name") is None
        assert r.get("contact_email") is None

    # Holder approves
    inc = await client.get(
        "/api/v1/marketplace/incoming-requests", headers=holder_headers
    )
    fid = inc.json()["data"][0]["id"]
    await client.patch(
        f"/api/v1/marketplace/requests/{fid}",
        headers=holder_headers,
        json={"action": "approve"},
    )

    # Seeker still sees no contact PII after approval
    my_reqs2 = await client.get(
        "/api/v1/marketplace/my-requests", headers=seeker_headers
    )
    for r in my_reqs2.json()["data"]:
        assert r.get("contact_name") is None
        assert r.get("contact_email") is None

    # Holder DOES see their own contact info (it's their data)
    inc2 = await client.get(
        "/api/v1/marketplace/incoming-requests", headers=holder_headers
    )
    approved = [r for r in inc2.json()["data"] if r["status"] == "approved"]
    assert len(approved) >= 1
    assert approved[0].get("contact_name") is not None


async def test_unverified_user_blocked_from_marketplace(client: AsyncClient):
    """Unverified users should be blocked from marketplace endpoints that
    require email verification (search, request-intro, credit purchase)."""

    # Create user WITHOUT verifying email
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db,
            email="unverified@example.com",
            full_name="Unverified User",
            email_verified=False,
        )

    # marketplace/search — requires verified email
    resp = await client.post(
        "/api/v1/marketplace/search",
        headers=headers,
        json={"company_names": ["Google"]},
    )
    assert resp.status_code == 403

    # marketplace/request-intro — requires verified email
    resp2 = await client.post(
        "/api/v1/marketplace/request-intro",
        headers=headers,
        json={
            "marketplace_listing_id": "00000000-0000-0000-0000-000000000000",
            "profile_visibility": "summary",
        },
    )
    assert resp2.status_code == 403

    # credits/purchase — requires verified email
    resp3 = await client.post(
        "/api/v1/credits/purchase",
        headers=headers,
        json={"amount": 10},
    )
    assert resp3.status_code == 403

    # Own-network features should still work (contacts, search, etc.)
    contacts_resp = await client.get("/api/v1/contacts", headers=headers)
    assert contacts_resp.status_code == 200


async def test_cross_vault_marketplace_isolation(client: AsyncClient):
    """User B should never see User A's raw contacts via marketplace search.
    Marketplace only exposes anonymized listings, not vault data."""

    holder_headers = await _signup_verified(
        client, "vault_holder@example.com", full_name="Vault Holder"
    )
    await client.post(
        "/api/v1/contacts/upload", headers=holder_headers, files=_csv_file()
    )
    await client.put(
        "/api/v1/marketplace/sharing-preferences",
        headers=holder_headers,
        json={"opt_in_marketplace": True, "is_paused": False},
    )

    seeker_headers = await _signup_verified(
        client, "vault_seeker@example.com", full_name="Vault Seeker"
    )

    # Seeker can't access holder's contacts directly
    contacts_resp = await client.get(
        "/api/v1/contacts", headers=seeker_headers, params={"per_page": 100}
    )
    assert contacts_resp.json()["meta"]["total"] == 0

    # Marketplace search returns anonymized data only
    resp = await client.post(
        "/api/v1/marketplace/search",
        headers=seeker_headers,
        json={"company_names": ["Stripe"]},
    )
    assert resp.status_code == 200
    for r in resp.json()["data"]:
        assert "contact_name" not in r
        assert "contact_email" not in r


# ===========================================================================
# Section 5 — Existing helper tests (dedup, isolation, scoring)
# ===========================================================================


async def test_csv_deduplication_on_reupload(client: AsyncClient):
    """Uploading the same CSV twice should not create duplicate contacts."""
    headers = await _signup(client, email="dedup@example.com")

    # First upload
    await client.post("/api/v1/contacts/upload", headers=headers, files=_csv_file())
    resp1 = await client.get(
        "/api/v1/contacts", headers=headers, params={"per_page": 100}
    )
    count_first = resp1.json()["meta"]["total"]

    # Second upload of same CSV — contacts should be updated, not duplicated
    await client.post("/api/v1/contacts/upload", headers=headers, files=_csv_file())
    resp2 = await client.get(
        "/api/v1/contacts", headers=headers, params={"per_page": 100}
    )
    count_second = resp2.json()["meta"]["total"]

    assert count_first == count_second == 19


async def test_user_data_isolation(client: AsyncClient):
    """Each user should only see their own contacts and searches."""
    headers_a = await _signup(client, email="usera@example.com")
    headers_b = await _signup(client, email="userb@example.com")

    # User A uploads contacts
    await client.post("/api/v1/contacts/upload", headers=headers_a, files=_csv_file())

    # User B should see zero contacts
    resp_b = await client.get("/api/v1/contacts", headers=headers_b)
    assert resp_b.json()["meta"]["total"] == 0

    # User A should see 19 contacts
    resp_a = await client.get("/api/v1/contacts", headers=headers_a)
    assert resp_a.json()["meta"]["total"] == 19

    # User A creates a search
    search_resp = await client.post(
        "/api/v1/search",
        headers=headers_a,
        json={"name": "User A's search", "target_role": "VP Engineering"},
    )
    search_id = search_resp.json()["data"]["id"]

    # User B should not see User A's search
    get_resp = await client.get(f"/api/v1/search/{search_id}", headers=headers_b)
    assert get_resp.status_code == 404


async def test_search_results_have_warm_and_relevance_scores(client: AsyncClient):
    """Search results should include both warm_score and relevance_score."""
    headers = await _signup(client, email="scores@example.com")

    # Upload contacts
    await client.post("/api/v1/contacts/upload", headers=headers, files=_csv_file())

    # Create and run search
    search_resp = await client.post(
        "/api/v1/search",
        headers=headers,
        json={
            "name": "Score check",
            "target_titles": ["VP Engineering"],
            "target_companies": ["Stripe"],
            "target_role": "VP Engineering",
        },
    )
    search_id = search_resp.json()["data"]["id"]

    await client.post(f"/api/v1/search/{search_id}/run", headers=headers)

    results_resp = await client.get(
        f"/api/v1/search/{search_id}/results", headers=headers
    )
    results = results_resp.json()["data"]

    for r in results:
        # Every result should have all score fields
        assert "relevance_score" in r
        assert "warm_score" in r
        assert "combined_score" in r
        # combined = relevance * 0.5 + warm * 0.5
        warm = r["warm_score"] or 0
        expected = round(r["relevance_score"] * 0.5 + warm * 0.5, 2)
        assert abs(r["combined_score"] - expected) < 0.02  # floating-point tolerance


# ===========================================================================
# Section 6 — Onboarding funnel regression (beta sandbox mode)
# ===========================================================================


async def test_beta_signup_then_upload_succeeds(client: AsyncClient, monkeypatch):
    """Regression: welcome bonus (500 in beta) must not block same-day CSV upload.

    Previously the 500-credit welcome bonus filled the daily earn cap (500),
    causing every new user who uploaded on signup day to fail with
    "Daily earn cap exceeded". Contacts were rolled back.

    This test reproduces the exact production failure path:
    signup → 500 welcome bonus → CSV upload → contacts must exist.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "BETA_SANDBOX_MODE", True)

    # Step 1: Signup with 500-credit beta welcome bonus
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db,
            email="louisa@beta-test.com",
            full_name="Beta User",
            email_verified=True,
        )
        await earn_credits(user.id, 500, "welcome_bonus", db, skip_daily_cap=True)
        await db.commit()

    # Verify 500 balance before upload
    balance_resp = await client.get("/api/v1/credits/balance", headers=headers)
    assert balance_resp.json()["data"]["balance"] == 500

    # Step 2: Upload CSV — this is the step that used to fail
    upload_resp = await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file()
    )
    assert upload_resp.status_code == 201
    upload_data = upload_resp.json()["data"]
    assert upload_data["status"] == "completed"
    assert upload_data["contacts_created"] == 19

    # Step 3: Verify contacts actually exist (not rolled back)
    contacts_resp = await client.get(
        "/api/v1/contacts", headers=headers, params={"per_page": 100}
    )
    assert contacts_resp.status_code == 200
    assert len(contacts_resp.json()["data"]) == 19

    # Step 4: Verify upload credits awarded (500 welcome + 100 upload = 600)
    after_resp = await client.get("/api/v1/credits/balance", headers=headers)
    assert after_resp.json()["data"]["balance"] == 600
