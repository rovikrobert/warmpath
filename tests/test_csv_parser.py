import io

import pytest
from httpx import AsyncClient

from app.services.csv_parser import generate_fingerprint, parse_linkedin_csv

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Sample CSV fixtures
# ---------------------------------------------------------------------------

SAMPLE_CSV = (
    "First Name,Last Name,Email Address,Company,Position,Connected On,URL\n"
    "Alice,Smith,alice@example.com,Acme Corp,Software Engineer,15 Jan 2024,https://linkedin.com/in/alice\n"
    "Bob,Jones,bob@example.com,Globex Inc,Product Manager,2024-02-20,https://linkedin.com/in/bob\n"
    "Charlie,Brown,,Initech,Designer,03/01/2024,https://linkedin.com/in/charlie\n"
    "Diana,Prince,diana@example.com,,VP Engineering,10 Jan 2024,https://linkedin.com/in/diana\n"
    "  eve ,  ADAMS ,eve@example.com, SpaceCorp , Data Scientist ,2024-03-15,https://linkedin.com/in/eve\n"
)

# Variant column names that LinkedIn sometimes uses
VARIANT_HEADER_CSV = (
    "FirstName,LastName,Email,Company Name,Job Title,Date Connected,Profile URL\n"
    "Frank,Castle,frank@example.com,Wayne Enterprises,Security Analyst,01 Jun 2024,https://linkedin.com/in/frank\n"
)

MISSING_NAMES_CSV = (
    "First Name,Last Name,Email Address,Company,Position,Connected On\n"
    ",,missing@example.com,SomeCo,Tester,2024-01-01\n"
    "Valid,User,valid@example.com,OtherCo,Dev,2024-01-01\n"
)

LATIN1_CSV_BYTES = (
    "First Name,Last Name,Email Address,Company,Position,Connected On\n"
    "Ren\xe9,M\xfcller,rene@example.com,Caf\xe9 Corp,Barista,01 Jan 2024\n"
).encode("latin-1")

BOM_CSV = (
    "First Name,Last Name,Email Address,Company,Position,Connected On\n"
    "Bom,Test,bom@example.com,BomCo,Dev,2024-01-01\n"
)


# ---------------------------------------------------------------------------
# Unit tests — csv_parser.py
# ---------------------------------------------------------------------------


class TestParseLinkedinCsv:
    def test_parse_standard_csv(self):
        contacts = parse_linkedin_csv(SAMPLE_CSV.encode("utf-8"))
        assert len(contacts) == 5

        alice = contacts[0]
        assert alice["first_name"] == "Alice"
        assert alice["last_name"] == "Smith"
        assert alice["full_name"] == "Alice Smith"
        assert alice["email"] == "alice@example.com"
        assert alice["current_company"] == "Acme Corp"
        assert alice["current_title"] == "Software Engineer"
        assert alice["linkedin_url"] == "https://linkedin.com/in/alice"
        assert alice["connected_on"] is not None
        assert alice["fingerprint"] is not None

    def test_names_are_title_cased_and_stripped(self):
        contacts = parse_linkedin_csv(SAMPLE_CSV.encode("utf-8"))
        eve = contacts[4]
        assert eve["first_name"] == "Eve"
        assert eve["last_name"] == "Adams"
        assert eve["full_name"] == "Eve Adams"
        assert eve["current_company"] == "SpaceCorp"
        assert eve["current_title"] == "Data Scientist"

    def test_missing_email_is_none(self):
        contacts = parse_linkedin_csv(SAMPLE_CSV.encode("utf-8"))
        charlie = contacts[2]
        assert charlie["email"] is None

    def test_missing_company_is_none(self):
        contacts = parse_linkedin_csv(SAMPLE_CSV.encode("utf-8"))
        diana = contacts[3]
        assert diana["current_company"] is None

    def test_variant_column_names(self):
        contacts = parse_linkedin_csv(VARIANT_HEADER_CSV.encode("utf-8"))
        assert len(contacts) == 1
        frank = contacts[0]
        assert frank["full_name"] == "Frank Castle"
        assert frank["current_company"] == "Wayne Enterprises"
        assert frank["current_title"] == "Security Analyst"

    def test_rows_without_names_are_skipped(self):
        contacts = parse_linkedin_csv(MISSING_NAMES_CSV.encode("utf-8"))
        assert len(contacts) == 1
        assert contacts[0]["full_name"] == "Valid User"

    def test_connected_on_date_formats(self):
        contacts = parse_linkedin_csv(SAMPLE_CSV.encode("utf-8"))
        # "15 Jan 2024"
        assert contacts[0]["connected_on"].isoformat() == "2024-01-15"
        # "2024-02-20"
        assert contacts[1]["connected_on"].isoformat() == "2024-02-20"
        # "03/01/2024"
        assert contacts[2]["connected_on"].isoformat() == "2024-03-01"
        # "10 Jan 2024"
        assert contacts[3]["connected_on"].isoformat() == "2024-01-10"

    def test_latin1_encoding(self):
        contacts = parse_linkedin_csv(LATIN1_CSV_BYTES)
        assert len(contacts) == 1
        assert contacts[0]["first_name"] == "René"
        assert contacts[0]["last_name"] == "Müller"

    def test_utf8_bom_handling(self):
        contacts = parse_linkedin_csv(BOM_CSV.encode("utf-8-sig"))
        assert len(contacts) == 1
        assert contacts[0]["full_name"] == "Bom Test"

    def test_empty_csv_returns_empty_list(self):
        contacts = parse_linkedin_csv(b"")
        assert contacts == []

    def test_header_only_csv_returns_empty_list(self):
        csv_bytes = b"First Name,Last Name,Email Address,Company,Position\n"
        contacts = parse_linkedin_csv(csv_bytes)
        assert contacts == []

    def test_raw_csv_row_preserved(self):
        contacts = parse_linkedin_csv(SAMPLE_CSV.encode("utf-8"))
        assert contacts[0]["raw_csv_row"]["First Name"] == "Alice"


