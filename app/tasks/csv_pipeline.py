"""Streaming CSV processing pipeline (V2).

4-stage pipeline connected by Redis Streams:
  Stage 1 - Parse: chunk CSV into batches, write to parsed stream
  Stage 2 - Clean: consume from parsed stream, AI clean, write to cleaned stream
  Stage 3 - Import: consume from cleaned stream, insert to DB
  Stage 4 - Score: compute warm scores, award credits, cleanup

Activated by CSV_PIPELINE_V2=true feature flag.
"""

import asyncio
import base64
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.celery_app import celery_app
from app.config import settings
from app.models.contact import Contact, CsvUpload
from app.models.csv_chunk import CsvUploadChunk
from app.models.company import Company
from app.models.privacy import SuppressionList
from app.models.user import ConnectorProfile
from app.services.csv_parser import classify_relationship, parse_linkedin_csv
from app.services.credits import earn_credits
from app.services.warm_scorer import batch_compute_scores
from app.utils.encryption import compute_blind_index
from app.utils.hashing import hash_for_suppression
from app.utils.redis_streams import (
    cleaned_stream_key,
    delete_stream,
    ensure_consumer_group,
    parsed_stream_key,
    stream_ack,
    stream_read_group,
    write_batch_to_stream,
    write_sentinel,
)

logger = logging.getLogger(__name__)

IMPORT_BATCH_SIZE = 500
CLEAN_CONSUMER_GROUP = "cleaners"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_session_factory():
    from app.database import _get_session_factory

    return _get_session_factory()


async def _dispose_engine():
    from app.database import _get_engine

    await _get_engine().dispose()


async def _update_upload(factory, upload_id: uuid.UUID, **fields) -> None:
    """Update CsvUpload fields in a separate transaction."""
    async with factory() as s:
        result = await s.execute(select(CsvUpload).where(CsvUpload.id == upload_id))
        upload = result.scalar_one()
        for k, v in fields.items():
            setattr(upload, k, v)
        await s.commit()


# ---------------------------------------------------------------------------
# Stage 1: Parse
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.tasks.csv_pipeline.csv_parse_task",
    soft_time_limit=120,
    time_limit=180,
)
def csv_parse_task(csv_upload_id: str, user_id: str, file_content_b64: str) -> None:
    """Parse CSV and write batches to Redis Stream."""
    asyncio.run(_parse_async(csv_upload_id, user_id, file_content_b64))


async def _parse_async(csv_upload_id: str, user_id: str, file_content_b64: str) -> None:
    await _dispose_engine()
    factory = _get_session_factory()
    upload_uuid = uuid.UUID(csv_upload_id)

    try:
        raw_bytes = base64.b64decode(file_content_b64)
        parsed = parse_linkedin_csv(raw_bytes)

        # Chunk into batches
        chunk_size = settings.CSV_CHUNK_SIZE
        batches = [
            parsed[i : i + chunk_size] for i in range(0, len(parsed), chunk_size)
        ]
        total_batches = len(batches)

        # Update upload with row count and total chunks
        await _update_upload(
            factory,
            upload_uuid,
            status="processing",
            progress_phase="cleaning",
            row_count=len(parsed),
            total_chunks=total_batches,
            started_at=datetime.now(timezone.utc),
        )

        # Create chunk records in DB
        async with factory() as session:
            for i, batch in enumerate(batches):
                chunk = CsvUploadChunk(
                    upload_id=upload_uuid,
                    chunk_index=i,
                    contacts_count=len(batch),
                    status="pending",
                )
                session.add(chunk)
            await session.commit()

        # Write batches to Redis Stream
        stream = parsed_stream_key(csv_upload_id)
        await ensure_consumer_group(stream, CLEAN_CONSUMER_GROUP)

        for i, batch in enumerate(batches):
            await write_batch_to_stream(stream, batch, i)

        await write_sentinel(stream, total_batches)

        logger.info(
            "Parse complete: %d contacts in %d batches -> stream %s",
            len(parsed),
            total_batches,
            stream,
        )

        # Dispatch clean worker for this upload
        csv_clean_worker.delay(csv_upload_id, user_id)

    except Exception as exc:
        logger.exception("Parse failed for upload %s", csv_upload_id)
        await _update_upload(
            factory,
            upload_uuid,
            status="failed",
            error_message=str(exc)[:500],
            completed_at=datetime.now(timezone.utc),
            progress_phase=None,
        )


