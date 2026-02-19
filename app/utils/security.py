"""Clerk JWT verification and FastAPI auth dependencies.

Replaces the old custom JWT system (jose + passlib) with Clerk's
RS256 JWKS-based verification. Tokens are issued by Clerk's frontend
SDK and verified here against Clerk's public JWKS endpoint.
"""

from functools import lru_cache
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_db
from app.models.user import User

bearer_scheme = HTTPBearer()


@lru_cache()
def _get_jwks_client():
    """Return a cached PyJWKClient for Clerk's JWKS endpoint."""
    from jwt import PyJWKClient

    jwks_url = f"https://{settings.CLERK_DOMAIN}/.well-known/jwks.json"
    jwks_client = PyJWKClient(jwks_url)
    return jwks_client


def verify_clerk_token(token: str) -> dict:
    """Verify a Clerk-issued JWT via JWKS (RS256).

    Returns the decoded payload dict on success.
    Raises HTTPException 401 on any verification failure.
    """
    import jwt as pyjwt

    try:
        client = _get_jwks_client()
        signing_key = client.get_signing_key_from_jwt(token)
        payload = pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=f"https://{settings.CLERK_DOMAIN}",
        )
        return payload
    except pyjwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Verify Clerk JWT, look up user by clerk_user_id, return User."""
    payload = verify_clerk_token(credentials.credentials)
    clerk_user_id = payload.get("sub")
    if not clerk_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing subject",
        )
    result = await db.execute(
        select(User).where(
            User.clerk_user_id == clerk_user_id, User.deleted_at.is_(None)
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated"
        )
    return user


async def require_verified_email(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency that requires the user's email to be verified.

    Use this on marketplace endpoints (search, intro requests, credit
    purchases). Own-network features (CSV upload, contacts, search) are
    allowed without verification.
    """
    if not current_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email to access marketplace features",
        )
    return current_user
