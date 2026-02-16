"""Tests for suppression list, hashing, and privacy cascades."""

import uuid as uuid_mod
from datetime import date, timedelta

import pytest_asyncio
from httpx import AsyncClient

from app.models.company import Company
from app.models.contact import Contact
from app.models.marketplace import (
    IntroFacilitation,
    MarketplaceListing,
    NetworkSharingPreferences,
)
from app.models.privacy import SuppressionList
from app.services.marketplace_indexer import generate_marketplace_listings
from app.services.suppression import (
    add_to_suppression,
    check_suppression,
    purge_suppressed_person,
)
from app.utils.hashing import hash_for_suppression
from tests.conftest import TestSessionLocal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "privacy@test.com",
            "password": "testpass123",
            "full_name": "Privacy Tester",
        },
    )
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "privacy@test.com", "password": "testpass123"},
    )
    token = login_res.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def user_id(auth_headers: dict, client: AsyncClient) -> str:
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    return resp.json()["data"]["id"]


@pytest_asyncio.fixture
async def second_user_id(client: AsyncClient) -> str:
    """Create a second user to test cross-vault purge."""
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "holder2@test.com",
            "password": "testpass123",
            "full_name": "Second Holder",
        },
    )
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "holder2@test.com", "password": "testpass123"},
    )
    token = login_res.json()["data"]["access_token"]
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp.json()["data"]["id"]


@pytest_asyncio.fixture
async def company_id() -> uuid_mod.UUID:
    async with TestSessionLocal() as db:
        company = Company(name="Stripe", domain="stripe.com")
        db.add(company)
        await db.commit()
        return company.id


@pytest_asyncio.fixture
async def suppressed_contact(user_id: str, company_id: uuid_mod.UUID):
    """Create a contact that will be added to suppression list."""
    uid = uuid_mod.UUID(user_id)
    async with TestSessionLocal() as db:
        contact = Contact(
            user_id=uid,
            full_name="Suppressed Person",
            first_name="Suppressed",
            last_name="Person",
            email="suppressed@example.com",
            current_title="Software Engineer",
            current_company="Stripe",
            company_id=company_id,
            connected_on=date.today() - timedelta(days=100),
        )
        db.add(contact)
        await db.commit()
        return {"id": contact.id, "email": "suppressed@example.com"}


# ---------------------------------------------------------------------------
# Test Hashing
# ---------------------------------------------------------------------------


class TestHashing:
    def test_deterministic(self):
        assert hash_for_suppression("test@example.com") == hash_for_suppression(
            "test@example.com"
        )

    def test_case_insensitive(self):
        assert hash_for_suppression("Test@Example.COM") == hash_for_suppression(
            "test@example.com"
        )

    def test_strips_whitespace(self):
        assert hash_for_suppression("  test@example.com  ") == hash_for_suppression(
            "test@example.com"
        )

    def test_different_inputs_different_hashes(self):
        assert hash_for_suppression("a@b.com") != hash_for_suppression("c@d.com")

    def test_correct_length(self):
        # SHA-256 produces 64 hex chars
        assert len(hash_for_suppression("test")) == 64


# ---------------------------------------------------------------------------
# Test Suppression Check
# ---------------------------------------------------------------------------


class TestSuppressionCheck:
    async def test_not_suppressed(self):
        async with TestSessionLocal() as db:
            result = await check_suppression(
                email="clean@example.com",
                first_name="Clean",
                last_name="Person",
                company="Good Corp",
                db=db,
            )
            assert result is False

    async def test_suppressed_by_email(self):
        async with TestSessionLocal() as db:
            email_hash = hash_for_suppression("bad@example.com")
            db.add(SuppressionList(
                email_hash=email_hash,
                reason="self_request",
            ))
            await db.flush()

            result = await check_suppression(
                email="bad@example.com",
                first_name="Bad",
                last_name="Person",
                company="Corp",
                db=db,
            )
            assert result is True

    async def test_suppressed_by_name_company(self):
        async with TestSessionLocal() as db:
            name_company = "JohnDoeAcme Corp"
            name_company_hash = hash_for_suppression(name_company)
            db.add(SuppressionList(
                name_company_hash=name_company_hash,
                reason="legal_request",
            ))
            await db.flush()

            result = await check_suppression(
                email=None,
                first_name="John",
                last_name="Doe",
                company="Acme Corp",
                db=db,
            )
            assert result is True

    async def test_email_check_case_insensitive(self):
        async with TestSessionLocal() as db:
            email_hash = hash_for_suppression("test@example.com")
            db.add(SuppressionList(
                email_hash=email_hash,
                reason="self_request",
            ))
            await db.flush()

            result = await check_suppression(
                email="TEST@EXAMPLE.COM",
                first_name="Test",
                last_name="User",
                company="Corp",
                db=db,
            )
            assert result is True


