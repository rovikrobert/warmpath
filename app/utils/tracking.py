"""Lightweight usage tracking helper.

Replaces inline UsageLog imports + db.add(UsageLog(...)) scattered across route files.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession


async def track_action(
    db: AsyncSession,
    user_id: uuid.UUID,
    action: str,
    resource_id: uuid.UUID | None = None,
    metadata_: dict | None = None,
) -> None:
    """Record a usage log entry."""
    from app.models.enrichment import UsageLog

    db.add(
        UsageLog(
            user_id=user_id,
            action=action,
            resource_id=resource_id,
            metadata_=metadata_,
        )
    )
