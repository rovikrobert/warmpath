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
                "app.tasks.vector_tasks.ensu[RESEND_KEY_REDACTED]",
                new_callable=AsyncMock,
            ),
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
        mock_listing.warm_sco[RESEND_KEY_REDACTED] = "high"
        mock_listing.connection_recency = "recent"
        mock_listing.network_holder_id = uuid.uuid4()
        mock_listing.company_id = uuid.uuid4()
        mock_listing.is_available = True
        mock_listing.deleted_at = None

        mock_db = AsyncMock()

        with (
            patch(
                "app.tasks.vector_tasks.ensu[RESEND_KEY_REDACTED]",
                new_callable=AsyncMock,
            ),
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
        assert payload["listing_id"] == str(mock_listing.id)
        # Privacy: network_holder_id must NOT be in Qdrant payloads
        assert "network_holder_id" not in payload


class TestSyncJobsTask:
    """Test job vectorization logic."""

    @pytest.mark.asyncio
    async def test_builds_text_and_upserts_jobs(self):
        from app.tasks.vector_tasks import _sync_jobs

        mock_cache = MagicMock()
        mock_cache.cache_key = "job_scan:stripe"
        mock_cache.source = "job_scan"
        mock_cache.data = {
            "jobs": [
                {
                    "title": "Backend Engineer",
                    "location": "Singapore",
                    "source": "board",
                }
            ]
        }

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_cache]
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with (
            patch(
                "app.tasks.vector_tasks.ensu[RESEND_KEY_REDACTED]",
                new_callable=AsyncMock,
            ),
            patch(
                "app.tasks.vector_tasks.generate_embeddings",
                new_callable=AsyncMock,
                return_value=[[0.3] * 1536],
            ) as mock_embed,
            patch(
                "app.tasks.vector_tasks.upsert_points",
                new_callable=AsyncMock,
            ) as mock_upsert,
        ):
            count = await _sync_jobs(db=mock_db)

        assert count == 1
        mock_embed.assert_called_once()
        mock_upsert.assert_called_once()
        payload = mock_upsert.call_args.kwargs["payloads"][0]
        assert payload["doc_type"] == "job"
        assert payload["company"] == "stripe"
        assert payload["title"] == "Backend Engineer"


class TestCeleryTaskGating:
    """Celery wrappers skip when VECTOR_SEARCH_ENABLED=false."""

    def test_full_reindex_skips_when_disabled(self):
        from app.tasks.vector_tasks import full_vector_reindex

        with patch("app.tasks.vector_tasks.settings", VECTOR_SEARCH_ENABLED=False):
            result = full_vector_reindex()

        assert result == {"skipped": True, "reason": "VECTOR_SEARCH_ENABLED=false"}

    def test_sync_contacts_skips_when_disabled(self):
        from app.tasks.vector_tasks import sync_user_contacts

        with patch("app.tasks.vector_tasks.settings", VECTOR_SEARCH_ENABLED=False):
            result = sync_user_contacts(str(uuid.uuid4()))

        assert result == 0

    def test_sync_listings_skips_when_disabled(self):
        from app.tasks.vector_tasks import sync_all_listings

        with patch("app.tasks.vector_tasks.settings", VECTOR_SEARCH_ENABLED=False):
            result = sync_all_listings()

        assert result == 0

    def test_sync_jobs_skips_when_disabled(self):
        from app.tasks.vector_tasks import sync_all_jobs

        with patch("app.tasks.vector_tasks.settings", VECTOR_SEARCH_ENABLED=False):
            result = sync_all_jobs()

        assert result == 0


class TestEnsureCollectionCalledInIncrementalSync:
    """Verify ensu[RESEND_KEY_REDACTED] is called in all incremental sync paths."""

    @pytest.mark.asyncio
    async def test_sync_contacts_calls_ensu[RESEND_KEY_REDACTED](self):
        from app.tasks.vector_tasks import _sync_contacts_for_user

        mock_db = AsyncMock()

        with (
            patch(
                "app.tasks.vector_tasks.ensu[RESEND_KEY_REDACTED]",
                new_callable=AsyncMock,
            ) as mock_ensure,
            patch(
                "app.tasks.vector_tasks._load_contacts",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await _sync_contacts_for_user(uuid.uuid4(), db=mock_db)

        mock_ensure.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_listings_calls_ensu[RESEND_KEY_REDACTED](self):
        from app.tasks.vector_tasks import _sync_listings

        mock_db = AsyncMock()

        with (
            patch(
                "app.tasks.vector_tasks.ensu[RESEND_KEY_REDACTED]",
                new_callable=AsyncMock,
            ) as mock_ensure,
            patch(
                "app.tasks.vector_tasks._load_listings",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await _sync_listings(db=mock_db)

        mock_ensure.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_jobs_calls_ensu[RESEND_KEY_REDACTED](self):
        from app.tasks.vector_tasks import _sync_jobs

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.tasks.vector_tasks.ensu[RESEND_KEY_REDACTED]",
            new_callable=AsyncMock,
        ) as mock_ensure:
            await _sync_jobs(db=mock_db)

        mock_ensure.assert_called_once()


class TestVectorTasksUseDatabaseEngine:
    """Verify vector_tasks reuses database.py engine (not a local one)."""

    def test_imports_session_factory_from_database(self):
        """The _get_session_factory should come from app.database, not a local def."""
        import app.tasks.vector_tasks as vt
        import app.database as db_mod

        assert vt._get_session_factory is db_mod._get_session_factory
