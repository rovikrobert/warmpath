"""Tests for AI-powered CSV data cleanup service."""

from app.services.ai_csv_cleaner import clean_contacts_mock


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
