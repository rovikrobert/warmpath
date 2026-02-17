"""LinkedIn OAuth2 / OpenID Connect integration.

When LINKEDIN_CLIENT_ID is empty (default), all functions return deterministic
mock data so the feature works in development without LinkedIn credentials.
"""

import logging
import urllib.parse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"

SCOPES = "openid profile email"


def _is_mock_mode() -> bool:
    return settings.AI_MOCK_MODE or not settings.LINKEDIN_CLIENT_ID


def get_authorize_url(state: str) -> str:
    """Build LinkedIn OAuth2 authorization URL with openid+profile+email scopes."""
    if _is_mock_mode():
        base = settings.FRONTEND_URL.rstrip("/")
        return f"{base}/auth/linkedin/callback?code=mock_code&state={state}"

    params = {
        "response_type": "code",
        "client_id": settings.LINKEDIN_CLIENT_ID,
        "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
        "state": state,
        "scope": SCOPES,
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


async def exchange_code(code: str) -> str:
    """Exchange authorization code for access token via LinkedIn API."""
    if _is_mock_mode():
        return "mock_access_token"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
                "client_id": settings.LINKEDIN_CLIENT_ID,
                "client_secret": settings.LINKEDIN_CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


async def fetch_profile(access_token: str) -> dict:
    """Fetch profile from LinkedIn userinfo endpoint.

    Returns dict with keys: sub, email, name, given_name, family_name, picture.
    """
    if _is_mock_mode():
        return {
            "sub": "mock_linkedin_id_12345",
            "email": "linkedin.user@example.com",
            "name": "Mock LinkedIn User",
            "given_name": "Mock",
            "family_name": "User",
            "picture": None,
        }

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "sub": data.get("sub", ""),
            "email": data.get("email", ""),
            "name": data.get("name", ""),
            "given_name": data.get("given_name", ""),
            "family_name": data.get("family_name", ""),
            "picture": data.get("picture"),
        }