# ---------------------------------------------------------------------------
# Test Add to Suppression
# ---------------------------------------------------------------------------


class TestAddToSuppression:
    async def test_adds_entry(self):
        async with TestSessionLocal() as db:
            entry_id = await add_to_suppression(
                email="suppress@example.com",
                first_name="Suppress",
                last_name="Me",
                company="Corp",
                reason="self_request",
                db=db,
            )
            await db.flush()
            assert entry_id is not None

            # Verify it's now suppressed
            result = await check_suppression(
                email="suppress@example.com",
                first_name="Suppress",
                last_name="Me",
                company="Corp",
                db=db,
            )
            assert result is True

    async def test_adds_both_hashes(self):
        async with TestSessionLocal() as db:
            await add_to_suppression(
                email="both@example.com",
                first_name="Both",
                last_name="Hashes",
                company="Corp",
                reason="self_request",
                db=db,
            )
            await db.flush()

            # Check the entry has both hashes
            from sqlalchemy import select

            result = await db.execute(
                select(SuppressionList).where(
                    SuppressionList.email_hash
                    == hash_for_suppression("both@example.com")
                )
            )
            entry = result.scalar_one()
            assert entry.email_hash is not None
            assert entry.name_company_hash is not None

    async def test_adds_without_email(self):
        async with TestSessionLocal() as db:
            entry_id = await add_to_suppression(
                email=None,
                first_name="NoEmail",
                last_name="Person",
                company="Corp",
                reason="abuse",
                db=db,
            )
            await db.flush()
            assert entry_id is not None

            from sqlalchemy import select

            result = await db.execute(
                select(SuppressionList).where(SuppressionList.id == entry_id)
            )
            entry = result.scalar_one()
            assert entry.email_hash is None
            assert entry.name_company_hash is not None


# ---------------------------------------------------------------------------
# Test Purge Cascade
# ---------------------------------------------------------------------------


class TestPurgeCascade:
    async def test_soft_deletes_contact(
        self, user_id: str, suppressed_contact, company_id
    ):
        """Purging a suppressed person soft-deletes their contacts."""
        async with TestSessionLocal() as db:
            email_hash = hash_for_suppression("suppressed@example.com")
            affected = await purge_suppressed_person(email_hash, None, db)
            await db.flush()

            assert affected >= 1

            from sqlalchemy import select

            result = await db.execute(
                select(Contact).where(
                    Contact.id == suppressed_contact["id"]
                )
            )
            contact = result.scalar_one()
            assert contact.deleted_at is not None

    async def test_deletes_marketplace_listings(
        self, user_id: str, suppressed_contact, company_id
    ):
        """Purging removes marketplace listings for that contact."""
        uid = uuid_mod.UUID(user_id)
        async with TestSessionLocal() as db:
            # Create a marketplace listing for this contact
            listing = MarketplaceListing(
                network_holder_id=uid,
                contact_id=suppressed_contact["id"],
                company_id=company_id,
                role_level="mid",
                department_category="engineering",
                warm_score_range="medium",
                connection_recency="recent",
            )
            db.add(listing)
            await db.flush()

            email_hash = hash_for_suppression("suppressed@example.com")
            affected = await purge_suppressed_person(email_hash, None, db)
            await db.flush()

            # Listing should be soft-deleted
            from sqlalchemy import select

            result = await db.execute(
                select(MarketplaceListing).where(
                    MarketplaceListing.id == listing.id
                )
            )
            deleted_listing = result.scalar_one()
            assert deleted_listing.deleted_at is not None
            assert affected >= 2  # listing + contact

    async def test_cancels_pending_facilitations(
        self, user_id: str, second_user_id: str, suppressed_contact, company_id
    ):
        """Purging cancels pending intro facilitations."""
        uid = uuid_mod.UUID(user_id)
        seeker_uid = uuid_mod.UUID(second_user_id)
        async with TestSessionLocal() as db:
            listing = MarketplaceListing(
                network_holder_id=uid,
                contact_id=suppressed_contact["id"],
                company_id=company_id,
                role_level="mid",
                department_category="engineering",
                warm_score_range="medium",
                connection_recency="recent",
            )
            db.add(listing)
            await db.flush()

            facilitation = IntroFacilitation(
                job_seeker_id=seeker_uid,
                network_holder_id=uid,
                marketplace_listing_id=listing.id,
                status="requested",
            )
            db.add(facilitation)
            await db.flush()

            email_hash = hash_for_suppression("suppressed@example.com")
            await purge_suppressed_person(email_hash, None, db)
            await db.flush()

            from sqlalchemy import select

            result = await db.execute(
                select(IntroFacilitation).where(
                    IntroFacilitation.id == facilitation.id
                )
            )
            updated = result.scalar_one()
            assert updated.status == "expired"

    async def test_cross_vault_purge(
        self, user_id: str, second_user_id: str, company_id
    ):
        """Purging removes contacts across multiple users' vaults."""
        uid1 = uuid_mod.UUID(user_id)
        uid2 = uuid_mod.UUID(second_user_id)

        async with TestSessionLocal() as db:
            # Same person in two different users' contacts
            c1 = Contact(
                user_id=uid1,
                full_name="Shared Person",
                first_name="Shared",
                last_name="Person",
                email="shared@example.com",
                current_title="Engineer",
                current_company="Stripe",
                company_id=company_id,
            )
            c2 = Contact(
                user_id=uid2,
                full_name="Shared Person",
                first_name="Shared",
                last_name="Person",
                email="shared@example.com",
                current_title="Engineer",
                current_company="Stripe",
                company_id=company_id,
            )
            db.add(c1)
            db.add(c2)
            await db.flush()

            email_hash = hash_for_suppression("shared@example.com")
            affected = await purge_suppressed_person(email_hash, None, db)
            await db.flush()

            assert affected == 2  # Both contacts soft-deleted

            from sqlalchemy import select

            for cid in [c1.id, c2.id]:
                result = await db.execute(select(Contact).where(Contact.id == cid))
                contact = result.scalar_one()
                assert contact.deleted_at is not None

    async def test_purge_by_name_company_hash(self, user_id: str, company_id):
        """Purge works using name+company hash when no email."""
        uid = uuid_mod.UUID(user_id)
        async with TestSessionLocal() as db:
            contact = Contact(
                user_id=uid,
                full_name="NoEmail Person",
                first_name="NoEmail",
                last_name="Person",
                email=None,
                current_title="Designer",
                current_company="Stripe",
                company_id=company_id,
            )
            db.add(contact)
            await db.flush()

            name_hash = hash_for_suppression("NoEmailPersonStripe")
            affected = await purge_suppressed_person(None, name_hash, db)
            await db.flush()

            assert affected == 1

            from sqlalchemy import select

            result = await db.execute(
                select(Contact).where(Contact.id == contact.id)
            )
            c = result.scalar_one()
            assert c.deleted_at is not None


