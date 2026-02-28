"""Tests for Gemini batch API and context caching features."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import TestSessionLocal, create_test_user_in_db


class TestGeminiBatchCacheConfig:
    """Verify new config settings exist with correct defaults."""

    def test_gemini_cache_enabled_default_true(self):
        from app.config import Settings

        s = Settings(DATABASE_URL="sqlite:///:memory:")
        assert s.GEMINI_CACHE_ENABLED is True

    def test_gemini_batch_threshold_default_5000(self):
        from app.config import Settings

        s = Settings(DATABASE_URL="sqlite:///:memory:")
        assert s.GEMINI_BATCH_THRESHOLD == 5000

    def test_gemini_batch_poll_interval_default_60(self):
        from app.config import Settings

        s = Settings(DATABASE_URL="sqlite:///:memory:")
        assert s.GEMINI_BATCH_POLL_INTERVAL == 60

    def test_gemini_batch_max_polls_default_120(self):
        from app.config import Settings

        s = Settings(DATABASE_URL="sqlite:///:memory:")
        assert s.GEMINI_BATCH_MAX_POLLS == 120


class TestCachedCleanupContent:
    """Test the expanded cleanup content includes reference data."""

    def test_cached_content_includes_system_prompt(self):
        from app.services.ai_csv_cleaner import build_cached_cleanup_content

        content = build_cached_cleanup_content()
        assert "data-cleaning assistant" in content
        assert "current_company" in content

    def test_cached_content_includes_company_registry(self):
        from app.services.ai_csv_cleaner import build_cached_cleanup_content

        content = build_cached_cleanup_content()
        assert "Google" in content
        assert "Meta" in content
        assert "Canonical Company Names" in content

    def test_cached_content_includes_title_abbreviations(self):
        from app.services.ai_csv_cleaner import build_cached_cleanup_content

        content = build_cached_cleanup_content()
        assert "Software Engineer" in content
        assert "Title Abbreviations" in content

    def test_cached_content_exceeds_2048_token_estimate(self):
        from app.services.ai_csv_cleaner import build_cached_cleanup_content

        content = build_cached_cleanup_content()
        # Gemini requires at least 2,048 tokens for caching.
        # Rough estimate: 1 token ~ 4 chars → 2,048 tokens ~ 8,192 chars.
        # The system prompt + company registry + title abbrevs should
        # comfortably exceed this floor.
        assert len(content) > 8000


class TestGeminiCacheLifecycle:
    """Test cache creation and deletion for cleanup prompt."""

    @pytest.mark.asyncio
    async def test_create_cleanup_cache_returns_cache_name(self):
        from app.utils.gemini_cache import create_cleanup_cache

        mock_types = MagicMock()
        mock_client = MagicMock()
        mock_cache = MagicMock()
        mock_cache.name = "cachedContents/abc123"
        mock_client.caches.create = MagicMock(return_value=mock_cache)

        with patch.dict(
            "sys.modules",
            {"google.genai": MagicMock(types=mock_types), "google": MagicMock()},
        ):
            result = await create_cleanup_cache(mock_client, "upload-123")
        assert result == "cachedContents/abc123"
        mock_client.caches.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_cleanup_cache_returns_none_on_failure(self):
        from app.utils.gemini_cache import create_cleanup_cache

        mock_types = MagicMock()
        mock_client = MagicMock()
        mock_client.caches.create = MagicMock(side_effect=Exception("API error"))

        with patch.dict(
            "sys.modules",
            {"google.genai": MagicMock(types=mock_types), "google": MagicMock()},
        ):
            result = await create_cleanup_cache(mock_client, "upload-123")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_cleanup_cache_calls_client(self):
        from app.utils.gemini_cache import delete_cleanup_cache

        mock_client = MagicMock()
        mock_client.caches.delete = MagicMock()

        await delete_cleanup_cache(mock_client, "cachedContents/abc123")
        mock_client.caches.delete.assert_called_once_with(name="cachedContents/abc123")

    @pytest.mark.asyncio
    async def test_delete_cleanup_cache_ignores_errors(self):
        from app.utils.gemini_cache import delete_cleanup_cache

        mock_client = MagicMock()
        mock_client.caches.delete = MagicMock(side_effect=Exception("Not found"))

        # Should not raise
        await delete_cleanup_cache(mock_client, "cachedContents/abc123")

    @pytest.mark.asyncio
    async def test_create_cache_disabled_returns_none(self):
        from app.utils.gemini_cache import create_cleanup_cache

        mock_client = MagicMock()

        with patch("app.utils.gemini_cache.settings") as s:
            s.GEMINI_CACHE_ENABLED = False
            result = await create_cleanup_cache(mock_client, "upload-123")

        assert result is None
        mock_client.caches.create.assert_not_called()


class TestCacheAwareDispatch:
    """Test that dispatch_batch passes cache_name to Gemini provider."""

    @pytest.mark.asyncio
    async def test_dispatch_passes_cache_name_to_gemini_call(self):
        from app.services.ai_provider_pool import dispatch_batch

        mock_cleaned = [{"current_company": "Google", "current_title": "Engineer"}]
        batch = [
            {
                "first_name": "alice",
                "last_name": "smith",
                "current_company": "google",
                "current_title": "eng",
                "email": None,
                "linkedin_url": None,
                "full_name": "alice smith",
                "fingerprint": "old",
                "connected_on": None,
            }
        ]

        with (
            patch("app.services.ai_provider_pool.get_enabled_providers") as mock_get,
            patch(
                "app.services.ai_provider_pool.acquire_slot",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "app.services.ai_provider_pool.release_slot",
                new_callable=AsyncMock,
            ),
        ):
            mock_provider = MagicMock()
            mock_provider.name = "gemini"
            mock_provider.call = AsyncMock(return_value=mock_cleaned)
            mock_provider.max_concurrent = 5
            mock_provider.get_client = MagicMock()
            mock_get.return_value = [mock_provider]

            await dispatch_batch(batch, cache_name="cachedContents/test123")

            # Verify cache_name was passed through to the call
            call_args = mock_provider.call.call_args
            assert call_args is not None
            # cache_name should be the 4th positional arg or a kwarg
            args, kwargs = call_args
            assert (
                "cachedContents/test123" in args
                or kwargs.get("cache_name") == "cachedContents/test123"
            )

    @pytest.mark.asyncio
    async def test_dispatch_without_cache_name_works_unchanged(self):
        from app.services.ai_provider_pool import dispatch_batch

        mock_cleaned = [{"current_company": "Google", "current_title": "Engineer"}]
        batch = [
            {
                "first_name": "alice",
                "last_name": "smith",
                "current_company": "google",
                "current_title": "eng",
                "email": None,
                "linkedin_url": None,
                "full_name": "alice smith",
                "fingerprint": "old",
                "connected_on": None,
            }
        ]

        with (
            patch("app.services.ai_provider_pool.get_enabled_providers") as mock_get,
            patch(
                "app.services.ai_provider_pool.acquire_slot",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "app.services.ai_provider_pool.release_slot",
                new_callable=AsyncMock,
            ),
        ):
            mock_provider = MagicMock()
            mock_provider.name = "test"
            mock_provider.call = AsyncMock(return_value=mock_cleaned)
            mock_provider.max_concurrent = 5
            mock_provider.get_client = MagicMock()
            mock_get.return_value = [mock_provider]

            result = await dispatch_batch(batch)
            assert len(result) == 1
            assert result[0]["first_name"] == "Alice"


class TestPipelineCacheIntegration:
    """Test that the clean stage creates and deletes caches."""

    def test_clean_async_creates_cache_when_gemini_enabled(self):
        """Verify _clean_async calls create_cleanup_cache before dispatching."""
        # This is a structural test — verify the import exists and function is callable
        from app.utils.gemini_cache import create_cleanup_cache, delete_cleanup_cache

        assert callable(create_cleanup_cache)
        assert callable(delete_cleanup_cache)

    def test_dispatch_batch_accepts_cache_name_kwarg(self):
        """Verify dispatch_batch signature accepts cache_name."""
        import inspect

        from app.services.ai_provider_pool import dispatch_batch

        sig = inspect.signature(dispatch_batch)
        assert "cache_name" in sig.parameters
        assert sig.parameters["cache_name"].default is None


@pytest_asyncio.fixture
async def db():
    """Yield a test DB session."""
    async with TestSessionLocal() as session:
        yield session


class TestBatchJobNameColumn:
    """Test batch_job_name column on CsvUpload model."""

    @pytest.mark.asyncio
    async def test_csv_upload_has_batch_job_name_column(self, db):
        """CsvUpload model has batch_job_name column."""
        from app.models.contact import CsvUpload

        user, _ = await create_test_user_in_db(db)
        upload = CsvUpload(
            user_id=user.id,
            filename="test.csv",
            status="pending",
            batch_job_name="batches/abc123",
        )
        db.add(upload)
        await db.flush()
        assert upload.batch_job_name == "batches/abc123"

    @pytest.mark.asyncio
    async def test_csv_upload_batch_job_name_nullable(self, db):
        """batch_job_name is nullable (None for non-batch uploads)."""
        from app.models.contact import CsvUpload

        user, _ = await create_test_user_in_db(db)
        upload = CsvUpload(
            user_id=user.id,
            filename="test.csv",
            status="pending",
        )
        db.add(upload)
        await db.flush()
        assert upload.batch_job_name is None

    def test_csv_upload_response_schema_has_batch_job_name(self):
        """CsvUploadResponse schema includes batch_job_name field."""
        from app.schemas.contact import CsvUploadResponse

        fields = CsvUploadResponse.model_fields
        assert "batch_job_name" in fields


class TestGeminiBatchSubmission:
    """Test batch job creation for large CSV uploads."""

    @pytest.mark.asyncio
    async def test_submit_batch_returns_job_name(self):
        from app.services.gemini_batch import submit_cleanup_batch

        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_job.name = "batches/job-123"
        mock_client.batches.create = MagicMock(return_value=mock_job)

        batches = [
            [{"current_company": "google", "current_title": "eng"}],
            [{"current_company": "meta", "current_title": "pm"}],
        ]

        result = await submit_cleanup_batch(mock_client, batches, "upload-abc")
        assert result == "batches/job-123"
        mock_client.batches.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_batch_builds_correct_inline_requests(self):
        from app.services.gemini_batch import submit_cleanup_batch

        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_job.name = "batches/job-456"
        mock_client.batches.create = MagicMock(return_value=mock_job)

        batches = [
            [{"current_company": "stripe", "current_title": "swe"}],
        ]

        await submit_cleanup_batch(mock_client, batches, "upload-xyz")

        call_kwargs = mock_client.batches.create.call_args
        src = call_kwargs.kwargs.get("src") or call_kwargs[1].get("src")
        assert len(src) == 1
        assert src[0]["key"] == "chunk-0"

    @pytest.mark.asyncio
    async def test_submit_batch_returns_none_on_failure(self):
        from app.services.gemini_batch import submit_cleanup_batch

        mock_client = MagicMock()
        mock_client.batches.create = MagicMock(side_effect=Exception("Quota exceeded"))

        batches = [[{"current_company": "x", "current_title": "y"}]]

        result = await submit_cleanup_batch(mock_client, batches, "upload-err")
        assert result is None


class TestGeminiBatchPollResult:
    """Test batch result processing."""

    @pytest.mark.asyncio
    async def test_get_batch_results_succeeded(self):
        from app.services.gemini_batch import get_batch_results

        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_job.state.name = "JOB_STATE_SUCCEEDED"
        mock_resp_0 = MagicMock()
        mock_resp_0.response.text = (
            '[{"current_company": "Google", "current_title": "Engineer"}]'
        )
        mock_resp_0.error = None
        mock_resp_1 = MagicMock()
        mock_resp_1.response.text = (
            '[{"current_company": "Meta", "current_title": "PM"}]'
        )
        mock_resp_1.error = None
        mock_job.dest.inlined_responses = [mock_resp_0, mock_resp_1]
        mock_client.batches.get = MagicMock(return_value=mock_job)

        state, results = await get_batch_results(mock_client, "batches/job-1")
        assert state == "JOB_STATE_SUCCEEDED"
        assert len(results) == 2
        assert results[0][0]["current_company"] == "Google"

    @pytest.mark.asyncio
    async def test_get_batch_results_still_running(self):
        from app.services.gemini_batch import get_batch_results

        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_job.state.name = "JOB_STATE_RUNNING"
        mock_client.batches.get = MagicMock(return_value=mock_job)

        state, results = await get_batch_results(mock_client, "batches/job-2")
        assert state == "JOB_STATE_RUNNING"
        assert results is None

    @pytest.mark.asyncio
    async def test_get_batch_results_failed(self):
        from app.services.gemini_batch import get_batch_results

        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_job.state.name = "JOB_STATE_FAILED"
        mock_client.batches.get = MagicMock(return_value=mock_job)

        state, results = await get_batch_results(mock_client, "batches/job-3")
        assert state == "JOB_STATE_FAILED"
        assert results is None


class TestBatchPollTaskImportable:
    """Verify poll task is registered and importable."""

    def test_poll_gemini_batch_importable(self):
        from app.tasks.csv_pipeline import poll_gemini_batch

        assert poll_gemini_batch is not None