class TestGenerateFingerprint:
    def test_same_inputs_same_hash(self):
        fp1 = generate_fingerprint(
            "Alice Smith", "Acme Corp", "https://linkedin.com/in/alice"
        )
        fp2 = generate_fingerprint(
            "Alice Smith", "Acme Corp", "https://linkedin.com/in/alice"
        )
        assert fp1 == fp2

    def test_case_insensitive(self):
        fp1 = generate_fingerprint("Alice Smith", "Acme Corp", None)
        fp2 = generate_fingerprint("alice smith", "acme corp", None)
        assert fp1 == fp2

    def test_different_inputs_different_hash(self):
        fp1 = generate_fingerprint("Alice Smith", "Acme Corp", None)
        fp2 = generate_fingerprint("Bob Jones", "Acme Corp", None)
        assert fp1 != fp2

    def test_all_empty_returns_none(self):
        assert generate_fingerprint(None, None, None) is None
        assert generate_fingerprint("", "", "") is None


# ---------------------------------------------------------------------------
# Integration tests — upload endpoint + deduplication
# ---------------------------------------------------------------------------


async def _signup_and_get_token(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "csv@example.com",
            "password": "secret123",
            "full_name": "CSV User",
        },
    )
    return resp.json()["data"]["access_token"]


def _csv_file(content: str | bytes, filename: str = "connections.csv"):
    if isinstance(content, str):
        content = content.encode("utf-8")
    return {"file": (filename, io.BytesIO(content), "text/csv")}


async def test_upload_csv_success(client: AsyncClient):
    token = await _signup_and_get_token(client)
    resp = await client.post(
        "/api/v1/contacts/upload",
        headers={"Authorization": f"Bearer {token}"},
        files=_csv_file(SAMPLE_CSV),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["data"]["status"] == "completed"
    assert body["data"]["row_count"] == 5
    assert body["data"]["processed_count"] == 5
    assert "meta" in body


async def test_upload_deduplication(client: AsyncClient):
    token = await _signup_and_get_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    # Upload the same CSV twice
    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )
    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )

    # Should still have only 5 contacts, not 10
    resp = await client.get("/api/v1/contacts", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["meta"]["total"] == 5


async def test_upload_rejects_non_csv(client: AsyncClient):
    token = await _signup_and_get_token(client)
    resp = await client.post(
        "/api/v1/contacts/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("data.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert resp.status_code == 400


async def test_list_contacts_pagination(client: AsyncClient):
    token = await _signup_and_get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )

    resp = await client.get("/api/v1/contacts?per_page=2&page=1", headers=headers)
    body = resp.json()
    assert len(body["data"]) == 2
    assert body["meta"]["total"] == 5
    assert body["meta"]["total_pages"] == 3


async def test_list_contacts_search(client: AsyncClient):
    token = await _signup_and_get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )

    resp = await client.get("/api/v1/contacts?search=Acme", headers=headers)
    body = resp.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["current_company"] == "Acme Corp"


async def test_get_single_contact(client: AsyncClient):
    token = await _signup_and_get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )

    list_resp = await client.get("/api/v1/contacts", headers=headers)
    contact_id = list_resp.json()["data"][0]["id"]

    resp = await client.get(f"/api/v1/contacts/{contact_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == contact_id


async def test_delete_contact_soft_delete(client: AsyncClient):
    token = await _signup_and_get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )

    list_resp = await client.get("/api/v1/contacts", headers=headers)
    contact_id = list_resp.json()["data"][0]["id"]

    del_resp = await client.delete(f"/api/v1/contacts/{contact_id}", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["data"]["deleted"] is True

    # Contact should no longer appear in list
    list_resp2 = await client.get("/api/v1/contacts", headers=headers)
    assert list_resp2.json()["meta"]["total"] == 4


async def test_contacts_are_user_scoped(client: AsyncClient):
    """User A's contacts should not be visible to User B (multi-tenant)."""
    # User A uploads contacts
    resp_a = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "usera@example.com",
            "password": "secret123",
            "full_name": "User A",
        },
    )
    token_a = resp_a.json()["data"]["access_token"]
    await client.post(
        "/api/v1/contacts/upload",
        headers={"Authorization": f"Bearer {token_a}"},
        files=_csv_file(SAMPLE_CSV),
    )

    # User B should see 0 contacts
    resp_b = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "userb@example.com",
            "password": "secret123",
            "full_name": "User B",
        },
    )
    token_b = resp_b.json()["data"]["access_token"]
    resp = await client.get(
        "/api/v1/contacts",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.json()["meta"]["total"] == 0


async def test_upload_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/contacts/upload",
        files=_csv_file(SAMPLE_CSV),
    )
    assert resp.status_code in (401, 403)
