"""Tests for AI-powered CSV data cleanup service."""

import pytest
from unittest.mock import AsyncMock, patch

from app.services.ai_csv_cleaner import clean_contacts_mock
from app.services.ai_provider_pool import _extract_contacts_array


class TestCleanContactsMock:
    def test_title_cases_names(self):
        """Names with bad capitalization are fixed to title case."""
        contacts = [
            {
                "first_name": "alice",
                "last_name": "SMITH",
                "full_name": "alice SMITH",
                "email": "alice@example.com",
                "current_company": "Acme Corp",
                "current_title": "Engineer",
                "connected_on": None,
                "linkedin_url": None,
                "fingerprint": "abc123",
            }
        ]
        result = clean_contacts_mock(contacts)
        assert result[0]["first_name"] == "Alice"
        assert result[0]["last_name"] == "Smith"
        assert result[0]["full_name"] == "Alice Smith"

    def test_strips_extra_whitespace(self):
        """Extra whitespace in all fields is stripped."""
        contacts = [
            {
                "first_name": "  Bob  ",
                "last_name": "  Jones  ",
                "full_name": "  Bob    Jones  ",
                "email": " bob@example.com ",
                "current_company": "  Globex Inc  ",
                "current_title": "  Product Manager  ",
                "connected_on": None,
                "linkedin_url": None,
                "fingerprint": "def456",
            }
        ]
        result = clean_contacts_mock(contacts)
        assert result[0]["first_name"] == "Bob"
        assert result[0]["last_name"] == "Jones"
        assert result[0]["full_name"] == "Bob Jones"
        assert result[0]["email"] == "bob@example.com"
        assert result[0]["current_company"] == "Globex Inc"
        assert result[0]["current_title"] == "Product Manager"

    def test_splits_combined_first_name(self):
        """A full name crammed into first_name is split into first/last."""
        contacts = [
            {
                "first_name": "Charlie Brown",
                "last_name": "",
                "full_name": "Charlie Brown",
                "email": None,
                "current_company": "Acme",
                "current_title": "Dev",
                "connected_on": None,
                "linkedin_url": None,
                "fingerprint": "ghi789",
            }
        ]
        result = clean_contacts_mock(contacts)
        assert result[0]["first_name"] == "Charlie"
        assert result[0]["last_name"] == "Brown"
        assert result[0]["full_name"] == "Charlie Brown"

    def test_normalizes_well_known_company_names(self):
        """Well-known company names are normalized to proper form."""
        contacts = [
            {
                "first_name": "Test",
                "last_name": "User",
                "full_name": "Test User",
                "email": None,
                "current_company": "GOOGLE LLC",
                "current_title": "SWE",
                "connected_on": None,
                "linkedin_url": None,
                "fingerprint": "jkl012",
            }
        ]
        result = clean_contacts_mock(contacts)
        assert result[0]["current_company"] == "Google"

    def test_infers_company_from_email_domain(self):
        """When company is empty, infer from well-known email domains."""
        contacts = [
            {
                "first_name": "Test",
                "last_name": "User",
                "full_name": "Test User",
                "email": "test@google.com",
                "current_company": "",
                "current_title": "SWE",
                "connected_on": None,
                "linkedin_url": None,
                "fingerprint": "mno345",
            }
        ]
        result = clean_contacts_mock(contacts)
        assert result[0]["current_company"] == "Google"

    def test_does_not_overwrite_existing_company_from_email(self):
        """Email-to-company inference only fills empty company fields."""
        contacts = [
            {
                "first_name": "Test",
                "last_name": "User",
                "full_name": "Test User",
                "email": "test@google.com",
                "current_company": "Startup Inc",
                "current_title": "SWE",
                "connected_on": None,
                "linkedin_url": None,
                "fingerprint": "pqr678",
            }
        ]
        result = clean_contacts_mock(contacts)
        assert result[0]["current_company"] == "Startup Inc"

    def test_regenerates_fingerprint_after_cleanup(self):
        """Fingerprints are regenerated since names/companies may change."""
        contacts = [
            {
                "first_name": "alice",
                "last_name": "smith",
                "full_name": "alice smith",
                "email": None,
                "current_company": "GOOGLE LLC",
                "current_title": "SWE",
                "connected_on": None,
                "linkedin_url": "https://linkedin.com/in/alice",
                "fingerprint": "old_fingerprint",
            }
        ]
        result = clean_contacts_mock(contacts)
        assert result[0]["fingerprint"] != "old_fingerprint"
        assert result[0]["fingerprint"] is not None

    def test_handles_empty_list(self):
        """Empty input returns empty output."""
        assert clean_contacts_mock([]) == []

    def test_handles_none_fields_gracefully(self):
        """None values in optional fields don't cause errors."""
        contacts = [
            {
                "first_name": "Test",
                "last_name": "User",
                "full_name": "Test User",
                "email": None,
                "current_company": None,
                "current_title": None,
                "connected_on": None,
                "linkedin_url": None,
                "fingerprint": "stu901",
            }
        ]
        result = clean_contacts_mock(contacts)
        assert result[0]["first_name"] == "Test"
        assert result[0]["current_company"] is None

    def test_preserves_non_cleaned_fields(self):
        """Fields not targeted by cleanup (connected_on, linkedin_url, raw_csv_row, etc.) pass through."""
        contacts = [
            {
                "first_name": "Test",
                "last_name": "User",
                "full_name": "Test User",
                "email": "test@example.com",
                "current_company": "Acme",
                "current_title": "Dev",
                "connected_on": "2024-01-15",
                "linkedin_url": "https://linkedin.com/in/test",
                "fingerprint": "xyz",
                "raw_csv_row": {"original": "data"},
                "relationship_type": "friend",
                "source": "linkedin_csv",
            }
        ]
        result = clean_contacts_mock(contacts)
        assert result[0]["connected_on"] == "2024-01-15"
        assert result[0]["linkedin_url"] == "https://linkedin.com/in/test"
        assert result[0]["raw_csv_row"] == {"original": "data"}
        assert result[0]["relationship_type"] == "friend"
        assert result[0]["source"] == "linkedin_csv"


