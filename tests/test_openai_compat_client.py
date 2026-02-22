"""Tests for OpenAI-compatible client factory."""

from unittest.mock import patch


class TestOpenAICompatClients:
    """Verify lazy singleton behavior for all OpenAI-compatible providers."""

    def test_get_openai_client_returns_async_client(self):
        with patch("app.utils.openai_compat_client.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "test-key"
            from app.utils.openai_compat_client import _build_openai_client

            client = _build_openai_client()
            assert client.api_key == "test-key"
            assert "api.openai.com" in str(client.base_url)

    def test_get_groq_client_uses_groq_base_url(self):
        with patch("app.utils.openai_compat_client.settings") as mock_settings:
            mock_settings.GROQ_API_KEY = "test-groq-key"
            from app.utils.openai_compat_client import _build_groq_client

            client = _build_groq_client()
            assert client.api_key == "test-groq-key"
            assert "groq.com" in str(client.base_url)
