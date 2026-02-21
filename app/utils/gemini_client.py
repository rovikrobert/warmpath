"""Shared Gemini client singleton.

Provides a lazy-initialized client reused across AI services that use Gemini.
Async calls use client.aio.models.generate_content() — no separate async client needed.

Supports two modes:
- **Vertex AI** (preferred): Set GOOGLE_SERVICE_ACCOUNT_JSON + GOOGLE_PROJECT_ID.
  Uses GCP free credits and higher quotas.
- **AI Studio**: Set GOOGLE_API_KEY. Simple API key auth.
"""

from __future__ import annotations

import contextlib
import json
import logging

from google import genai

from app.config import settings

logger = logging.getLogger(__name__)

_client: genai.Client | None = None


def get_gemini_client() -> genai.Client:
    """Lazy singleton Gemini client.

    If GOOGLE_SERVICE_ACCOUNT_JSON is set, uses Vertex AI mode.
    Otherwise falls back to API key (AI Studio) mode.
    """
    global _client
    if _client is not None:
        return _client

    if settings.GOOGLE_SERVICE_ACCOUNT_JSON.strip():
        from app.utils.gcp_credentials import load_gcp_credentials

        credentials = load_gcp_credentials(settings.GOOGLE_SERVICE_ACCOUNT_JSON)

        # Extract project from SA JSON if not explicitly set
        project = settings.GOOGLE_PROJECT_ID
        if not project:
            with contextlib.suppress(json.JSONDecodeError, AttributeError):
                project = json.loads(settings.GOOGLE_SERVICE_ACCOUNT_JSON.strip()).get(
                    "project_id", ""
                )

        _client = genai.Client(
            vertexai=True,
            project=project,
            location=settings.GOOGLE_LOCATION,
            credentials=credentials,
        )
        logger.info(
            "Gemini client initialized in Vertex AI mode (project=%s, location=%s)",
            project,
            settings.GOOGLE_LOCATION,
        )
    else:
        _client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        logger.info("Gemini client initialized in AI Studio mode")

    return _client
