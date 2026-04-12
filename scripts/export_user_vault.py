"""Export a user's vault data to JSON for sunset data-portability.

Usage:
    python3 -m scripts.export_user_vault --user-id <uuid> --output <path>

Exports: user profile, contacts (decrypted), uploads metadata, intro requests.
Read-only — no DB writes performed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact, CsvUpload
from app.models.marketplace import IntroFacilitation
from app.models.user import User


def _serialize(value: Any) -> Any:
    """Convert non-JSON-serializable types to strings."""
    if isinstance(value, (uuid.UUID,)):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _row_to_dict(obj: Any, fields: list[str]) -> dict[str, Any]:
    """Extract named fields from a SQLAlchemy ORM object into a plain dict."""
    result: dict[str, Any] = {}
    for field in fields:
        val = getattr(obj, field, None)
        result[field] = _serialize(val)
    return result


async def export_user_vault(
    user_id: str,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    """Return a dict with the user's full vault data.

    Args:
        user_id: UUID string of the user to export.
        db: Optional AsyncSession for testing. When None, a production session
            is created from the app database settings.

    Raises:
        ValueError: If no user with the given user_id exists.
    """
    own_session = db is None
    if own_session:
        from app.database import _get_session_factory

        session_factory = _get_session_factory()
        db = session_factory()

    try:
        return await _do_export(user_id=user_id, db=db)
    finally:
        if own_session:
            await db.close()


async def _do_export(user_id: str, db: AsyncSession) -> dict[str, Any]:
    uid = uuid.UUID(user_id)

    # --- User ---
    user_result = await db.execute(select(User).where(User.id == uid))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise ValueError("User not found")

    user_dict = _row_to_dict(
        user,
        [
            "id",
            "email",
            "full_name",
            "clerk_user_id",
            "email_verified",
            "intent",
            "onboarding_completed",
            "created_at",
            "updated_at",
        ],
    )

    # --- Contacts (active only — exclude soft-deleted) ---
    contacts_result = await db.execute(
        select(Contact).where(
            Contact.user_id == uid,
            Contact.deleted_at.is_(None),
        )
    )
    contacts = contacts_result.scalars().all()
    contact_fields = [
        "id",
        "csv_upload_id",
        "first_name",
        "last_name",
        "full_name",
        "email",
        "linkedin_url",
        "phone",
        "current_title",
        "current_company",
        "location",
        "connected_on",
        "relationship_type",
        "source",
        "how_you_know",
        "would_refer",
        "warm_score_override",
        "notes",
        "tags",
        "last_interaction_date",
        "created_at",
        "updated_at",
    ]
    contacts_list = [_row_to_dict(c, contact_fields) for c in contacts]

    # --- Uploads ---
    uploads_result = await db.execute(select(CsvUpload).where(CsvUpload.user_id == uid))
    uploads = uploads_result.scalars().all()
    upload_fields = [
        "id",
        "filename",
        "file_size_bytes",
        "row_count",
        "processed_count",
        "contacts_created",
        "status",
        "error_message",
        "started_at",
        "completed_at",
        "created_at",
    ]
    uploads_list = [_row_to_dict(u, upload_fields) for u in uploads]

    # --- Intro requests (as job seeker) ---
    intros_result = await db.execute(
        select(IntroFacilitation).where(IntroFacilitation.job_seeker_id == uid)
    )
    intros = intros_result.scalars().all()
    intro_fields = [
        "id",
        "marketplace_listing_id",
        "network_holder_id",
        "status",
        "requested_at",
        "reviewed_at",
        "completed_at",
        "delivery_method",
        "delivery_status",
        "delivered_at",
        "created_at",
        "updated_at",
    ]
    intros_list = [_row_to_dict(i, intro_fields) for i in intros]

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": user_dict,
        "contacts": contacts_list,
        "uploads": uploads_list,
        "intro_requests": intros_list,
    }


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


async def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Export a user's vault data to JSON (sunset data-portability)."
    )
    parser.add_argument("--user-id", required=True, help="UUID of the user to export")
    parser.add_argument(
        "--output", required=True, help="Path to write the JSON output file"
    )
    args = parser.parse_args()

    data = await export_user_vault(user_id=args.user_id)

    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)

    contact_count = len(data["contacts"])
    upload_count = len(data["uploads"])
    intro_count = len(data["intro_requests"])
    print(
        f"Exported vault for {data['user']['email']}: "
        f"{contact_count} contacts, {upload_count} uploads, {intro_count} intro requests"
    )
    print(f"Output written to: {args.output}")


if __name__ == "__main__":
    asyncio.run(_main())
