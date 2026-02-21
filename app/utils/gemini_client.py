"""Shared Gemini client singleton.

Provides a lazy-initialized client reused across AI services that use Gemini.
Async calls use client.aio.models.generate_content() — no separate async client needed.

Supports two modes:
- **Vertex AI** (preferred): Set GOOGLE_SERVICE_ACCOUNT_JSON + GOOGLE_PROJECT_ID.
  Uses GCP free credits and higher quotas.
- **AI Studio**: Set GOOGLE_API_KEY. Simple API key auth.
"""

import contextlib
import json
import os
import tempfile

from google import genai

from app.config import settings

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
        # Vertex AI mode — write SA key to temp file for ADC
        sa_json = settings.GOOGLE_SERVICE_ACCOUNT_JSON
        fd, path = tempfile.mkstemp(suffix=".json", prefix="gcp_sa_")
        with os.fdopen(fd, "w") as f:
            f.write(sa_json)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path

        # Extract project from SA JSON if not explicitly set
        project = settings.GOOGLE_PROJECT_ID
        if not project:
            with contextlib.suppress(json.JSONDecodeError, AttributeError):
                project = json.loads(sa_json).get("project_id", "")

        _client = genai.Client(
            vertexai=True,
            project=project,
            location=settings.GOOGLE_LOCATION,
        )
    else:
        # AI Studio mode — simple API key
        _client = genai.Client(api_key=settings.GOOGLE_API_KEY)

    return _client
