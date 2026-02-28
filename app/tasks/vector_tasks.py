"""Celery tasks for syncing data to Qdrant vector index.

Full reindex runs daily. Incremental sync tasks are called from
API routes after contact/listing/job mutations.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.celery_app import celery_app
from app.config import settings
from app.services.embedding_service import (
    build_contact_text,
    build_listing_text,
    build_job_text,
    generate_embeddings,
)
from app.services.vector_service import (
    ensure_collection,
    make_point_id,
    upsert_points,
)

logger = logging.getLogger(__name__)

BATCH_SIZE = 100  # Embed/upsert in batches of 100


def _get_engine():
    return create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)


def _get_session_factory():
    return async_sessionmaker(
        _get_engine(), class_=AsyncSession, expire_on_commit=False
    )


async def _load_contacts(user_id: uuid.UUID, db: AsyncSession):
    from app.models.contact import Contact

    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.deleted_at.is_(None),
        )
    )
    return list(result.scalars().all())


async def _load_warm_scores(
    user_id: uuid.UUID, contact_ids: list[uuid.UUID], db: AsyncSession
) -> dict[uuid.UUID, float]:
    from app.models.match_result import WarmScore

    result = await db.execute(
        select(WarmScore).where(
            WarmScore.user_id == user_id,
            WarmScore.contact_id.in_(contact_ids),
        )
    )
    return {ws.contact_id: float(ws.total_score) for ws in result.scalars().all()}


async def _sync_contacts_for_user(
    user_id: uuid.UUID, db: AsyncSession | None = None
) -> int:
    """Embed and upsert all contacts for a user. Returns count."""
    close_db = False
    if db is None:
        factory = _get_session_factory()
        db = factory()
        close_db = True

    try:
        contacts = await _load_contacts(user_id, db)
        if not contacts:
            return 0

        score_map = await _load_warm_scores(user_id, [c.id for c in contacts], db)

        # Build texts and metadata in batches
        count = 0
        for i in range(0, len(contacts), BATCH_SIZE):
            batch = contacts[i : i + BATCH_SIZE]
            texts = []
            ids = []
            payloads = []

            for c in batch:
                text = build_contact_text(
                    title=c.current_title,
                    company=c.current_company,
                    location=c.location,
                    relationship_type=c.relationship_type,
                    tags=c.tags,
                )
                texts.append(text)
                ids.append(make_point_id("contact", f"{user_id}:{c.id}"))
                payloads.append(
                    {
                        "doc_type": "contact",
                        "user_id": str(user_id),
                        "contact_id": str(c.id),
                        "company": c.current_company or "",
                        "warm_score": score_map.get(c.id, 0.0),
                        "relationship_type": c.relationship_type or "",
                    }
                )

            vectors = await generate_embeddings(texts)
            if vectors:
                await upsert_points(ids=ids, vectors=vectors, payloads=payloads)
                count += len(vectors)

        return count
    finally:
        if close_db:
            await db.close()


async def _load_listings(db: AsyncSession):
    from app.models.marketplace import MarketplaceListing
    from app.models.company import Company

    result = await db.execute(
        select(MarketplaceListing, Company.name)
        .join(Company, MarketplaceListing.company_id == Company.id)
        .where(
            MarketplaceListing.is_available.is_(True),
            MarketplaceListing.deleted_at.is_(None),
        )
    )
    return list(result.all())


async def _sync_listings(db: AsyncSession | None = None) -> int:
    """Embed and upsert all marketplace listings. Returns count."""
    close_db = False
    if db is None:
        factory = _get_session_factory()
        db = factory()
        close_db = True

    try:
        rows = await _load_listings(db)
        if not rows:
            return 0

        count = 0
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            texts = []
            ids = []
            payloads = []

            for listing, company_name in batch:
                text = build_listing_text(
                    role_level=listing.role_level,
                    department_category=listing.department_category,
                    company_name=company_name,
                )
                texts.append(text)
                ids.append(make_point_id("listing", str(listing.id)))
                payloads.append(
                    {
                        "doc_type": "listing",
                        "listing_id": str(listing.id),
                        "company_id": str(listing.company_id),
                        "role_level": listing.role_level,
                        "department_category": listing.department_category,
                        "warm_score_range": listing.warm_score_range,
                    }
                )

            vectors = await generate_embeddings(texts)
            if vectors:
                await upsert_points(ids=ids, vectors=vectors, payloads=payloads)
                count += len(vectors)

        return count
    finally:
        if close_db:
            await db.close()


async def _sync_jobs(db: AsyncSession | None = None) -> int:
    """Embed and upsert cached jobs. Returns count."""
    from app.models.enrichment import EnrichmentCache

    close_db = False
    if db is None:
        factory = _get_session_factory()
        db = factory()
        close_db = True

    try:
        result = await db.execute(
            select(EnrichmentCache).where(
                EnrichmentCache.source == "job_scan",
                EnrichmentCache.expires_at > datetime.now(timezone.utc),
            )
        )
        caches = list(result.scalars().all())
        if not caches:
            return 0

        count = 0
        all_texts = []
        all_ids = []
        all_payloads = []

        for cache_row in caches:
            raw_data = cache_row.data if isinstance(cache_row.data, dict) else {}
            jobs = raw_data.get("jobs", [])
            # cache_key format: "job_scan:{company_key}"
            company_name = cache_row.cache_key.replace("job_scan:", "")

            for job in jobs:
                title = job.get("title", "")
                location = job.get("location", "")
                text = build_job_text(
                    job_title=title,
                    company_name=company_name,
                    location=location,
                )
                dedup_key = f"{company_name}:{title}:{location}".lower()
                all_texts.append(text)
                all_ids.append(make_point_id("job", dedup_key))
                all_payloads.append(
                    {
                        "doc_type": "job",
                        "company": company_name,
                        "title": title,
                        "location": location,
                        "source": job.get("source", ""),
                    }
                )

        for i in range(0, len(all_texts), BATCH_SIZE):
            batch_texts = all_texts[i : i + BATCH_SIZE]
            batch_ids = all_ids[i : i + BATCH_SIZE]
            batch_payloads = all_payloads[i : i + BATCH_SIZE]

            vectors = await generate_embeddings(batch_texts)
            if vectors:
                await upsert_points(
                    ids=batch_ids, vectors=vectors, payloads=batch_payloads
                )
                count += len(vectors)

        return count
    finally:
        if close_db:
            await db.close()


async def _full_reindex() -> dict:
    """Full reindex: all contacts (all users), all listings, all jobs."""
    from app.models.user import User

    await ensure_collection()

    factory = _get_session_factory()
    async with factory() as db:
        # Get all user IDs
        result = await db.execute(select(User.id))
        user_ids = [row[0] for row in result.all()]

    contact_count = 0
    for uid in user_ids:
        contact_count += await _sync_contacts_for_user(uid)

    listing_count = await _sync_listings()
    job_count = await _sync_jobs()

    totals = {
        "contacts": contact_count,
        "listings": listing_count,
        "jobs": job_count,
    }
    logger.info("Full vector reindex complete: %s", totals)
    return totals


# --- Celery task wrappers (sync → asyncio.run) ---


@celery_app.task(
    bind=True,
    soft_time_limit=600,
    time_limit=660,
    acks_late=True,
    reject_on_worker_lost=True,
)
def full_vector_reindex(self) -> dict:
    """Daily full reindex of all vectors."""
    if not settings.VECTOR_SEARCH_ENABLED:
        return {"skipped": True, "reason": "VECTOR_SEARCH_ENABLED=false"}
    return asyncio.run(_full_reindex())


@celery_app.task(soft_time_limit=120, time_limit=150)
def sync_user_contacts(user_id: str) -> int:
    """Incremental sync after CSV import or contact update."""
    if not settings.VECTOR_SEARCH_ENABLED:
        return 0
    return asyncio.run(_sync_contacts_for_user(uuid.UUID(user_id)))


@celery_app.task(soft_time_limit=120, time_limit=150)
def sync_all_listings() -> int:
    """Incremental sync after listing create/delete."""
    if not settings.VECTOR_SEARCH_ENABLED:
        return 0
    return asyncio.run(_sync_listings())


@celery_app.task(soft_time_limit=120, time_limit=150)
def sync_all_jobs() -> int:
    """Incremental sync after job cache refresh."""
    if not settings.VECTOR_SEARCH_ENABLED:
        return 0
    return asyncio.run(_sync_jobs())
