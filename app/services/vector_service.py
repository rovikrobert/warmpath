"""Qdrant vector service — collection management, upsert, search, delete.

Single unified collection with doc_type payload filter.
All operations are no-ops when VECTOR_SEARCH_ENABLED is False.
"""

import logging
import uuid
from qdrant_client import QdrantClient, models
from app.config import settings

logger = logging.getLogger(__name__)

_client: QdrantClient | None = None

# Namespace UUID for deterministic point IDs (UUID5)
_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def _get_qdrant_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY or None,
            timeout=10,
        )
    return _client


def make_point_id(doc_type: str, key: str) -> str:
    """Deterministic UUID5 point ID from doc_type + key."""
    return str(uuid.uuid5(_NAMESPACE, f"{doc_type}:{key}"))


async def ensure_collection() -> None:
    """Create the collection if it doesn't exist."""
    client = _get_qdrant_client()
    if client.collection_exists(settings.QDRANT_COLLECTION):
        return

    client.create_collection(
        collection_name=settings.QDRANT_COLLECTION,
        vectors_config=models.VectorParams(
            size=settings.OPENAI_EMBEDDING_DIMS,
            distance=models.Distance.COSINE,
        ),
    )
    # Create payload index for doc_type filter
    client.create_payload_index(
        collection_name=settings.QDRANT_COLLECTION,
        field_name="doc_type",
        field_schema=models.PayloadSchemaType.KEYWORD,
    )
    # Create payload index for user_id filter (contact search)
    client.create_payload_index(
        collection_name=settings.QDRANT_COLLECTION,
        field_name="user_id",
        field_schema=models.PayloadSchemaType.KEYWORD,
    )
    # Create payload index for company_id filter (job search)
    client.create_payload_index(
        collection_name=settings.QDRANT_COLLECTION,
        field_name="company_id",
        field_schema=models.PayloadSchemaType.KEYWORD,
    )
    logger.info("Created Qdrant collection '%s'", settings.QDRANT_COLLECTION)


async def upsert_points(
    ids: list[str],
    vectors: list[list[float]],
    payloads: list[dict],
) -> None:
    """Upsert points into the collection."""
    if not ids:
        return

    client = _get_qdrant_client()
    points = [
        models.PointStruct(id=pid, vector=vec, payload=pay)
        for pid, vec, pay in zip(ids, vectors, payloads, strict=True)
    ]
    client.upsert(
        collection_name=settings.QDRANT_COLLECTION,
        points=points,
        wait=True,
    )


async def search_similar(
    query_vector: list[float],
    doc_type: str,
    limit: int = 20,
    filters: dict | None = None,
) -> list[dict]:
    """Search for similar vectors filtered by doc_type and optional payload filters.

    Returns list of {"id": str, "score": float, "payload": dict}.
    """
    client = _get_qdrant_client()

    must_conditions = [
        models.FieldCondition(
            key="doc_type",
            match=models.MatchValue(value=doc_type),
        )
    ]
    if filters:
        for key, value in filters.items():
            must_conditions.append(
                models.FieldCondition(
                    key=key,
                    match=models.MatchValue(value=value),
                )
            )

    results = client.query_points(
        collection_name=settings.QDRANT_COLLECTION,
        query=query_vector,
        query_filter=models.Filter(must=must_conditions),
        limit=limit,
        with_payload=True,
    )

    return [
        {"id": point.id, "score": point.score, "payload": point.payload}
        for point in results.points
    ]


async def delete_points(point_ids: list[str]) -> None:
    """Delete specific points by ID."""
    if not point_ids:
        return

    client = _get_qdrant_client()
    client.delete(
        collection_name=settings.QDRANT_COLLECTION,
        points_selector=models.PointIdsList(points=point_ids),
    )
