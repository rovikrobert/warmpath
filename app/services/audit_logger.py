"""Audit logger — write-only security event logging.

All sensitive operations are logged to the audit_logs table.
This table is append-only — no updates, no deletes.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


async def log_event(
    db: AsyncSession,
    action: str,
    user_id: uuid.UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict | None = None,
) -> AuditLog:
    """Insert an immutable audit log entry."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata_=metadata,
    )
    db.add(entry)
    await db.flush()
    return entry
