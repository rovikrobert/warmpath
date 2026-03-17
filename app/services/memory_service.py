"""Unified Memory Service — write path (remember) + read path (hybrid BM25+vector search).

Provides a single interface for agents, Claude Code sessions, and CoS to
persist and retrieve memories.  Memories are stored in Postgres with optional
Qdrant vector embeddings for semantic search.

Read pipeline:
  1. BM25 keyword search (tsvector on Postgres, LIKE fallback on SQLite)
  2. Vector search (Qdrant cosine similarity)
  3. Score normalisation + hybrid merge
  4. Temporal decay (exponential half-life)
  5. Importance boost
  6. MMR re-ranking for diversity
"""

from __futu[RESEND_KEY_REDACTED] import annotations

import asyncio
import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.memory import Memory

logger = logging.getLogger(__name__)

# Namespace UUID for deterministic Qdrant point IDs (different from vector_service)
_MEMORY_NAMESPACE = uuid.UUID("b2c3d4e5-f6a7-8901-bcde-f23456789012")


def _make_embedding_id(memory_id: uuid.UUID) -> str:
    """Deterministic UUID5 point ID for a memory in Qdrant."""
    return str(uuid.uuid5(_MEMORY_NAMESPACE, str(memory_id)))


# ---------------------------------------------------------------------------
# Helpers: Qdrant operations (sync, run via asyncio.to_thread)
# ---------------------------------------------------------------------------


def _ensu[RESEND_KEY_REDACTED]() -> None:
    """Create the warmpath_memory Qdrant collection if it doesn't exist."""
    from qdrant_client import models

    from app.services.vector_service import _get_qdrant_client

    client = _get_qdrant_client()
    collection = settings.MEMORY_QDRANT_COLLECTION

    if client.collection_exists(collection):
        return

    client.create_collection(
        collection_name=collection,
        vectors_config=models.VectorParams(
            size=settings.OPENAI_EMBEDDING_DIMS,
            distance=models.Distance.COSINE,
        ),
    )
    for field_name in ("source_type", "team", "importance"):
        client.create_payload_index(
            collection_name=collection,
            field_name=field_name,
            field_schema=models.PayloadSchemaType.KEYWORD
            if field_name != "importance"
            else models.PayloadSchemaType.FLOAT,
        )
    logger.info("Created Qdrant memory collection '%s'", collection)


def _upsert_memory_vector(
    point_id: str,
    vector: list[float],
    payload: dict[str, Any],
) -> None:
    """Upsert a single memory vector into Qdrant (sync)."""
    from qdrant_client import models

    from app.services.vector_service import _get_qdrant_client

    client = _get_qdrant_client()
    client.upsert(
        collection_name=settings.MEMORY_QDRANT_COLLECTION,
        points=[models.PointStruct(id=point_id, vector=vector, payload=payload)],
        wait=True,
    )


