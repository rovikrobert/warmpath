"""Tests for PII redaction in Weave trace inputs."""

from __futu[RESEND_KEY_REDACTED] import annotations

import uuid

from app.utils.weave_redact import redact_inputs


class TestRedactInputs:
    """Unit tests for redact_inputs helper."""

    def test_redact_inputs_strips_name_fields(self) -> None:
        """PII fields are replaced with [REDACTED]; non-PII fields preserved."""
        raw = {
            "full_name": "Alice Smith",
            "email": "alice@example.com",
            "first_name": "Alice",
            "last_name": "Smith",
            "name": "Alice Smith",
            "phone": "+6591234567",
            "phone_number": "+6591234567",
            "linkedin_url": "https://linkedin.com/in/alice",
            "company": "Stripe",
            "role": "Engineer",
        }

        result = redact_inputs(raw)

        # Every PII field should be redacted
        for pii_key in (
            "full_name",
            "email",
            "first_name",
            "last_name",
            "name",
            "phone",
            "phone_number",
            "linkedin_url",
        ):
            assert result[pii_key] == "[REDACTED]"

        # Non-PII fields pass through unchanged
        assert result["company"] == "Stripe"
        assert result["role"] == "Engineer"

        # Original dict is not mutated
        assert raw["full_name"] == "Alice Smith"

    def test_redact_inputs_handles_nested_contact(self) -> None:
        """Contact ORM object is replaced with a summarised string."""

        class _FakeContact:
            def __init__(self, id: uuid.UUID) -> None:
                self.id = id

        contact_id = uuid.uuid4()
        raw = {"contact": _FakeContact(contact_id), "query": "engineer at Stripe"}

        result = redact_inputs(raw)

        assert result["contact"] == f"<Contact id={contact_id}>"
        assert result["query"] == "engineer at Stripe"

    def test_redact_inputs_preserves_non_pii(self) -> None:
        """A dict with no PII keys passes through completely unchanged."""
        raw = {
            "query": "senior engineer",
            "company": "Google",
            "limit": 10,
            "include_marketplace": True,
        }

        result = redact_inputs(raw)

        assert result == raw
        # Ensure it is a new dict, not the same object
        assert result is not raw
