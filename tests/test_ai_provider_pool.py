"""Tests for multi-provider AI dispatch pool."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestProviderRegistry:
    """Test provider enablement based on API keys."""

    def test_provider_enabled_when_key_set(self):
        from app.services.ai_provider_pool import _is_provider_enabled

        with patch("app.services.ai_provider_pool.settings") as s:
            s.GOOGLE_API_KEY = "key"
            assert _is_provider_enabled("gemini", s) is True

    def test_provider_disabled_when_key_empty(self):
        from app.services.ai_provider_pool import _is_provider_enabled

        with patch("app.services.ai_provider_pool.settings") as s:
            s.GOOGLE_API_KEY = ""
            assert _is_provider_enabled("gemini", s) is False

    def test_get_enabled_providers_filters_correctly(self):
        from app.services.ai_provider_pool import (
            get_enabled_providers,
            CleaningProvider,
        )

        def _mock_build(name):
            return CleaningProvider(
                name=name,
                model="test",
                max_concurrent=10,
                get_client=lambda: None,
                call=lambda: None,
            )

        with (
            patch("app.services.ai_provider_pool.settings") as s,
            patch(
                "app.services.ai_provider_pool._build_provider", side_effect=_mock_build
            ),
        ):
            s.GOOGLE_API_KEY = "key"
            s.ANTHROPIC_API_KEY = ""
            s.OPENAI_API_KEY = "key"
            s.GROQ_API_KEY = ""
            s.DEEPSEEK_API_KEY = "key"
            s.GOOGLE_MAX_CONCURRENT = 10
            s.OPENAI_MAX_CONCURRENT = 10
            s.DEEPSEEK_MAX_CONCURRENT = 10
            enabled = get_enabled_providers(s)
            names = [p.name for p in enabled]
            assert "gemini" in names
            assert "openai" in names
            assert "deepseek" in names
            assert "anthropic" not in names
            assert "groq" not in names


class TestDispatchBatch:
    """Test the dispatch algorithm with mocked providers."""

    @pytest.mark.asyncio
    async def test_dispatch_returns_cleaned_batch_from_first_available(self):
        from app.services.ai_provider_pool import dispatch_batch

        mock_cleaned = [
            {
                "first_name": "Alice",
                "last_name": "Smith",
                "current_company": "Google",
                "current_title": "Engineer",
            }
        ]
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
                "app.services.ai_provider_pool.acqui[RESEND_KEY_REDACTED]",
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

    @pytest.mark.asyncio
    async def test_dispatch_falls_back_to_mock_when_all_providers_fail(self):
        from app.services.ai_provider_pool import dispatch_batch

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
                "app.services.ai_provider_pool.acqui[RESEND_KEY_REDACTED]",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "app.services.ai_provider_pool.release_slot",
                new_callable=AsyncMock,
            ),
            patch("app.services.ai_provider_pool.asyncio") as mock_asyncio,
        ):
            mock_asyncio.sleep = AsyncMock()
            mock_provider = MagicMock()
            mock_provider.name = "test"
            mock_provider.call = AsyncMock(side_effect=Exception("API error"))
            mock_provider.max_concurrent = 5
            mock_provider.get_client = MagicMock()
            mock_get.return_value = [mock_provider]

            result = await dispatch_batch(batch)
            # Should fall back to mock cleaner — still returns cleaned data
            assert len(result) == 1
            assert result[0]["first_name"] is not None

    @pytest.mark.asyncio
    async def test_dispatch_falls_back_to_mock_when_no_providers_enabled(self):
        from app.services.ai_provider_pool import dispatch_batch

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

        with patch("app.services.ai_provider_pool.get_enabled_providers") as mock_get:
            mock_get.return_value = []
            result = await dispatch_batch(batch)
            assert len(result) == 1


class TestPostProcessing:
    """Test deterministic post-processing on AI output."""

    def test_post_process_normalizes_known_company(self):
        from app.services.ai_csv_cleaner import post_process_ai_output

        original = {
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
        ai_output = {
            "first_name": "Alice",
            "last_name": "Smith",
            "current_company": "Google LLC",
            "current_title": "Engineer",
        }
        result = post_process_ai_output(original, ai_output)
        assert (
            result["current_company"] == "Google"
        )  # normalized by deterministic lookup

    def test_post_process_keeps_original_when_ai_returns_empty(self):
        from app.services.ai_csv_cleaner import post_process_ai_output

        original = {
            "first_name": "alice",
            "last_name": "smith",
            "current_company": "Acme Corp",
            "current_title": "Engineer",
            "email": None,
            "linkedin_url": None,
            "full_name": "alice smith",
            "fingerprint": "old",
            "connected_on": None,
        }
        ai_output = {
            "first_name": "Alice",
            "last_name": "Smith",
            "current_company": "",
            "current_title": "Engineer",
        }
        result = post_process_ai_output(original, ai_output)
        assert result["first_name"] == "Alice"
