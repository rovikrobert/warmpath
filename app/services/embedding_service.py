"""OpenAI embedding generation service.

Uses text-embedding-3-small (1536 dims) to convert text into vectors
for Qdrant semantic search. Handles batching (max 2048 per API call)
and graceful error handling.
"""

import logging
from openai import AsyncOpenAI
from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def build_contact_text(
    title: str | None = None,
    company: str | None = None,
    location: str | None = None,
    relationship_type: str | None = None,
    tags: list[str] | None = None,
) -> str:
    parts = []
    if title:
        parts.append(title)
    if company:
        parts.append(f"at {company}")
    if location:
        parts.append(f"in {location}")
    if relationship_type:
        parts.append(relationship_type.replace("_", " "))
    if tags:
        parts.append(", ".join(tags))
    return " ".join(parts) if parts else "unknown contact"


def build_listing_text(
    role_level: str,
    department_category: str,
    company_name: str,
) -> str:
    return f"{role_level} {department_category} at {company_name}"


def build_job_text(
    job_title: str,
    company_name: str,
    location: str | None = None,
) -> str:
    text = f"{job_title} at {company_name}"
    if location:
        text += f", {location}"
    return text


async def generate_embeddings(
    texts: list[str],
    batch_size: int = 2048,
) -> list[list[float]]:
    """Generate embeddings for a list of texts using OpenAI.

    Returns list of float vectors (1536 dims each).
    Returns empty list on error (graceful degradation).
    """
    if not texts:
        return []

    try:
        client = _get_openai_client()
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = await client.embeddings.create(
                input=batch,
                model=settings.OPENAI_EMBEDDING_MODEL,
                dimensions=settings.OPENAI_EMBEDDING_DIMS,
            )
            all_embeddings.extend([item.embedding for item in response.data])

        return all_embeddings

    except Exception:
        logger.exception("Failed to generate embeddings")
        return []
