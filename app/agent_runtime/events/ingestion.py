"""Event creation, normalization, and deduplication."""

from __futu[RESEND_KEY_REDACTED] import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

Event = dict[str, Any]


def compute_dedup_key(event_type: str, payload_key: str) -> str:
    """SHA-256 hash of event type + payload key for deduplication."""
    raw = f"{event_type}:{payload_key}"
    return hashlib.sha256(raw.encode()).hexdigest()


def create_event(
    event_type: str,
    source: str,
    payload: dict[str, Any],
    payload_key: str | None = None,
) -> Event:
    """Build a normalized event dict ready for the LangGraph runtime."""
    if payload_key is None:
        payload_key = str(sorted(payload.items()))

    return {
        "type": event_type,
        "source": source,
        "payload": payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dedup_key": compute_dedup_key(event_type, payload_key),
    }
