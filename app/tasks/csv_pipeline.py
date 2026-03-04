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


async def _create_gemini_cache(csv_upload_id: str) -> str | None:
    """Create a Gemini context cache for this upload if enabled."""
    if not settings.GEMINI_CACHE_ENABLED:
        return None
    try:
        from app.utils.gemini_cache import create_cleanup_cache
        from app.utils.gemini_client import get_gemini_client

        gemini_client = get_gemini_client()
        return await create_cleanup_cache(gemini_client, csv_upload_id)
    except Exception:
        logger.warning(
            "Gemini cache creation failed for upload %s, proceeding without cache",
            csv_upload_id,
            exc_info=True,
        )
        return None


async def _notify_csv_completion(
    factory,
    user_uuid: uuid.UUID,
    upload_uuid: uuid.UUID,
    contacts_created: int,
    duplicates_skipped: int,
) -> None:
    """Send completion email and create feed item after CSV import finishes."""
    # Feed item
    try:
        from app.services.feed_generator import generate_csv_completion

        async with factory() as session:
            items = await generate_csv_completion(
                user_uuid, session, upload_uuid, contacts_created, duplicates_skipped
            )
            await session.commit()
            if items:
                logger.info("Created CSV completion feed item for user %s", user_uuid)
    except Exception:
        logger.warning(
            "Failed to create CSV completion feed item for user %s",
            user_uuid,
            exc_info=True,
        )

    # Email
    try:
        from app.models.user import User
        from app.services.email_engagement import send_csv_completion_email

        async with factory() as session:
            result = await session.execute(select(User).where(User.id == user_uuid))
            user = result.scalar_one_or_none()
            if user:
                await send_csv_completion_email(user, session, contacts_created)
                await session.commit()
    except Exception:
        logger.warning(
            "Failed to send CSV completion email for user %s",
            user_uuid,
            exc_info=True,
        )


