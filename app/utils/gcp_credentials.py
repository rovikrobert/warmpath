"""Shared GCP credential loader.

Decodes a base64-encoded (or raw JSON) service account key from the
GOOGLE_SERVICE_ACCOUNT_JSON env var and returns typed Credentials.

Used by the Gemini client (Vertex AI mode) today; available for
Cloud Storage / BigQuery if needed later.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)


def load_gcp_credentials(sa_json: str) -> "Credentials | None":
    """Parse service account JSON and return Credentials.

    *sa_json* may be either raw JSON or base64-encoded JSON (Railway
    stores multi-line env vars as base64).  Returns ``None`` on any
    parse failure so the caller can fall back to API-key mode.
    """
    if not sa_json or not sa_json.strip():
        return None

    sa_json = sa_json.strip()

    # Detect base64 vs raw JSON
    raw: str
    if sa_json.startswith("{"):
        raw = sa_json
    else:
        try:
            raw = base64.b64decode(sa_json).decode("utf-8")
        except Exception:
            logger.warning("GOOGLE_SERVICE_ACCOUNT_JSON is not valid base64 or JSON")
            return None

    try:
        info = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON")
        return None

    try:
        from google.oauth2.service_account import Credentials

        scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        return Credentials.from_service_account_info(info, scopes=scopes)
    except Exception:
        logger.exception("Failed to build GCP credentials from service account JSON")
        return None
