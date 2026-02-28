"""Tests for vector sync Celery tasks."""

import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestSyncContactsTask:
    """Test contact vectorization logic."""

    @pytest.mark.asyncio
    async def test_builds_text_and_upserts(self):
        from app.tasks.vector_tasks import _sync_contacts_for_user

        user_id = uuid.uuid4()
        mock_contact = MagicMock()
        mock_contact.id = uuid.uuid4()
        mock_contact.current_title = "Engineer"
        mock_contact.current_company = "Stripe"
        mock_contact.location = "Singapore"
        mock_contact.relationship_type = "former_colleague"
        mock_contact.tags = ["python"]
        mock_contact.deleted_at = None

        mock_db = AsyncMock()

        with (
            patch(
                "app.tasks.vector_tasks._load_contacts",
                new_callable=AsyncMock,
                return_value=[mock_contact],
            ),
            patch(
                "app.tasks.vector_tasks._load_warm_scores",
                new_callable=AsyncMock,
                return_value={mock_contact.id: 85.0},
            ),
            patch(
                "app.tasks.vector_tasks.generate_embeddings",
                new_callable=AsyncMock,
                return_value=[[0.1] * 1536],
            ) as mock_embed,
            patch(
                "app.tasks.vector_tasks.upsert_points",
                new_callable=AsyncMock,
            ) as mock_upsert,
        ):
            await _sync_contacts_for_user(user_id, db=mock_db)

        mock_embed.assert_called_once()
        mock_upsert.assert_called_once()
        # Verify payload includes user_id and contact_id
        call_args = mock_upsert.call_args
        payload = call_args.kwargs["payloads"][0]
        assert payload["doc_type"] == "contact"
        assert payload["user_id"] == str(user_id)
        assert payload["contact_id"] == str(mock_contact.id)
        assert payload["warm_score"] == 85.0


class TestSyncListingsTask:
    """Test listing vectorization logic."""

    @pytest.mark.asyncio
    async def test_builds_text_and_upserts(self):
        from app.tasks.vector_tasks import _sync_listings

        mock_listing = MagicMock()
        mock_listing.id = uuid.uuid4()
        mock_listing.role_level = "senior"
        mock_listing.department_category = "engineering"
        mock_listing.warm_score_range = "high"
        mock_listing.connection_recency = "recent"
        mock_listing.network_holder_id = uuid.uuid4()
        mock_listing.company_id = uuid.uuid4()
        mock_listing.is_available = True
        mock_listing.deleted_at = None

        mock_db = AsyncMock()

        with (
            patch(
                "app.tasks.vector_tasks._load_listings",
                new_callable=AsyncMock,
                return_value=[(mock_listing, "Stripe")],
            ),
            patch(
                "app.tasks.vector_tasks.generate_embeddings",
                new_callable=AsyncMock,
                return_value=[[0.2] * 1536],
            ) as mock_embed,
            patch(
                "app.tasks.vector_tasks.upsert_points",
                new_callable=AsyncMock,
            ) as mock_upsert,
        ):
            await _sync_listings(db=mock_db)

        mock_embed.assert_called_once()
        mock_upsert.assert_called_once()
        payload = mock_upsert.call_args.kwargs["payloads"][0]
        assert payload["doc_type"] == "listing"