# ---------------------------------------------------------------------------
# Stage 2: Clean
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.tasks.csv_pipeline.csv_clean_worker",
    soft_time_limit=600,
    time_limit=660,
)
def csv_clean_worker(csv_upload_id: str, user_id: str) -> None:
    """Consume batches from parsed stream, AI clean, write to cleaned stream."""
    asyncio.run(_clean_async(csv_upload_id, user_id))


async def _clean_async(csv_upload_id: str, user_id: str) -> None:
    await _dispose_engine()
    factory = _get_session_factory()
    upload_uuid = uuid.UUID(csv_upload_id)

    from app.services.ai_provider_pool import dispatch_batch, warm_up_providers

    warm_up_providers()

    stream_in = parsed_stream_key(csv_upload_id)
    stream_out = cleaned_stream_key(csv_upload_id)
    consumer_name = f"worker-{uuid.uuid4().hex[:8]}"

    await ensure_consumer_group(stream_in, CLEAN_CONSUMER_GROUP)
    await ensure_consumer_group(stream_out, "importers")

    # Phase 1: Collect all batch messages from stream
    pending = []  # (msg_id, chunk_index, contacts)
    total_batches = None
    max_empty_reads = 60  # 5 seconds block * 60 = 5 minutes max wait
    empty_reads = 0

    while True:
        messages = await stream_read_group(
            stream_in, CLEAN_CONSUMER_GROUP, consumer_name, count=50, block=5000
        )

        if not messages:
            empty_reads += 1
            if total_batches is not None and len(pending) >= total_batches:
                break
            if empty_reads >= max_empty_reads:
                logger.warning(
                    "Clean worker timed out waiting for messages (upload %s)",
                    csv_upload_id,
                )
                break
            continue

        empty_reads = 0
        for msg_id, fields in messages:
            data = json.loads(fields["data"])

            if data.get("sentinel"):
                total_batches = data["total_batches"]
                await stream_ack(stream_in, CLEAN_CONSUMER_GROUP, msg_id)
                await write_sentinel(stream_out, total_batches)
                continue

            pending.append((msg_id, data["chunk_index"], data["contacts"]))

        if total_batches is not None and len(pending) >= total_batches:
            break

    # Phase 2: Dispatch all batches concurrently across providers
    batches_cleaned = 0

    async def _clean_one(msg_id, chunk_index, contacts):
        nonlocal batches_cleaned

        try:
            async with factory() as session:
                result = await session.execute(
                    select(CsvUploadChunk).where(
                        CsvUploadChunk.upload_id == upload_uuid,
                        CsvUploadChunk.chunk_index == chunk_index,
                    )
                )
                chunk = result.scalar_one_or_none()
                if chunk:
                    chunk.status = "cleaning"
                    await session.commit()

            cleaned = await asyncio.wait_for(dispatch_batch(contacts), timeout=120)
            await write_batch_to_stream(stream_out, cleaned, chunk_index)

            async with factory() as session:
                result = await session.execute(
                    select(CsvUploadChunk).where(
                        CsvUploadChunk.upload_id == upload_uuid,
                        CsvUploadChunk.chunk_index == chunk_index,
                    )
                )
                chunk = result.scalar_one_or_none()
                if chunk:
                    chunk.status = "cleaned"
                    chunk.completed_at = datetime.now(timezone.utc)
                    await session.commit()

        except Exception:
            logger.exception(
                "Clean failed for chunk %d of upload %s",
                chunk_index,
                csv_upload_id,
            )
            from app.services.ai_csv_cleaner import clean_contacts_mock

            fallback = clean_contacts_mock(contacts)
            await write_batch_to_stream(stream_out, fallback, chunk_index)

        batches_cleaned += 1
        await _update_upload(factory, upload_uuid, chunks_cleaned=batches_cleaned)
        await stream_ack(stream_in, CLEAN_CONSUMER_GROUP, msg_id)

    logger.info(
        "Dispatching %d batches concurrently for upload %s",
        len(pending),
        csv_upload_id,
    )
    await asyncio.gather(
        *[_clean_one(mid, ci, cts) for mid, ci, cts in pending],
        return_exceptions=True,
    )

    logger.info(
        "Clean complete: %d batches for upload %s", batches_cleaned, csv_upload_id
    )

    # Trigger import stage
    csv_import_task.delay(csv_upload_id, user_id)


