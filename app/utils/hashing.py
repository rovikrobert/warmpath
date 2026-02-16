"""SHA-256 hashing utilities for suppression list matching."""

import hashlib


def hash_for_suppression(value: str) -> str:
    """SHA-256 of lowercased, stripped input."""
    return hashlib.sha256(value.lower().strip().encode()).hexdigest()