def _search_memory_vectors_sync(
    query_vector: list[float],
    limit: int,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Search the memory collection (sync). Returns [{id, score, payload}]."""
    from qdrant_client import models

    from app.services.vector_service import _get_qdrant_client

    client = _get_qdrant_client()
    must_conditions: list[models.FieldCondition] = []
    if filters:
        for key, value in filters.items():
            must_conditions.append(
                models.FieldCondition(key=key, match=models.MatchValue(value=value))
            )

    query_filter = models.Filter(must=must_conditions) if must_conditions else None

    results = client.query_points(
        collection_name=settings.MEMORY_QDRANT_COLLECTION,
        query=query_vector,
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
    )
    return [
        {"id": point.id, "score": point.score, "payload": point.payload}
        for point in results.points
    ]


# ---------------------------------------------------------------------------
# SQLite vs Postgres detection
# ---------------------------------------------------------------------------


def _is_sqlite(db: AsyncSession) -> bool:
    """Return True if the session is bound to a SQLite backend."""
    bind = db.get_bind()
    return bind.dialect.name == "sqlite"


# ---------------------------------------------------------------------------
# Score normalisation helpers
# ---------------------------------------------------------------------------


def _normalize_scores(scores: dict[uuid.UUID, float]) -> dict[uuid.UUID, float]:
    """Min-max normalise scores to [0, 1]."""
    if not scores:
        return {}
    values = list(scores.values())
    lo, hi = min(values), max(values)
    span = hi - lo
    if span == 0:
        return {k: 1.0 for k in scores}
    return {k: (v - lo) / span for k, v in scores.items()}


def _word_overlap_similarity(a: str, b: str) -> float:
    """Jaccard-style word overlap as a simple similarity proxy for MMR."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


# ---------------------------------------------------------------------------
# MemoryService
# ---------------------------------------------------------------------------


class MemoryService:
    """Unified memory store — write (remember) and read (recall) paths."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -----------------------------------------------------------------------
    # Write path
    # -----------------------------------------------------------------------

    async def remember(
        self,
        content: str,
        source_type: str,
        source_id: str,
        *,
        summary: str | None = None,
        team: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
        ttl_hours: int | None = None,
    ) -> uuid.UUID:
        """Store a memory in Postgres + optionally embed in Qdrant.

        Returns the memory UUID.
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=ttl_hours) if ttl_hours else None

        mem = Memory(
            source_type=source_type,
            source_id=source_id,
            team=team,
            content=content,
            summary=summary,
            tags=tags,
            metadata_=metadata,
            importance=importance,
            expires_at=expires_at,
        )
        self.db.add(mem)
        await self.db.commit()
        await self.db.refresh(mem)

        # --- Optional vector embedding ---
        if settings.VECTOR_SEARCH_ENABLED:
            await self._embed_memory(mem)

        return mem.id

    async def _embed_memory(self, mem: Memory) -> None:
        """Generate embedding and upsert to Qdrant. Logs warning on failure."""
        try:
            from app.services.embedding_service import generate_embeddings

            text_to_embed = mem.summary or mem.content
            embeddings = await generate_embeddings([text_to_embed])
            if not embeddings:
                logger.warning(
                    "Empty embedding for memory %s — skipping Qdrant upsert", mem.id
                )
                return

            point_id = _make_embedding_id(mem.id)
            payload: dict[str, Any] = {
                "memory_id": str(mem.id),
                "source_type": mem.source_type,
                "content_preview": mem.content[:500],
            }
            if mem.team:
                payload["team"] = mem.team
            if mem.importance is not None:
                payload["importance"] = mem.importance

            # Ensure collection exists, then upsert
            await asyncio.to_thread(_ensu[RESEND_KEY_REDACTED])
            await asyncio.to_thread(
                _upsert_memory_vector, point_id, embeddings[0], payload
            )

            # Store embedding_id back on the row
            mem.embedding_id = uuid.UUID(point_id)
            self.db.add(mem)
            await self.db.commit()

        except Exception:
            logger.exception(
                "Failed to embed memory %s — continuing without vector", mem.id
            )

    # -----------------------------------------------------------------------
    # Read path
    # -----------------------------------------------------------------------

    async def recall(
        self,
        query: str,
        *,
        top_k: int = 10,
        team: str | None = None,
        source_type: str | None = None,
        bm25_weight: float | None = None,
        vector_weight: float | None = None,
        temporal_half_life: int | None = None,
        mmr_lambda: float | None = None,
    ) -> list[dict[str, Any]]:
        """Hybrid BM25 + vector search with temporal decay and MMR re-ranking.

        Returns up to *top_k* memories as dicts, ordered by final score.
        """
        if not query or not query.strip():
            return []

        bm25_w = bm25_weight if bm25_weight is not None else settings.MEMORY_BM25_WEIGHT
        vec_w = (
            vector_weight
            if vector_weight is not None
            else settings.MEMORY_VECTOR_WEIGHT
        )
        half_life = (
            temporal_half_life
            if temporal_half_life is not None
            else settings.MEMORY_TEMPORAL_HALF_LIFE_DAYS
        )
        lam = mmr_lambda if mmr_lambda is not None else settings.MEMORY_MMR_LAMBDA
        candidate_pool = settings.MEMORY_CANDIDATE_POOL

        # 1. BM25 keyword search
        bm25_scores = await self._bm25_search(
            query, candidate_pool, team=team, source_type=source_type
        )

        # 2. Vector search (if enabled)
        vector_scores: dict[uuid.UUID, float] = {}
        if settings.VECTOR_SEARCH_ENABLED:
            vector_scores = await self._vector_search(
                query, candidate_pool, team=team, source_type=source_type
            )

        # Collect all candidate IDs
        all_ids = set(bm25_scores.keys()) | set(vector_scores.keys())
        if not all_ids:
            return []

        # 3. Normalise each source to [0, 1]
        norm_bm25 = _normalize_scores(bm25_scores)
        norm_vec = _normalize_scores(vector_scores)

        # Hybrid merge
        hybrid: dict[uuid.UUID, float] = {}
        for mid in all_ids:
            b = norm_bm25.get(mid, 0.0)
            v = norm_vec.get(mid, 0.0)
            hybrid[mid] = bm25_w * b + vec_w * v

        # Fetch Memory rows for all candidates
        rows = await self._fetch_memories_by_ids(list(all_ids))
        row_map: dict[uuid.UUID, Memory] = {r.id: r for r in rows}

        # 4. Temporal decay
        now = datetime.now(timezone.utc)
        decay_lambda = math.log(2) / half_life if half_life > 0 else 0.0
        for mid, score in hybrid.items():
            mem = row_map.get(mid)
            if mem and mem.created_at:
                created = mem.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                days_old = max((now - created).total_seconds() / 86400, 0)
                score *= math.exp(-decay_lambda * days_old)
            hybrid[mid] = score

        # 5. Importance boost: score *= (0.5 + importance * 0.5)
        for mid in hybrid:
            mem = row_map.get(mid)
            if mem:
                hybrid[mid] *= 0.5 + mem.importance * 0.5

        # 6. MMR re-ranking
        selected = self._mmr_rerank(hybrid, row_map, lam, top_k)

        return [
            self._row_to_dict(row_map[mid], hybrid[mid])
            for mid in selected
            if mid in row_map
        ]

    # -----------------------------------------------------------------------
    # BM25 — Postgres tsvector or SQLite LIKE fallback
    # -----------------------------------------------------------------------

    async def _bm25_search(
        self,
        query: str,
        limit: int,
        *,
        team: str | None = None,
        source_type: str | None = None,
    ) -> dict[uuid.UUID, float]:
        """Keyword search returning {memory_id: raw_score}."""
        if not query or not query.strip():
            return {}
        if _is_sqlite(self.db):
            return await self._bm25_search_sqlite(
                query, limit, team=team, source_type=source_type
            )
        return await self._bm25_search_postgres(
            query, limit, team=team, source_type=source_type
        )

    async def _bm25_search_postgres(
        self,
        query: str,
        limit: int,
        *,
        team: str | None = None,
        source_type: str | None = None,
    ) -> dict[uuid.UUID, float]:
        """Full-text search using Postgres tsvector/tsquery."""
        whe[RESEND_KEY_REDACTED] = [
            "plainto_tsquery('english', :query) @@ content_tsv",
            "(expires_at IS NULL OR expires_at > NOW())",
        ]
        params: dict[str, Any] = {"query": query, "limit": limit}

        if team:
            whe[RESEND_KEY_REDACTED].append("team = :team")
            params["team"] = team
        if source_type:
            whe[RESEND_KEY_REDACTED].append("source_type = :source_type")
            params["source_type"] = source_type

        whe[RESEND_KEY_REDACTED] = " AND ".join(whe[RESEND_KEY_REDACTED])
        sql = text(
            "SELECT id, ts_rank_cd(content_tsv, plainto_tsquery('english', :query)) AS rank"
            " FROM memories"
            " WHERE " + whe[RESEND_KEY_REDACTED] + " ORDER BY rank DESC"
            " LIMIT :limit"
        )

        result = await self.db.execute(sql, params)
        return {row[0]: float(row[1]) for row in result.fetchall()}

    async def _bm25_search_sqlite(
        self,
        query: str,
        limit: int,
        *,
        team: str | None = None,
        source_type: str | None = None,
    ) -> dict[uuid.UUID, float]:
        """LIKE-based keyword fallback for SQLite (test environment)."""
        now = datetime.now(timezone.utc)
        stmt = select(Memory).where(
            (Memory.expires_at.is_(None)) | (Memory.expires_at > now)
        )
        if team:
            stmt = stmt.where(Memory.team == team)
        if source_type:
            stmt = stmt.where(Memory.source_type == source_type)

        result = await self.db.execute(stmt)
        rows = result.scalars().all()

        # Score by keyword overlap: count how many query words appear in content
        query_words = [w.lower() for w in query.split() if len(w) > 1]
        scores: dict[uuid.UUID, float] = {}
        for mem in rows:
            content_lower = mem.content.lower()
            hits = sum(1 for w in query_words if w in content_lower)
            if hits > 0:
                scores[mem.id] = hits / max(len(query_words), 1)

        # Sort and limit
        sorted_ids = sorted(scores, key=scores.get, reverse=True)[:limit]
        return {mid: scores[mid] for mid in sorted_ids}

    # -----------------------------------------------------------------------
    # Vector search (Qdrant)
    # -----------------------------------------------------------------------

    async def _vector_search(
        self,
        query: str,
        limit: int,
        *,
        team: str | None = None,
        source_type: str | None = None,
    ) -> dict[uuid.UUID, float]:
        """Semantic search via Qdrant. Returns {memory_id: cosine_score}."""
        try:
            from app.services.embedding_service import generate_embeddings

            embeddings = await generate_embeddings([query])
            if not embeddings:
                return {}

            filters: dict[str, Any] = {}
            if team:
                filters["team"] = team
            if source_type:
                filters["source_type"] = source_type

            results = await asyncio.to_thread(
                _search_memory_vectors_sync, embeddings[0], limit, filters or None
            )

            scores: dict[uuid.UUID, float] = {}
            for hit in results:
                payload = hit.get("payload", {})
                memory_id_str = payload.get("memory_id")
                if memory_id_str:
                    scores[uuid.UUID(memory_id_str)] = float(hit["score"])
            return scores

        except Exception:
            logger.exception("Vector search failed — falling back to BM25 only")
            return {}

    # -----------------------------------------------------------------------
    # MMR re-ranking
    # -----------------------------------------------------------------------

    @staticmethod
    def _mmr_rerank(
        scores: dict[uuid.UUID, float],
        row_map: dict[uuid.UUID, Memory],
        lam: float,
        top_k: int,
    ) -> list[uuid.UUID]:
        """Maximal Marginal Relevance: iteratively pick diverse, relevant items.

        Score = lambda * relevance - (1 - lambda) * max_similarity_to_selected
        Similarity proxy: word overlap between content strings.
        """
        if not scores:
            return []

        candidates = set(scores.keys())
        selected: list[uuid.UUID] = []
        max_iterations = min(top_k, 100)  # Cap to prevent runaway loops

        while len(selected) < max_iterations and candidates:
            best_id: uuid.UUID | None = None
            best_mmr = -float("inf")

            for cid in candidates:
                relevance = scores.get(cid, 0.0)
                max_sim = 0.0
                c_content = row_map[cid].content if cid in row_map else ""
                for sid in selected:
                    s_content = row_map[sid].content if sid in row_map else ""
                    sim = _word_overlap_similarity(c_content, s_content)
                    max_sim = max(max_sim, sim)
                mmr_score = lam * relevance - (1 - lam) * max_sim
                if mmr_score > best_mmr:
                    best_mmr = mmr_score
                    best_id = cid

            if best_id is None:
                break
            selected.append(best_id)
            candidates.discard(best_id)

        return selected

    # -----------------------------------------------------------------------
    # Convenience methods
    # -----------------------------------------------------------------------

    async def recall_about_file(
        self, file_path: str, *, top_k: int = 5
    ) -> list[dict[str, Any]]:
        """Find memories tagged with a specific file path."""
        if not file_path or not file_path.strip():
            return []

        now = datetime.now(timezone.utc)

        if _is_sqlite(self.db):
            # SQLite stores ARRAY as JSON — can't use @> operator.
            # Cap the scan to 500 rows to avoid loading entire table.
            stmt = (
                select(Memory)
                .where((Memory.expires_at.is_(None)) | (Memory.expires_at > now))
                .order_by(Memory.created_at.desc())
                .limit(500)
            )
            result = await self.db.execute(stmt)
            rows = result.scalars().all()
            # Python-side filtering: parse JSON tags and check membership
            import json as _json

            matched = []
            for mem in rows:
                tags = mem.tags
                if isinstance(tags, str):
                    tags = _json.loads(tags)
                if tags and file_path in tags:
                    matched.append(mem)
            matched.sort(
                key=lambda m: m.created_at or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )
            return [self._row_to_dict(m) for m in matched[:top_k]]
        else:
            # Postgres: use ARRAY contains
            stmt = (
                select(Memory)
                .where(Memory.tags.any(file_path))
                .where((Memory.expires_at.is_(None)) | (Memory.expires_at > now))
                .order_by(Memory.created_at.desc())
                .limit(top_k)
            )
            result = await self.db.execute(stmt)
            return [self._row_to_dict(m) for m in result.scalars().all()]

    async def recall_recent(
        self,
        *,
        days: int = 7,
        team: str | None = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Get most recent memories, optionally filtered by team."""
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=days)

        stmt = (
            select(Memory)
            .where(Memory.created_at >= since)
            .where((Memory.expires_at.is_(None)) | (Memory.expires_at > now))
        )
        if team:
            stmt = stmt.where(Memory.team == team)
        stmt = stmt.order_by(Memory.created_at.desc()).limit(top_k)

        result = await self.db.execute(stmt)
        return [self._row_to_dict(m) for m in result.scalars().all()]

    # -----------------------------------------------------------------------
    # Fetch helpers
    # -----------------------------------------------------------------------

    async def _fetch_memories_by_ids(self, ids: list[uuid.UUID]) -> list[Memory]:
        """Load Memory rows by primary key."""
        if not ids:
            return []
        stmt = select(Memory).where(Memory.id.in_(ids))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def _row_to_dict(row: Memory, score: float | None = None) -> dict[str, Any]:
        """Convert Memory ORM to dict."""
        import json as _json

        tags = row.tags
        if isinstance(tags, str):
            tags = _json.loads(tags)

        metadata = row.metadata_
        if isinstance(metadata, str):
            metadata = _json.loads(metadata)

        d: dict[str, Any] = {
            "id": str(row.id),
            "source_type": row.source_type,
            "source_id": row.source_id,
            "team": row.team,
            "content": row.content,
            "summary": row.summary,
            "tags": tags,
            "metadata": metadata,
            "importance": row.importance,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        }
        if score is not None:
            d["score"] = score
        return d