# ---------------------------------------------------------------------------
# Stage 3: Import (combines import + scoring)
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.tasks.csv_pipeline.csv_import_task",
    soft_time_limit=900,
    time_limit=960,
    acks_late=True,
    reject_on_worker_lost=True,
)
def csv_import_task(csv_upload_id: str, user_id: str) -> None:
    """Consume cleaned batches from stream and import to DB."""
    asyncio.run(_import_async(csv_upload_id, user_id))


async def _process_contact_row(
    row: dict,
    session,
    user_uuid: uuid.UUID,
    upload_uuid: uuid.UUID,
    suppressed_email_hashes: set,
    suppressed_name_co_hashes: set,
    existing_fps: dict,
    user_company: str | None,
    user_work_history: dict | None,
) -> str:
    """Process a single contact row. Returns 'created', 'duplicate', or 'suppressed'."""
    # Suppression check
    email = row.get("email")
    if email and hash_for_suppression(email) in suppressed_email_hashes:
        return "suppressed"

    fn = row.get("first_name", "")
    ln = row.get("last_name", "")
    co = row.get("current_company", "")
    name_co_key = f"{fn}{ln}{co}"
    if hash_for_suppression(name_co_key) in suppressed_name_co_hashes:
        return "suppressed"

    fingerprint = row.get("fingerprint")

    # Dedup: check DB
    if fingerprint and fingerprint not in existing_fps:
        fp_result = await session.execute(
            select(Contact.id, Contact.fingerprint).where(
                Contact.user_id == user_uuid,
                Contact.fingerprint == fingerprint,
                Contact.deleted_at.is_(None),
            )
        )
        existing_row = fp_result.first()
        if existing_row:
            existing_fps[fingerprint] = existing_row[0]

    existing_id = existing_fps.get(fingerprint) if fingerprint else None

    rel_type = row.get("relationship_type") or classify_relationship(
        row.get("current_company"),
        row.get("current_title"),
        user_company,
        user_work_history,
    )
    source = row.get("source", "linkedin_csv")

    email_bi = compute_blind_index(email) if email else None
    name_co_bi = None
    if fn and ln and co:
        name_co_bi = compute_blind_index(f"{fn}{ln}{co}")

    if existing_id:
        return "duplicate"

    # Parse connected_on — JSON serialization through Redis turns dates to strings
    connected_on = row.get("connected_on")
    if isinstance(connected_on, str):
        try:
            connected_on = datetime.strptime(connected_on, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            connected_on = None

    contact = Contact(
        user_id=user_uuid,
        csv_upload_id=upload_uuid,
        first_name=row.get("first_name"),
        last_name=row.get("last_name"),
        full_name=row.get("full_name"),
        email=row.get("email"),
        current_title=row.get("current_title"),
        current_company=row.get("current_company"),
        linkedin_url=row.get("linkedin_url"),
        connected_on=connected_on,
        fingerprint=fingerprint,
        relationship_type=rel_type,
        source=source,
        phone=row.get("phone"),
        email_blind_index=email_bi,
        name_company_blind_index=name_co_bi,
    )
    session.add(contact)
    if fingerprint:
        existing_fps[fingerprint] = contact.id
    return "created"


async def _import_async(csv_upload_id: str, user_id: str) -> None:
    await _dispose_engine()
    factory = _get_session_factory()
    upload_uuid = uuid.UUID(csv_upload_id)
    user_uuid = uuid.UUID(user_id)

    stream_in = cleaned_stream_key(csv_upload_id)
    consumer_name = f"importer-{uuid.uuid4().hex[:8]}"

    await ensure_consumer_group(stream_in, "importers")
    await _update_upload(factory, upload_uuid, progress_phase="importing")

    total_batches = None
    batches_imported = 0
    max_empty_reads = 60

    async with factory() as session:
        try:
            # Pre-load user context
            profile_result = await session.execute(
                select(ConnectorProfile).where(ConnectorProfile.user_id == user_uuid)
            )
            profile = profile_result.scalar_one_or_none()
            user_company = profile.current_company if profile else None
            user_work_history = (
                profile.work_history
                if profile and hasattr(profile, "work_history")
                else None
            )

            # Pre-load suppression set
            supp_result = await session.execute(
                select(SuppressionList.email_hash, SuppressionList.name_company_hash)
            )
            supp_rows = supp_result.all()
            suppressed_email_hashes = {r[0] for r in supp_rows if r[0]}
            suppressed_name_co_hashes = {r[1] for r in supp_rows if r[1]}

            # Pre-load company cache
            co_result = await session.execute(select(Company))
            _company_cache: dict[str, uuid.UUID | None] = {
                co.name.lower(): co.id for co in co_result.scalars()
            }

            existing_fps: dict = {}
            created = 0
            duplicates = 0
            suppressed_count = 0

            empty_reads = 0
            while True:
                messages = await stream_read_group(
                    stream_in, "importers", consumer_name, count=1, block=5000
                )

                if not messages:
                    empty_reads += 1
                    if total_batches is not None and batches_imported >= total_batches:
                        break
                    if empty_reads >= max_empty_reads:
                        logger.warning(
                            "Importer timed out waiting for messages (upload %s)",
                            csv_upload_id,
                        )
                        break
                    continue

                empty_reads = 0
                for msg_id, fields in messages:
                    data = json.loads(fields["data"])

                    if data.get("sentinel"):
                        total_batches = data["total_batches"]
                        await stream_ack(stream_in, "importers", msg_id)
                        continue

                    contacts = data["contacts"]

                    for row in contacts:
                        result = await _process_contact_row(
                            row,
                            session,
                            user_uuid,
                            upload_uuid,
                            suppressed_email_hashes,
                            suppressed_name_co_hashes,
                            existing_fps,
                            user_company,
                            user_work_history,
                        )
                        if result == "suppressed":
                            suppressed_count += 1
                        elif result == "duplicate":
                            duplicates += 1
                        else:
                            created += 1

                    # Flush and checkpoint after each batch
                    await session.flush()
                    batches_imported += 1

                    await _update_upload(
                        factory,
                        upload_uuid,
                        chunks_imported=batches_imported,
                        processed_count=created + duplicates + suppressed_count,
                    )
                    await stream_ack(stream_in, "importers", msg_id)

            # Finalize
            await session.flush()

            # Score
            await _update_upload(factory, upload_uuid, progress_phase="scoring")
            await batch_compute_scores(user_uuid, session)

            if created > 0:
                await earn_credits(
                    user_uuid,
                    100,
                    "csv_upload",
                    session,
                    reference_id=upload_uuid,
                )

            # Strip raw CSV data
            await session.execute(
                update(Contact)
                .where(Contact.csv_upload_id == upload_uuid)
                .values(raw_csv_row=None)
            )

            await session.commit()

            # Mark complete and cleanup
            await _update_upload(
                factory,
                upload_uuid,
                status="completed",
                contacts_created=created,
                duplicates_skipped=duplicates,
                processed_count=created + duplicates,
                completed_at=datetime.now(timezone.utc),
                progress_phase=None,
            )

            # Cleanup Redis streams
            await delete_stream(parsed_stream_key(csv_upload_id))
            await delete_stream(cleaned_stream_key(csv_upload_id))

            logger.info(
                "Import complete for upload %s: %d created, %d duplicates, %d suppressed",
                csv_upload_id,
                created,
                duplicates,
                suppressed_count,
            )

        except Exception as exc:
            await session.rollback()
            logger.exception("Import failed for upload %s", csv_upload_id)
            await _update_upload(
                factory,
                upload_uuid,
                status="failed",
                error_message=str(exc)[:500],
                completed_at=datetime.now(timezone.utc),
                progress_phase=None,
            )
            raise
