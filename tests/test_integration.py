"""End-to-end integration test — full user journey.

Exercises every major feature in sequence:
  1. Sign up
  2. Upload a realistic 20-row LinkedIn CSV
  3. Verify contacts were created and deduplicated
  4. Verify companies were normalized
  5. Verify warm scores were computed
  6. Create a search request ("VP Engineering at fintech companies")
  7. Run the search (mock AI scorer)
  8. Get results sorted by combined score
  9. Request an intro message for the top result
  10. Check usage stats reflect all actions
"""

import io
from datetime import date, timedelta

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

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


async def _signup(client: AsyncClient, email: str = "journey@example.com") -> str:
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Str0ngP@ss!", "full_name": "Journey User"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["access_token"]


# ---------------------------------------------------------------------------
# The big test
# ---------------------------------------------------------------------------


async def test_full_user_journey(client: AsyncClient):
    """Walk through the entire WarmPath user flow end-to-end."""

    # -----------------------------------------------------------------------
    # Step 1: Sign up
    # -----------------------------------------------------------------------
    token = await _signup(client)
    headers = {"Authorization": f"Bearer {token}"}

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
    assert run_data["matches_found"] == 19  # all contacts scored

    # -----------------------------------------------------------------------
    # Step 8: Get results sorted by combined score
    # -----------------------------------------------------------------------
    results_resp = await client.get(
        f"/api/v1/search/{search_id}/results",
        headers=headers,
        params={"per_page": 50},
    )
    assert results_resp.status_code == 200
    results = results_resp.json()["data"]
    assert len(results) == 19

    # Results should be sorted descending by combined_score
    scores = [r["combined_score"] for r in results]
    assert scores == sorted(scores, reverse=True)

    # Top result should be someone with high title + company match
    top = results[0]
    assert top["combined_score"] > 0
    assert top["relevance_score"] > 0
    assert top["match_type"] in ("direct", "indirect", "weak")
    assert top["contact_name"] is not None

    # Sarah Chen (VP Eng @ Stripe) should be near the top — title + company match
    sarah_result = next(r for r in results if r["contact_name"] == "Sarah Chen")
    assert sarah_result["match_type"] == "direct"
    assert sarah_result["relevance_score"] >= 50  # title + company match

    # Alex Brown (SWE @ Google) should have a low relevance score
    alex_result = next(r for r in results if r["contact_name"] == "Alex Brown")
    assert alex_result["relevance_score"] < sarah_result["relevance_score"]

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
    assert len(intro_data["messages"]) == 3

    # Check variant labels
    variants = {m["variant_label"] for m in intro_data["messages"]}
    assert variants == {"direct", "mutual-interest", "casual"}

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

    # The middleware should have logged:
    #  - csv_upload (1 upload)
    #  - search_create (1 search created)
    #  - search_run (1 search run)
    #  - contacts_list, companies_list, etc.
    #  - intro_draft (1 intro created)
    # total_api_calls covers all authenticated API requests
    assert usage["total_api_calls"] >= 5  # at minimum several calls were made
    assert usage["csv_uploads"] >= 1
    assert usage["searches_run"] >= 1
    assert usage["intros_drafted"] >= 1


# ---------------------------------------------------------------------------
# Deduplication-specific test
# ---------------------------------------------------------------------------


async def test_csv_deduplication_on_reupload(client: AsyncClient):
    """Uploading the same CSV twice should not create duplicate contacts."""
    token = await _signup(client, email="dedup@example.com")
    headers = {"Authorization": f"Bearer {token}"}

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


# ---------------------------------------------------------------------------
# Multi-user isolation test
# ---------------------------------------------------------------------------


async def test_user_data_isolation(client: AsyncClient):
    """Each user should only see their own contacts and searches."""
    token_a = await _signup(client, email="usera@example.com")
    token_b = await _signup(client, email="userb@example.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

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
        json={"name": "User A's search"},
    )
    search_id = search_resp.json()["data"]["id"]

    # User B should not see User A's search
    get_resp = await client.get(f"/api/v1/search/{search_id}", headers=headers_b)
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# Search and scoring sanity checks
# ---------------------------------------------------------------------------


async def test_search_results_have_warm_and_relevance_scores(client: AsyncClient):
    """Search results should include both warm_score and relevance_score."""
    token = await _signup(client, email="scores@example.com")
    headers = {"Authorization": f"Bearer {token}"}

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