class TestCleanContactsRealMode:
    """Tests for Claude API cleanup mode (mocked API calls)."""

    @pytest.mark.asyncio
    async def test_real_mode_dispatches_to_provider_pool(self):
        """Real mode dispatches batches to provider pool and returns cleaned data."""
        contacts = [
            {
                "first_name": "alice",
                "last_name": "smith",
                "full_name": "alice smith",
                "email": "alice@example.com",
                "current_company": "acme",
                "current_title": "engineer",
                "connected_on": None,
                "linkedin_url": None,
                "fingerprint": "old",
            }
        ]

        # dispatch_batch returns cleaned contacts list
        cleaned_batch = [
            {
                "first_name": "Alice",
                "last_name": "Smith",
                "full_name": "Alice Smith",
                "email": "alice@example.com",
                "current_company": "Acme Corp",
                "current_title": "Software Engineer",
                "connected_on": None,
                "linkedin_url": None,
                "fingerprint": "new",
            }
        ]

        with patch(
            "app.services.ai_provider_pool.dispatch_batch",
            new_callable=AsyncMock,
            return_value=cleaned_batch,
        ):
            from app.services.ai_csv_cleaner import clean_contacts_real

            result = await clean_contacts_real(contacts)

        assert result[0]["first_name"] == "Alice"
        assert result[0]["last_name"] == "Smith"
        assert result[0]["current_company"] == "Acme Corp"
        assert result[0]["current_title"] == "Software Engineer"

    @pytest.mark.asyncio
    async def test_real_mode_falls_back_to_mock_on_pool_failure(self):
        """If all providers fail, falls back to mock cleanup per-batch."""
        contacts = [
            {
                "first_name": "alice",
                "last_name": "smith",
                "full_name": "alice smith",
                "email": None,
                "current_company": "acme",
                "current_title": "dev",
                "connected_on": None,
                "linkedin_url": None,
                "fingerprint": "old",
            }
        ]

        with patch(
            "app.services.ai_provider_pool.dispatch_batch",
            new_callable=AsyncMock,
            side_effect=RuntimeError("All providers exhausted"),
        ):
            from app.services.ai_csv_cleaner import clean_contacts_real

            result = await clean_contacts_real(contacts)

        # Should still get cleaned data via mock fallback
        assert result[0]["first_name"] == "Alice"
        assert result[0]["last_name"] == "Smith"


