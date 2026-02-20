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
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.models.contact import Contact, CsvUpload
from app.models.privacy import SuppressionList
from app.models.user import ConnectorProfile
from app.services.company_normalizer import link_contact_to_company
from app.services.credits import earn_credits
from app.services.ai_csv_cleaner import clean_contacts
from app.services.csv_parser import classify_relationship, parse_linkedin_csv
from app.services.warm_scorer import batch_compute_scores
from app.utils.encryption import compute_blind_index
from app.utils.hashing import hash_for_suppression
from app.utils.performance import timed


async def _publish_progress(factory, upload_id: uuid.UUID, **fields) -> None:
    """Commit progress fields in a separate transaction so polling sees them."""
    async with factory() as s:
        result = await s.execute(select(CsvUpload).where(CsvUpload.id == upload_id))
        upload = result.scalar_one()
        for k, v in fields.items():
            setattr(upload, k, v)
        await s.commit()


@timed("csv_process")
async def process_csv_upload_core(
    csv_upload_id: str,
    user_id: str,
    file_content_b64: str,
    db: AsyncSession,
    progress_callback=None,
) -> None:
    """Core CSV processing logic — reusable from Celery task or inline mode.

    Args:
        csv_upload_id: UUID string of the CsvUpload record.
        user_id: UUID string of the owning user.
        file_content_b64: Base64-encoded raw CSV bytes.
        db: An async SQLAlchemy session (caller manages commit/rollback).
        progress_callback: Optional async callable(upload_id, **fields) to
            publish progress milestones in a separate transaction.
    """
    upload_uuid = uuid.UUID(csv_upload_id)
    user_uuid = uuid.UUID(user_id)
    raw_bytes = base64.b64decode(file_content_b64)

    # Fetch the CsvUpload record
    result = await db.execute(select(CsvUpload).where(CsvUpload.id == upload_uuid))
    csv_upload = result.scalar_one()

    csv_upload.status = "processing"
    csv_upload.started_at = datetime.now(timezone.utc)
    csv_upload.progress_phase = "parsing"
    await db.flush()

    # Publish processing status so polling sees it immediately
    if progress_callback:
        await progress_callback(
            upload_uuid,
            status="processing",
            progress_phase="parsing",
            started_at=csv_upload.started_at,
        )

    try:
        parsed = parse_linkedin_csv(raw_bytes)
        csv_upload.row_count = len(parsed)

        # Publish row_count + cleaning phase
        if progress_callback:
            await progress_callback(
                upload_uuid,
                row_count=len(parsed),
                progress_phase="cleaning",
            )

        # AI-powered data cleanup (mock or real based on AI_MOCK_MODE)
        parsed = await clean_contacts(parsed)

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

        # Publish importing phase
        csv_upload.progress_phase = "importing"
        if progress_callback:
            await progress_callback(upload_uuid, progress_phase="importing")

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

        # Pre-load ALL suppression hashes in one query (avoids N+1)
        supp_result = await db.execute(
            select(SuppressionList.email_hash, SuppressionList.name_company_hash)
        )
        supp_rows = supp_result.all()
        suppressed_email_hashes = {r[0] for r in supp_rows if r[0]}
        suppressed_name_co_hashes = {r[1] for r in supp_rows if r[1]}

        for row in parsed:
            # Check suppression list via set membership (O(1) per row)
            email = row.get("email")
            if email and hash_for_suppression(email) in suppressed_email_hashes:
                suppressed_count += 1
                continue

            fn = row.get("first_name", "")
            ln = row.get("last_name", "")
            co = row.get("current_company", "")
            name_co_key = f"{fn}{ln}{co}"
            if hash_for_suppression(name_co_key) in suppressed_name_co_hashes:
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

            # Pre-compute blind indexes (reuse fn/ln/co/email from suppression check)
            email_bi = compute_blind_index(email) if email else None
            name_co_bi = None
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

            # Publish incremental progress every 50 contacts
            processed_so_far = created + duplicates + suppressed_count
            if progress_callback and processed_so_far % 50 == 0:
                await progress_callback(upload_uuid, processed_count=processed_so_far)

        csv_upload.contacts_created = created
        csv_upload.duplicates_skipped = duplicates
        csv_upload.processed_count = created + duplicates
        csv_upload.error_count = 0
        csv_upload.progress_phase = "scoring"

        # Publish scoring phase
        if progress_callback:
            await progress_callback(
                upload_uuid,
                processed_count=created + duplicates,
                progress_phase="scoring",
            )

        # Auto-compute warm scores after upload
        await batch_compute_scores(user_uuid, db)

        # Award credits for CSV upload
        if created > 0:
            await earn_credits(
                user_uuid, 100, "csv_upload", db, reference_id=upload_uuid
            )

        # Data freshness bonus: 10 credits if re-uploading (not first upload)
        from sqlalchemy import func as sa_func

        upload_count_result = await db.execute(
            select(sa_func.count()).select_from(
                select(CsvUpload.id)
                .where(
                    CsvUpload.user_id == user_uuid,
                    CsvUpload.status == "completed",
                )
                .subquery()
            )
        )
        upload_count = upload_count_result.scalar() or 0
        if upload_count > 1 and created > 0:
            await earn_credits(
                user_uuid, 10, "data_freshness", db, reference_id=upload_uuid
            )

        csv_upload.status = "completed"
        csv_upload.completed_at = datetime.now(timezone.utc)
        csv_upload.progress_phase = None

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
        csv_upload.progress_phase = None
        await db.flush()
        raise


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660)
def process_csv_upload(
    self, csv_upload_id: str, user_id: str, file_content_b64: str
) -> None:
    """Celery task: process a CSV upload in the background.

    Uses shared DB engine from database.py, delegates to the core function.
    """
    import logging

    logger = logging.getLogger(__name__)
    logger.info("Worker received task %s for upload %s", self.request.id, csv_upload_id)
    asyncio.run(_celery_run(self, csv_upload_id, user_id, file_content_b64))
    logger.info("Worker completed task for upload %s", csv_upload_id)


async def _celery_run(task, csv_upload_id, user_id, file_content_b64):
    """Async wrapper for the Celery task — uses shared DB engine."""
    import logging

    from app.database import _get_session_factory

    logger = logging.getLogger(__name__)
    factory = _get_session_factory()

    async def publish(upload_id, **fields):
        await _publish_progress(factory, upload_id, **fields)

    async with factory() as session:
        try:
            await process_csv_upload_core(
                csv_upload_id,
                user_id,
                file_content_b64,
                session,
                progress_callback=publish,
            )
            await session.commit()
        except Exception as exc:
            await session.rollback()
            # Write error status in a separate transaction so it survives
            # the rollback above (the flush in process_csv_upload_core is
            # lost when we rollback the main transaction).
            try:
                async with factory() as err_session:
                    result = await err_session.execute(
                        select(CsvUpload).where(
                            CsvUpload.id == uuid.UUID(csv_upload_id)
                        )
                    )
                    upload = result.scalar_one_or_none()
                    if upload and upload.status != "completed":
                        upload.status = "failed"
                        upload.error_message = str(exc)[:500]
                        upload.completed_at = datetime.now(timezone.utc)
                        await err_session.commit()
            except Exception:
                logger.exception(
                    "Failed to persist error status for upload %s",
                    csv_upload_id,
                )
            raise