# ---------------------------------------------------------------------------
# Test Suppression During Marketplace Indexing
# ---------------------------------------------------------------------------


class TestSuppressionDuringIndexing:
    async def test_suppressed_contacts_excluded_from_listings(
        self, user_id: str, suppressed_contact, company_id
    ):
        """Suppressed contacts are not included in marketplace listings."""
        uid = uuid_mod.UUID(user_id)

        async with TestSessionLocal() as db:
            # Add a non-suppressed contact
            clean = Contact(
                user_id=uid,
                full_name="Clean Person",
                first_name="Clean",
                last_name="Person",
                email="clean@stripe.com",
                current_title="Senior Engineer",
                current_company="Stripe",
                company_id=company_id,
                connected_on=date.today() - timedelta(days=100),
            )
            db.add(clean)

            # Add suppression entry
            db.add(SuppressionList(
                email_hash=hash_for_suppression("suppressed@example.com"),
                reason="self_request",
            ))

            # Set up sharing preferences
            db.add(NetworkSharingPreferences(
                user_id=uid, opt_in_marketplace=True
            ))
            await db.flush()

            count = await generate_marketplace_listings(uid, db)
            # Only the clean contact should generate a listing
            assert count == 1


# ---------------------------------------------------------------------------
# Test CSV Import Suppression (via API)
# ---------------------------------------------------------------------------


class TestCsvImportSuppression:
    async def test_suppressed_contact_skipped_on_import(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Contacts on suppression list are skipped during CSV upload."""
        import io

        # Add someone to suppression list
        async with TestSessionLocal() as db:
            db.add(SuppressionList(
                email_hash=hash_for_suppression("suppressed@example.com"),
                name_company_hash=hash_for_suppression(
                    "SuppressedPersonExample Corp"
                ),
                reason="self_request",
            ))
            await db.commit()

        # Build a CSV with one clean and one suppressed contact
        csv_content = (
            "First Name,Last Name,Email Address,Company,Position,"
            "Connected On\n"
            "Clean,Contact,clean@example.com,Clean Corp,Engineer,"
            "01 Jan 2024\n"
            "Suppressed,Person,suppressed@example.com,Example Corp,"
            "Manager,01 Jan 2024\n"
        )

        resp = await client.post(
            "/api/v1/contacts/upload",
            headers=auth_headers,
            files={
                "file": (
                    "connections.csv",
                    io.BytesIO(csv_content.encode("utf-8")),
                    "text/csv",
                )
            },
        )
        assert resp.status_code in (200, 201, 202)

        # Check only 1 contact was created (suppressed one skipped)
        contacts_resp = await client.get(
            "/api/v1/contacts", headers=auth_headers
        )
        contacts = contacts_resp.json()["data"]
        names = [c["full_name"] for c in contacts]
        assert "Clean Contact" in names
        assert "Suppressed Person" not in names
