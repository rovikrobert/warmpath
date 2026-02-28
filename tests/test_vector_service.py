"""Tests for vector_service — Qdrant client wrapper."""

import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestPointId:
    """UUID5 deterministic point IDs."""

    def test_contact_point_id_deterministic(self):
        from app.services.vector_service import make_point_id

        user_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        contact_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        id1 = make_point_id("contact", f"{user_id}:{contact_id}")
        id2 = make_point_id("contact", f"{user_id}:{contact_id}")
        assert id1 == id2  # deterministic

    def test_different_types_different_ids(self):
        from app.services.vector_service import make_point_id

        id1 = make_point_id("contact", "same-key")
        id2 = make_point_id("listing", "same-key")
        assert id1 != id2


class TestEnsureCollection:
    """Collection initialization."""

    @pytest.mark.asyncio
    async def test_creates_collection_if_not_exists(self):
        from app.services.vector_service import ensu[RESEND_KEY_REDACTED]

        mock_client = MagicMock()
        mock_client.collection_exists = MagicMock(return_value=False)
        mock_client.create_collection = MagicMock()
        mock_client.create_payload_index = MagicMock()

        with patch(
            "app.services.vector_service._get_qdrant_client",
            return_value=mock_client,
        ):
            await ensu[RESEND_KEY_REDACTED]()

        mock_client.create_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_if_collection_exists(self):
        from app.services.vector_service import ensu[RESEND_KEY_REDACTED]

        mock_client = MagicMock()
        mock_client.collection_exists = MagicMock(return_value=True)

        with patch(
            "app.services.vector_service._get_qdrant_client",
            return_value=mock_client,
        ):
            await ensu[RESEND_KEY_REDACTED]()

        mock_client.create_collection.assert_not_called()


class TestUpsertPoints:
    """Upsert vectors into Qdrant."""

    @pytest.mark.asyncio
    async def test_upsert_single_point(self):
        from app.services.vector_service import upsert_points

        mock_client = MagicMock()
        mock_client.upsert = MagicMock()

        with patch(
            "app.services.vector_service._get_qdrant_client",
            return_value=mock_client,
        ):
            await upsert_points(
                ids=["point-1"],
                vectors=[[0.1] * 1536],
                payloads=[{"doc_type": "contact", "user_id": "abc"}],
            )

        mock_client.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_empty_is_noop(self):
        from app.services.vector_service import upsert_points

        mock_client = MagicMock()

        with patch(
            "app.services.vector_service._get_qdrant_client",
            return_value=mock_client,
        ):
            await upsert_points(ids=[], vectors=[], payloads=[])

        mock_client.upsert.assert_not_called()


class TestSearch:
    """Vector similarity search."""

    @pytest.mark.asyncio
    async def test_search_contacts(self):
        from app.services.vector_service import search_similar

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.score = 0.95
        mock_point.payload = {"doc_type": "contact", "contact_id": "abc"}

        mock_client = MagicMock()
        mock_client.query_points = MagicMock(
            return_value=MagicMock(points=[mock_point])
        )

        with patch(
            "app.services.vector_service._get_qdrant_client",
            return_value=mock_client,
        ):
            results = await search_similar(
                query_vector=[0.1] * 1536,
                doc_type="contact",
                limit=10,
                filters={"user_id": "user-123"},
            )

        assert len(results) == 1
        assert results[0]["score"] == 0.95
        assert results[0]["payload"]["contact_id"] == "abc"


class TestDeletePoints:
    """Delete points by filter."""

    @pytest.mark.asyncio
    async def test_delete_by_contact_id(self):
        from app.services.vector_service import delete_points

        mock_client = MagicMock()
        mock_client.delete = MagicMock()

        with patch(
            "app.services.vector_service._get_qdrant_client",
            return_value=mock_client,
        ):
            await delete_points(point_ids=["point-1", "point-2"])

        mock_client.delete.assert_called_once()
