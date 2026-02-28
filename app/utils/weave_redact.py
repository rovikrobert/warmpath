"""PII redaction utilities for Weave trace inputs.

Ensures that personally identifiable information (names, emails, phone
numbers, LinkedIn URLs) never appears in W&B Weave trace logs.  Contact
ORM objects are replaced with a short summary string containing only
the database ID.
"""

from __futu[RESEND_KEY_REDACTED] import annotations

from typing import Any

_PII_FIELDS: frozenset[str] = frozenset(
    {
        "full_name",
        "email",
        "first_name",
        "last_name",
        "name",
        "phone",
        "phone_number",
        "linkedin_url",
    }
)


def redact_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of *inputs* with PII fields replaced.

    * Keys in ``_PII_FIELDS`` are replaced with ``"[REDACTED]"``.
    * A ``"contact"`` key whose value has an ``id`` attribute (i.e. an
      ORM model) is replaced with ``"<Contact id=...>"``.
    * All other key/value pairs pass through unchanged.

    The original dict is never mutated.
    """
    redacted: dict[str, Any] = {}
    for key, value in inputs.items():
        if key == "contact" and hasattr(value, "id"):
            redacted[key] = f"<Contact id={value.id}>"
        elif key in _PII_FIELDS:
            redacted[key] = "[REDACTED]"
        else:
            redacted[key] = value
    return redacted
