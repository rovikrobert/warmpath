"""Tests for Gemini batch API and context caching features."""

import pytest
from unittest.mock import MagicMock, patch


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
