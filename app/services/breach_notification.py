"""Data breach notification service — PDPA/GDPR compliance.

Provides infrastructure to identify affected users and send bulk
breach notifications. Also tracks DSAR (data subject access requests)
with regulatory deadlines.
"""

import html
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.privacy import DataRequest
from app.models.user import User
from app.services.audit_logger import log_event
from app.services.email_service import _send_email

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Breach notification
# ---------------------------------------------------------------------------


async def send_breach_notification(
    affected_user_ids: list[uuid.UUID],
    breach_summary: str,
    data_affected: str,
    db: AsyncSession,
) -> int:
    """Send breach notification emails to affected users.

    Args:
        affected_user_ids: List of user IDs whose data may be affected.
        breach_summary: Plain-language description of the breach.
        data_affected: What data categories were involved.
        db: Database session.

    Returns count of notifications sent.
    """
    count = 0
    for user_id in affected_user_ids:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            continue

        safe_summary = html.escape(breach_summary)
        safe_data_affected = html.escape(data_affected)

        _send_email(
            to=user.email,
            subject="Important: WarmPath Data Security Notice",
            html=(
                '<div style="font-family: -apple-system, BlinkMacSystemFont, '
                "'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; "
                'padding: 40px 20px;">'
                '<h2 style="color: #1e293b;">Security Notice</h2>'
                f'<p style="color: #475569;">{safe_summary}</p>'
                f'<p style="color: #475569;"><strong>Data affected:</strong> '
                f"{safe_data_affected}</p>"
                '<p style="color: #475569;">We are taking the following steps:</p>'
                "<ul>"
                "<li>Investigating the root cause</li>"
                "<li>Strengthening our security controls</li>"
                "<li>Notifying the relevant data protection authorities</li>"
                "</ul>"
                '<p style="color: #475569;">If you have questions, contact us at '
                "rovik@majiq.agency.</p>"
                "</div>"
            ),
        )

        await log_event(
            db,
            "breach_notification_sent",
            user_id=user_id,
            metadata={
                "breach_summary": breach_summary[:200],
                "data_affected": data_affected[:200],
            },
        )
        count += 1

    await db.flush()
    return count


# ---------------------------------------------------------------------------
# DSAR tracking
# ---------------------------------------------------------------------------

# Deadline days by regulation
DSAR_DEADLINES = {
    "gdpr": 30,
    "ccpa": 45,
    "pdpa": 30,
    "general": 30,
}


async def create_data_request(
    request_type: str,
    requester_email: str,
    db: AsyncSession,
    user_id: uuid.UUID | None = None,
    details: dict | None = None,
    regulation: str = "general",
) -> DataRequest:
    """Create a tracked DSAR / rights request with regulatory deadline.

    request_type: "access", "deletion", "rectification", "restriction",
                  "portability", "objection"
    """
    deadline_days = DSAR_DEADLINES.get(regulation, 30)
    deadline = datetime.now(timezone.utc) + timedelta(days=deadline_days)

    request = DataRequest(
        user_id=user_id,
        request_type=request_type,
        requester_email=requester_email,
        details=details or {},
        deadline_at=deadline,
    )
    db.add(request)
    await db.flush()

    await log_event(
        db,
        "data_request_created",
        user_id=user_id,
        metadata={
            "request_type": request_type,
            "regulation": regulation,
            "deadline": deadline.isoformat(),
            "request_id": str(request.id),
        },
    )

    return request


async def resolve_data_request(
    request_id: uuid.UUID,
    response_notes: str,
    db: AsyncSession,
) -> DataRequest:
    """Mark a DSAR as resolved."""
    result = await db.execute(
        select(DataRequest).where(DataRequest.id == request_id)
    )
    request = result.scalar_one_or_none()
    if request is None:
        raise ValueError("Data request not found")

    request.status = "completed"
    request.response_notes = response_notes
    request.resolved_at = datetime.now(timezone.utc)

    await log_event(
        db,
        "data_request_resolved",
        user_id=request.user_id,
        metadata={"request_id": str(request_id)},
    )
    await db.flush()
    return request


async def get_pending_requests(db: AsyncSession) -> list[DataRequest]:
    """Get all pending DSAR requests, ordered by deadline (most urgent first)."""
    result = await db.execute(
        select(DataRequest)
        .where(DataRequest.status == "pending")
        .order_by(DataRequest.deadline_at.asc())
    )
    return list(result.scalars().all())
