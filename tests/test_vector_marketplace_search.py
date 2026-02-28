"""Tests for vector-enhanced marketplace search."""

import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestVectorMarketplaceSearch:
    """Vector search for marketplace listings."""

    @pytest.mark.asyncio
    async def test_vector_marketplace_search_returns_listing_ids(self):
        from app.api.marketplace import _vector_marketplace_search

        mock_results = [
            {
                "id": "point-1",
                "score": 0.88,
                "payload": {
                    "doc_type": "listing",
                    "listing_id": str(uuid.uuid4()),
                    "role_level": "senior",
                    "department_category": "engineering",
                },
            }
        ]

        with (
            patch(
                "app.services.embedding_service.generate_embeddings",
                new_callable=AsyncMock,
                return_value=[[0.1] * 1536],
            ),
            patch(
                "app.services.vector_service.search_similar",
                new_callable=AsyncMock,
                return_value=mock_results,
            ),
        ):
            listing_ids = await _vector_marketplace_search(
                query="fintech engineering lead",
                role_levels=None,
                departments=None,
            )

        assert len(listing_ids) == 1

    @pytest.mark.asyncio
    async def test_returns_empty_on_embed_failure(self):
        from app.api.marketplace import _vector_marketplace_search

        with patch(
            "app.services.embedding_service.generate_embeddings",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await _vector_marketplace_search("query")

        assert result == []
