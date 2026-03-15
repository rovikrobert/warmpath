"""Tests for vector-enhanced contact NLP search."""

import uuid

import pytest
from unittest.mock import AsyncMock, patch


class TestVectorContactSearch:
    """Integration of vector search into NLP contact search."""

    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_vector_search_returns_ranked_results(self):
        from app.services.nlp_contact_search import _vector_search_contacts

        user_id = uuid.uuid4()
        contact_id = uuid.uuid4()

        mock_search_results = [
            {
                "id": "point-1",
                "score": 0.92,
                "payload": {
                    "doc_type": "contact",
                    "contact_id": str(contact_id),
                    "user_id": str(user_id),
                    "warm_score": 75.0,
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
                return_value=mock_search_results,
            ),
        ):
            results = await _vector_search_contacts(
                user_id, "backend engineer at stripe"
            )

        assert len(results) == 1
        assert results[0]["contact_id"] == str(contact_id)
        assert results[0]["vector_score"] == 0.92

    @pytest.mark.asyncio
    async def test_vector_search_returns_empty_on_embed_failure(self):
        from app.services.nlp_contact_search import _vector_search_contacts

        with patch(
            "app.services.embedding_service.generate_embeddings",
            new_callable=AsyncMock,
            return_value=[],  # embedding failed
        ):
            results = await _vector_search_contacts(uuid.uuid4(), "some query")

        assert results == []

    @pytest.mark.asyncio
    async def test_vector_search_falls_back_on_qdrant_error(self):
        """When Qdrant raises an error, _try_vector_contact_search returns None."""
        from app.config import settings
        from app.services.nlp_contact_search import _try_vector_contact_search

        mock_settings = type(settings)(VECTOR_SEARCH_ENABLED=True)
        with (
            patch("app.config.settings", mock_settings),
            patch(
                "app.services.embedding_service.generate_embeddings",
                new_callable=AsyncMock,
                return_value=[[0.1] * 1536],
            ),
            patch(
                "app.services.vector_service.search_similar",
                new_callable=AsyncMock,
                side_effect=ConnectionError("unreachable"),
            ),
        ):
            result = await _try_vector_contact_search(
                uuid.uuid4(), "backend engineer", AsyncMock()
            )

        assert result is None

    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_vector_search_combines_with_warm_score(self):
        from app.services.nlp_contact_search import _combine_vector_and_warm

        results = [
            {"contact_id": "a", "vector_score": 0.90, "warm_score": 80.0},
            {"contact_id": "b", "vector_score": 0.70, "warm_score": 95.0},
        ]
        ranked = _combine_vector_and_warm(results)
        # a: 0.90*50 + 80*0.5 = 85.0
        # b: 0.70*50 + 95*0.5 = 82.5
        # a should be first
        assert ranked[0]["contact_id"] == "a"