class TestCleanContactsPublicAPI:
    """Tests for the public clean_contacts() dispatcher."""

    @pytest.mark.asyncio
    async def test_dispatches_to_mock_when_mock_mode_true(self):
        """clean_contacts() uses mock cleaner when AI_MOCK_MODE=true."""
        contacts = [
            {
                "first_name": "test",
                "last_name": "user",
                "full_name": "test user",
                "email": None,
                "current_company": "GOOGLE LLC",
                "current_title": "SWE",
                "connected_on": None,
                "linkedin_url": None,
                "fingerprint": "old",
            }
        ]

        with (
            patch("app.services.ai_csv_cleaner.settings") as mock_settings,
            patch(
                "app.utils.rate_limiter.get_queue_depth",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            mock_settings.AI_MOCK_MODE = True

            from app.services.ai_csv_cleaner import clean_contacts

            result = await clean_contacts(contacts)

        assert result[0]["first_name"] == "Test"
        assert result[0]["current_company"] == "Google"


class TestCsvProcessingIntegration:
    """Verify AI cleaner is called during CSV upload processing."""

    @pytest.mark.asyncio
    async def test_uploaded_csv_gets_cleaned_names_and_company(self, client):
        """Messy CSV data has names title-cased and company inferred from email during upload."""
        from io import BytesIO

        from sqlalchemy import select

        from app.models.contact import Contact
        from tests.conftest import TestSessionLocal, create_test_user_in_db

        async with TestSessionLocal() as db_session:
            user, headers = await create_test_user_in_db(db_session)

        messy_csv = (
            "First Name,Last Name,Email Address,Company,Position,Connected On\n"
            "alice,SMITH,alice@google.com,,,15 Jan 2024\n"
        )
        csv_bytes = messy_csv.encode("utf-8")

        response = await client.post(
            "/api/v1/contacts/upload",
            files={"file": ("connections.csv", BytesIO(csv_bytes), "text/csv")},
            headers=headers,
        )
        assert response.status_code == 201

        # Verify the contact was stored with cleaned data
        async with TestSessionLocal() as db_session:
            result = await db_session.execute(
                select(Contact).where(Contact.user_id == user.id)
            )
            contact = result.scalar_one()
            assert contact.first_name == "Alice"
            assert contact.last_name == "Smith"
            assert contact.current_company == "Google"


class TestExtractContactsArray:
    """Tests for _extract_contacts_array helper that normalises AI responses."""

    def test_raw_array_passes_through(self):
        """A plain JSON array is returned as-is."""
        data = [{"first_name": "Alice", "last_name": "Smith"}]
        assert _extract_contacts_array(data) == data

    def test_wrapped_object_extracts_array(self):
        """OpenAI JSON-mode wraps arrays in an object — extract the list."""
        data = {"contacts": [{"first_name": "Bob", "last_name": "Jones"}]}
        assert _extract_contacts_array(data) == [
            {"first_name": "Bob", "last_name": "Jones"}
        ]

    def test_wrapped_with_different_key(self):
        """Any key name wrapping an array is handled."""
        data = {"result": [{"first_name": "Eve"}]}
        assert _extract_contacts_array(data) == [{"first_name": "Eve"}]

    def test_single_object_wrapped(self):
        """A single contact dict (no array) becomes a one-element list."""
        data = {"first_name": "Dan", "last_name": "Lee"}
        result = _extract_contacts_array(data)
        assert result == [{"first_name": "Dan", "last_name": "Lee"}]

    def test_empty_list(self):
        assert _extract_contacts_array([]) == []

    def test_non_dict_non_list_returns_empty(self):
        assert _extract_contacts_array("unexpected") == []
