import io

import pytest
from httpx import AsyncClient

from app.services.company_normalizer import normalize_company_name

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Unit tests — normalize_company_name
# ---------------------------------------------------------------------------


class TestNormalizeCompanyName:
    def test_strips_inc(self):
        assert normalize_company_name("Google Inc.") == "Google"
        assert normalize_company_name("Google, Inc.") == "Google"
        assert normalize_company_name("Google Inc") == "Google"

    def test_strips_llc(self):
        assert normalize_company_name("Acme LLC") == "Acme"
        assert normalize_company_name("Acme, LLC") == "Acme"
        assert normalize_company_name("Acme L.L.C.") == "Acme"

    def test_strips_ltd(self):
        assert normalize_company_name("Barclays Ltd.") == "Barclays"
        assert normalize_company_name("Barclays Ltd") == "Barclays"

    def test_strips_corporation(self):
        assert normalize_company_name("Acme Corporation") == "Acme"
        assert normalize_company_name("Acme Corp.") == "Acme"
        assert normalize_company_name("Acme Corp") == "Acme"

    def test_google_variants(self):
        assert normalize_company_name("Google") == "Google"
        assert normalize_company_name("Google LLC") == "Google"
        assert normalize_company_name("Alphabet Inc.") == "Google"
        assert normalize_company_name("Alphabet") == "Google"

    def test_meta_facebook_variants(self):
        assert normalize_company_name("Meta") == "Meta"
        assert normalize_company_name("Meta Platforms") == "Meta"
        assert normalize_company_name("Facebook") == "Meta"

    def test_microsoft_variants(self):
        assert normalize_company_name("Microsoft") == "Microsoft"
        assert normalize_company_name("Microsoft Corporation") == "Microsoft"
        assert normalize_company_name("Microsoft Corp") == "Microsoft"

    def test_amazon_variants(self):
        assert normalize_company_name("Amazon.com") == "Amazon"
        assert normalize_company_name("Amazon Web Services") == "AWS"
        assert normalize_company_name("AWS") == "AWS"

    def test_preserves_short_uppercase(self):
        assert normalize_company_name("IBM") == "IBM"
        assert normalize_company_name("SAP") == "SAP"

    def test_empty_and_none(self):
        assert normalize_company_name(None) is None
        assert normalize_company_name("") is None
        assert normalize_company_name("   ") is None

    def test_whitespace_stripped(self):
        assert normalize_company_name("  Acme Corp.  ") == "Acme"

    def test_unicode_company_names(self):
        assert normalize_company_name("Café Corp") == "Café"
        assert normalize_company_name("München GmbH") == "München"
        assert normalize_company_name("日本電気") == "日本電気"

    def test_unknown_company_passes_through(self):
        assert normalize_company_name("Warmpath") == "Warmpath"
        assert normalize_company_name("acme widgets") == "Acme Widgets"

    def test_gmbh_stripped(self):
        assert normalize_company_name("Siemens GmbH") == "Siemens"

    def test_plc_stripped(self):
        assert normalize_company_name("Barclays PLC") == "Barclays"


# ---------------------------------------------------------------------------
# Integration tests — company normalization during CSV upload
# ---------------------------------------------------------------------------

SAMPLE_CSV = (
    "First Name,Last Name,Email Address,Company,Position,Connected On\n"
    "Alice,Smith,alice@example.com,Google LLC,Software Engineer,15 Jan 2024\n"
    "Bob,Jones,bob@example.com,Google Inc.,Product Manager,20 Feb 2024\n"
    "Charlie,Brown,,Meta Platforms,Designer,01 Mar 2024\n"
    "Diana,Prince,diana@example.com,Facebook,VP Engineering,10 Jan 2024\n"
    "Eve,Adams,eve@example.com,Acme Corp.,Data Scientist,15 Mar 2024\n"
)


async def _signup_and_get_token(
    client: AsyncClient, email: str = "co@example.com"
) -> str:
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "secret123", "full_name": "Test User"},
    )
    return resp.json()["data"]["access_token"]


def _csv_file(content: str, filename: str = "connections.csv"):
    return {"file": (filename, io.BytesIO(content.encode("utf-8")), "text/csv")}


async def test_upload_creates_normalized_companies(client: AsyncClient):
    """Google LLC and Google Inc. should both map to one 'Google' company."""
    token = await _signup_and_get_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )

    resp = await client.get("/api/v1/companies", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    companies = {c["name"]: c["contact_count"] for c in body["data"]}

    # Google LLC + Google Inc. -> one "Google" with 2 contacts
    assert "Google" in companies
    assert companies["Google"] == 2

    # Meta Platforms + Facebook -> one "Meta" with 2 contacts
    assert "Meta" in companies
    assert companies["Meta"] == 2

    # Acme Corp. -> "Acme" with 1 contact
    assert "Acme" in companies
    assert companies["Acme"] == 1


async def test_companies_endpoint_pagination(client: AsyncClient):
    token = await _signup_and_get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )

    resp = await client.get("/api/v1/companies?per_page=2&page=1", headers=headers)
    body = resp.json()
    assert len(body["data"]) == 2
    assert body["meta"]["total"] == 3
    assert body["meta"]["total_pages"] == 2


async def test_companies_endpoint_search(client: AsyncClient):
    token = await _signup_and_get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )

    resp = await client.get("/api/v1/companies?search=Google", headers=headers)
    body = resp.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["name"] == "Google"


async def test_companies_a[RESEND_KEY_REDACTED](client: AsyncClient):
    """User B should not see User A's companies."""
    token_a = await _signup_and_get_token(client, email="a@example.com")
    await client.post(
        "/api/v1/contacts/upload",
        headers={"Authorization": f"Bearer {token_a}"},
        files=_csv_file(SAMPLE_CSV),
    )

    token_b = await _signup_and_get_token(client, email="b@example.com")
    resp = await client.get(
        "/api/v1/companies",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.json()["meta"]["total"] == 0


async def test_no_company_for_empty_company_field(client: AsyncClient):
    """Contacts with no company should not create a company record."""
    csv = (
        "First Name,Last Name,Email Address,Company,Position,Connected On\n"
        "Solo,Person,solo@example.com,,Freelancer,01 Jan 2024\n"
    )
    token = await _signup_and_get_token(client, email="solo@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    await client.post("/api/v1/contacts/upload", headers=headers, files=_csv_file(csv))

    resp = await client.get("/api/v1/companies", headers=headers)
    assert resp.json()["meta"]["total"] == 0


async def test_reupload_does_not_duplicate_companies(client: AsyncClient):
    """Uploading the same CSV twice should not create duplicate company records."""
    token = await _signup_and_get_token(client, email="reup@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )
    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )

    resp = await client.get("/api/v1/companies", headers=headers)
    body = resp.json()
    # Should still be exactly 3 companies, not 6
    assert body["meta"]["total"] == 3


async def test_companies_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/companies")
    assert resp.status_code in (401, 403)
