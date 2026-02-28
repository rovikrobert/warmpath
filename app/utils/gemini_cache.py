"""Gemini context cache lifecycle management.

Creates and deletes Gemini cached content objects for the CSV cleanup
pipeline. Caching the system prompt + reference data reduces input token
costs by 75% on gemini-2.0-flash.
"""

from __futu[RESEND_KEY_REDACTED] import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)

GEMINI_CACHE_MODEL = "models/gemini-2.0-flash"
GEMINI_CACHE_TTL = "3600s"  # 1 hour


async def create_cleanup_cache(client: object, upload_id: str) -> str | None:
    """Create a Gemini cache with the cleanup prompt + reference data.

    Returns the cache name (e.g. "cachedContents/abc123") or None if
    caching is disabled or creation fails.
    """
    if not settings.GEMINI_CACHE_ENABLED:
        return None

    try:
        from google.genai import types

        from app.services.ai_csv_cleaner import build_cached_cleanup_content

        content = build_cached_cleanup_content()

        cache = client.caches.create(
            model=GEMINI_CACHE_MODEL,
            config=types.CreateCachedContentConfig(
                display_name=f"csv-clean-{upload_id}",
                system_instruction=content,
                contents=[],
                ttl=GEMINI_CACHE_TTL,
            ),
        )

        logger.info("Created Gemini cache %s for upload %s", cache.name, upload_id)
        return cache.name

    except Exception:
        logger.warning(
            "Failed to create Gemini cache for upload %s, proceeding without caching",
            upload_id,
            exc_info=True,
        )
        return None


async def delete_cleanup_cache(client: object, cache_name: str) -> None:
    """Delete a Gemini cache after processing completes."""
    try:
        client.caches.delete(name=cache_name)
        logger.info("Deleted Gemini cache %s", cache_name)
    except Exception:
        logger.warning(
            "Failed to delete Gemini cache %s (will expire via TTL)",
            cache_name,
            exc_info=True,
        )
