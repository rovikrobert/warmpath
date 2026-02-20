"""Shared Gemini client singleton.

Provides a lazy-initialized client reused across AI services that use Gemini.
Async calls use client.aio.models.generate_content() — no separate async client needed.
"""

from google import genai

from app.config import settings

_client: genai.Client | None = None


def get_gemini_client() -> genai.Client:
    """Lazy singleton Gemini client."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    return _client
