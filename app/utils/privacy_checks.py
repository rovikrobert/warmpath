"""Privacy compliance checks — reusable guards for API endpoints.

These guards enforce GDPR Article 18 (right to restriction of processing)
and marketing opt-out across the platform.
"""

from fastapi import HTTPException, status

from app.models.user import User


def require_not_restricted(user: User) -> None:
    """Raise 403 if user's data processing is currently restricted.

    Called before AI matching, marketplace search, and batch processing
    to honor GDPR right to restrict processing.
    """
    if user.processing_restricted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Your data processing is currently restricted. "
                "Remove the restriction in your privacy settings to use this feature."
            ),
        )
