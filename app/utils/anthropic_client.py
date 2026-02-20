"""Shared Anthropic client singletons.

Provides lazy-initialized async and sync clients reused across all AI services.
Avoids creating throwaway clients on every API call.
"""

import anthropic

from app.config import settings

_async_client: anthropic.AsyncAnthropic | None = None
_sync_client: anthropic.Anthropic | None = None


def get_async_client() -> anthropic.AsyncAnthropic:
    """Lazy singleton async Anthropic client."""
    global _async_client
    if _async_client is None:
        _async_client = anthropic.AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=60.0,
            max_retries=1,
        )
    return _async_client


def get_sync_client() -> anthropic.Anthropic:
    """Lazy singleton sync Anthropic client."""
    global _sync_client
    if _sync_client is None:
        _sync_client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=60.0,
            max_retries=1,
        )
    return _sync_client
