"""Background CSV processing task.

Provides:
- process_csv_upload_core(): async function usable from both Celery and inline
- process_csv_upload: Celery task that wraps the core function
"""

import asyncio
import base64
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.celery_app import celery_app
from app.config import settings
from app.models.contact import Contact, CsvUpload
from app.models.user import ConnectorProfile
from app.services.company_normalizer import link_contact_to_company
from app.services.credits import earn_credits
from app.services.csv_parser import classify_relationship, parse_linkedin_csv
from app.services.suppression import check_suppression
from app.services.warm_scorer import batch_compute_scores
from app.utils.encryption import compute_blind_index


async def process_csv_upload_core(
    csv_upload_id: str,
    user_id: str,
    file_content_b64: str,
    db: AsyncSession,
) -> None:
    """Core CSV processing logic — reusable from Celery task or inline mode.

    Args:
        csv_upload_id: UUID string of the CsvUpload record.
        user_id: UUID string of the owning user.
        file_content_b64: Base64-encoded raw CSV bytes.
        db: An async SQLAlchemy session (caller manages commit/rollback).
    """
    upload_uuid = uuid.UUID(csv_upload_id)
    user_uuid = uuid.UUID(user_id)
    raw_bytes = base64.b64decode(file_content_b64)

    # Fetch the CsvUpload record
    result = await db.execute(select(CsvUpload).where(CsvUpload.id == upload_uuid))
    csv_upload = result.scalar_one()

    csv_upload.status = "processing"
    csv_upload.started_at = datetime.now(timezone.utc)
    await db.flush()

    try:
        parsed = parse_linkedin_csv(raw_bytes)
        csv_upload.row_count = len(parsed)

        # Load user's connector profile for relationship classification
        profile_result = await db.execute(
            select(ConnectorProfile).where(ConnectorProfile.user_id == user_uuid)
        )
        profile = profile_result.scalar_one_or_none()
        user_company = profile.current_company if profile else None
        user_work_history = (
            profile.work_history
            if profile and hasattr(profile, "work_history")
            else None
        )

        created = 0
        duplicates = 0
        suppressed_count = 0

        # Pre-load existing contacts by fingerprint for dedup (avoids N+1)
        all_fingerprints = [
            r.get("fingerprint") for r in parsed if r.get("fingerprint")
        ]
        existing_by_fp: dict = {}
        if all_fingerprints:
            fp_result = await db.execute(
                select(Contact).where(
                    Contact.user_id == user_uuid,
                    Contact.fingerprint.in_(all_fingerprints),
                    Contact.deleted_at.is_(None),
                )
            )
            existing_by_fp = {c.fingerprint: c for c in fp_result.scalars()}

        for row in parsed:
            # Check suppression list before inserting
            is_suppressed = await check_suppression(
                email=row.get("email"),
                first_name=row.get("first_name", ""),
                last_name=row.get("last_name", ""),
                company=row.get("current_company", ""),
                db=db,
            )
            if is_suppressed:
                suppressed_count += 1
                continue

            fingerprint = row.get("fingerprint")
            existing = existing_by_fp.get(fingerprint) if fingerprint else None

            # Auto-classify relationship (use row-level override if present)
            rel_type = row.get("relationship_type") or classify_relationship(
                row.get("current_company"),
                row.get("current_title"),
                user_company,
                user_work_history,
            )
            source = row.get("source", "linkedin_csv")

            # Pre-compute blind indexes for this row
            row_email = row.get("email")
            email_bi = compute_blind_index(row_email) if row_email else None
            name_co_bi = None
            fn = row.get("first_name", "")
            ln = row.get("last_name", "")
            co = row.get("current_company", "")
            if fn and ln and co:
                name_co_bi = compute_blind_index(f"{fn}{ln}{co}")

            if existing:
                # Update existing contact with fresh data
                existing.first_name = row["first_name"]
                existing.last_name = row["last_name"]
                existing.full_name = row["full_name"]
                existing.email = row.get("email") or existing.email
                existing.current_title = (
                    row.get("current_title") or existing.current_title
                )
                existing.current_company = (
                    row.get("current_company") or existing.current_company
                )
                existing.linkedin_url = row.get("linkedin_url") or existing.linkedin_url
                existing.connected_on = row.get("connected_on") or existing.connected_on
                existing.raw_csv_row = row.get("raw_csv_row")
                existing.csv_upload_id = csv_upload.id
                if rel_type and not existing.relationship_type:
                    existing.relationship_type = rel_type
                if row.get("how_you_know"):
                    existing.how_you_know = row["how_you_know"]
                if row.get("last_interaction_date"):
                    existing.last_interaction_date = row["last_interaction_date"]
                if row.get("location"):
                    existing.location = row["location"]
                # Update blind indexes
                if email_bi:
                    existing.email_blind_index = email_bi
                if name_co_bi:
                    existing.name_company_blind_index = name_co_bi
                await link_contact_to_company(existing, db)
                duplicates += 1
            else:
                contact = Contact(
                    user_id=user_uuid,
                    csv_upload_id=csv_upload.id,
                    first_name=row["first_name"],
                    last_name=row["last_name"],
                    full_name=row["full_name"],
                    email=row.get("email"),
                    current_title=row.get("current_title"),
                    current_company=row.get("current_company"),
                    linkedin_url=row.get("linkedin_url"),
                    connected_on=row.get("connected_on"),
                    fingerprint=fingerprint,
                    raw_csv_row=row.get("raw_csv_row"),
                    relationship_type=rel_type,
                    source=source,
                    how_you_know=row.get("how_you_know"),
                    last_interaction_date=row.get("last_interaction_date"),
                    location=row.get("location") or None,
                    email_blind_index=email_bi,
                    name_company_blind_index=name_co_bi,
                )
                db.add(contact)
                await db.flush()
                await link_contact_to_company(contact, db)
                # Track in map so duplicate rows within same CSV are caught
                if fingerprint:
                    existing_by_fp[fingerprint] = contact
                created += 1

        csv_upload.contacts_created = created
        csv_upload.duplicates_skipped = duplicates
        csv_upload.processed_count = created + duplicates
        csv_upload.error_count = 0
        csv_upload.status = "completed"
        csv_upload.completed_at = datetime.now(timezone.utc)

        # Auto-compute warm scores after upload
        await batch_compute_scores(user_uuid, db)

        # Award credits for CSV upload
        if created > 0:
            await earn_credits(
                user_uuid, 100, "csv_upload", db, reference_id=upload_uuid
            )

        # Clear raw CSV data after processing — matches privacy policy:
        # "CSV files deleted after processing"
        clear_result = await db.execute(
            select(Contact).where(Contact.csv_upload_id == csv_upload.id)
        )
        for c in clear_result.scalars():
            c.raw_csv_row = None

        await db.flush()

    except Exception as exc:
        csv_upload.status = "failed"
        csv_upload.error_message = str(exc)
        csv_upload.completed_at = datetime.now(timezone.utc)
        await db.flush()
        raise


@celery_app.task(bind=True)
def process_csv_upload(self, csv_upload_id: str, user_id: str, file_content_b64: str):
    """Celery task: process a CSV upload in the background.

    Creates its own async engine + session, then delegates to the core function.
    """
    asyncio.run(_celery_run(self, csv_upload_id, user_id, file_content_b64))


async def _celery_run(task, csv_upload_id, user_id, file_content_b64):
    """Async wrapper for the Celery task — owns its own DB connection."""
    url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(url, echo=False)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        try:
            await process_csv_upload_core(
                csv_upload_id, user_id, file_content_b64, session
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await engine.dispose()