async def _delete_gemini_cache(cache_name: str | None) -> None:
    """Delete a Gemini context cache if one was created."""
    if not cache_name:
        return
    try:
        from app.utils.gemini_cache import delete_cleanup_cache
        from app.utils.gemini_client import get_gemini_client

        await delete_cleanup_cache(get_gemini_client(), cache_name)
    except Exception:
        logger.warning("Failed to delete Gemini cache %s", cache_name, exc_info=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_session_factory():
    from app.database import _get_session_factory

    return _get_session_factory()


async def _dispose_engine():
    """Dispose old engine and clear caches so fresh objects are created in
    the current asyncio.run() event loop.  Without this, a cached
    sessionmaker/engine from a previous Celery task (different loop) causes:
    ``RuntimeError: Future attached to a different loop``
    """
    import contextlib

    from app.database import _get_engine, _get_session_factory

    with contextlib.suppress(Exception):
        await _get_engine().dispose()
    _get_engine.cache_clear()
    _get_session_factory.cache_clear()


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


def _is_gemini_enabled() -> bool:
    """Check if Gemini is available for batch processing."""
    from app.services.ai_provider_pool import _is_provider_enabled

    return _is_provider_enabled("gemini")


async def _submit_batch_mode(
    factory,
    upload_uuid: uuid.UUID,
    csv_upload_id: str,
    user_id: str,
    batches: list[list[dict]],
) -> None:
    """Submit batches to Gemini batch API and start polling."""
    from app.services.gemini_batch import submit_cleanup_batch
    from app.utils.gemini_client import get_gemini_client

    client = get_gemini_client()
    job_name = await submit_cleanup_batch(client, batches, csv_upload_id)

    if job_name:
        # Store raw batches in Redis for post-processing after batch completes
        from app.utils.redis_streams import _get_redis_client

        redis = _get_redis_client()
        if redis:
            try:
                key = f"csv:batch_originals:{csv_upload_id}"
                # TTL must exceed max poll duration (120 polls * 60s = 7200s)
                # Use 10800s (3h) for safety margin
                await redis.set(key, json.dumps(batches, default=str), ex=10800)
            except Exception:
                logger.warning(
                    "Failed to store batch originals in Redis for upload %s",
                    csv_upload_id,
                    exc_info=True,
                )
            finally:
                await redis.aclose()

        await _update_upload(
            factory,
            upload_uuid,
            progress_phase="batch_submitted",
            batch_job_name=job_name,
        )
        # Start polling for results
        try:
            poll_gemini_batch.apply_async(
                args=[csv_upload_id, user_id, 0],
                countdown=settings.GEMINI_BATCH_POLL_INTERVAL,
            )
        except Exception:
            logger.warning(
                "Failed to schedule poll task for upload %s, falling back to real-time",
                csv_upload_id,
                exc_info=True,
            )
            await _update_upload(
                factory, upload_uuid, progress_phase="cleaning", batch_job_name=None
            )
            csv_clean_worker.delay(csv_upload_id, user_id)
    else:
        # Batch submission failed — fall back to real-time
        logger.warning(
            "Batch submission failed for upload %s, falling back to real-time",
            csv_upload_id,
        )
        csv_clean_worker.delay(csv_upload_id, user_id)


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

        # Route: batch mode for large uploads, real-time for smaller ones
        total_contacts = len(parsed)
        # Enforce minimum floor of 100 contacts for batch mode
        batch_threshold = max(settings.GEMINI_BATCH_THRESHOLD, 100)
        if total_contacts > batch_threshold and _is_gemini_enabled():
            # Large upload — submit to Gemini batch API
            logger.info(
                "Upload %s has %d contacts (> %d threshold), using batch mode",
                csv_upload_id,
                total_contacts,
                batch_threshold,
            )
            await _submit_batch_mode(
                factory, upload_uuid, csv_upload_id, user_id, batches
            )
        else:
            # Normal upload — real-time provider pool
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

    cache_name = await _create_gemini_cache(csv_upload_id)

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

            cleaned = await asyncio.wait_for(
                dispatch_batch(contacts, cache_name=cache_name), timeout=120
            )
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

    await _delete_gemini_cache(cache_name)

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
                try:
                    await earn_credits(
                        user_uuid,
                        100,
                        "csv_upload",
                        session,
                        reference_id=upload_uuid,
                    )
                except ValueError:
                    logger.warning(
                        "Could not award upload credits for %s (daily cap likely reached)",
                        upload_uuid,
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

            # Send completion notifications (email + feed item)
            await _notify_csv_completion(
                factory, user_uuid, upload_uuid, created, duplicates
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


# ---------------------------------------------------------------------------
# Gemini Batch Polling
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.tasks.csv_pipeline.poll_gemini_batch",
    soft_time_limit=120,
    time_limit=180,
    max_retries=120,  # ~2 hours at 60s intervals
    acks_late=True,
    reject_on_worker_lost=True,
)
def poll_gemini_batch(csv_upload_id: str, user_id: str, poll_count: int = 0) -> None:
    """Poll Gemini batch job status. Re-schedules itself until complete."""
    asyncio.run(_poll_batch_async(csv_upload_id, user_id, poll_count))


async def _poll_batch_async(csv_upload_id: str, user_id: str, poll_count: int) -> None:
    await _dispose_engine()
    factory = _get_session_factory()
    upload_uuid = uuid.UUID(csv_upload_id)

    from app.services.gemini_batch import TERMINAL_STATES, get_batch_results
    from app.utils.gemini_client import get_gemini_client

    # Load upload to get batch_job_name
    async with factory() as session:
        result = await session.execute(
            select(CsvUpload).where(CsvUpload.id == upload_uuid)
        )
        upload = result.scalar_one_or_none()
        if not upload:
            logger.warning("Upload %s not found during batch poll", csv_upload_id)
            return
        job_name = upload.batch_job_name

    if not job_name:
        logger.error("No batch_job_name for upload %s", csv_upload_id)
        return

    client = get_gemini_client()
    state, results = await get_batch_results(client, job_name)

    logger.info(
        "Batch poll #%d for upload %s: state=%s", poll_count, csv_upload_id, state
    )

    if state == "JOB_STATE_SUCCEEDED" and results is not None:
        # Load original batches from Redis for post-processing
        from app.services.ai_csv_cleaner import post_process_ai_output
        from app.utils.redis_streams import _get_redis_client

        original_batches = None
        redis = _get_redis_client()
        if redis:
            try:
                raw = await redis.get(f"csv:batch_originals:{csv_upload_id}")
                original_batches = json.loads(raw) if raw else None
            except Exception:
                logger.warning(
                    "Failed to load batch originals from Redis for upload %s",
                    csv_upload_id,
                    exc_info=True,
                )
            finally:
                await redis.aclose()

        if not original_batches:
            # Originals lost (Redis eviction/restart) — fall back to real-time
            # rather than importing contacts without fingerprints/emails/names
            logger.warning(
                "Batch originals lost for upload %s, falling back to real-time",
                csv_upload_id,
            )
            await _update_upload(
                factory, upload_uuid, progress_phase="cleaning", batch_job_name=None
            )
            csv_clean_worker.delay(csv_upload_id, user_id)
            return

        # Use original chunk count for sentinel (not len(results) which may
        # be fewer if some chunks failed in the batch)
        total_chunks = len(original_batches)

        # Write results to cleaned stream and trigger import
        stream_out = cleaned_stream_key(csv_upload_id)
        await ensure_consumer_group(stream_out, "importers")

        for i, chunk_results in enumerate(results):
            cleaned = []
            if i < len(original_batches):
                for j, ai_fields in enumerate(chunk_results):
                    if j < len(original_batches[i]):
                        cleaned.append(
                            post_process_ai_output(original_batches[i][j], ai_fields)
                        )
                    else:
                        cleaned.append(ai_fields)
            else:
                cleaned = chunk_results  # Extra results beyond originals

            await write_batch_to_stream(stream_out, cleaned, i)

        await write_sentinel(stream_out, total_chunks)

        # Clean up Redis originals
        redis = _get_redis_client()
        if redis:
            try:
                await redis.delete(f"csv:batch_originals:{csv_upload_id}")
            except Exception:
                pass  # Will expire via TTL anyway
            finally:
                await redis.aclose()

        await _update_upload(
            factory,
            upload_uuid,
            progress_phase="importing",
            chunks_cleaned=len(results),
        )

        # Trigger import stage
        csv_import_task.delay(csv_upload_id, user_id)

    elif state in TERMINAL_STATES:
        # Failed/cancelled/expired — fall back to real-time pipeline
        logger.warning(
            "Batch job %s ended with state %s, falling back to real-time",
            job_name,
            state,
        )
        await _update_upload(
            factory, upload_uuid, progress_phase="cleaning", batch_job_name=None
        )
        csv_clean_worker.delay(csv_upload_id, user_id)

    elif poll_count >= settings.GEMINI_BATCH_MAX_POLLS:
        # Timeout — fall back to real-time
        logger.warning(
            "Batch poll timeout for upload %s after %d polls",
            csv_upload_id,
            poll_count,
        )
        await _update_upload(
            factory, upload_uuid, progress_phase="cleaning", batch_job_name=None
        )
        csv_clean_worker.delay(csv_upload_id, user_id)

    else:
        # Still running — re-schedule
        poll_gemini_batch.apply_async(
            args=[csv_upload_id, user_id, poll_count + 1],
            countdown=settings.GEMINI_BATCH_POLL_INTERVAL,
        )
