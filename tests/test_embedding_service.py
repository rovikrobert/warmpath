"""Tests for embedding_service — OpenAI text-embedding-3-small wrapper."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestBuildEmbeddingText:
    """Unit tests for text construction per doc type."""

    def test_contact_text(self):
        from app.services.embedding_service import build_contact_text

        text = build_contact_text(
            title="Senior Engineer",
            company="Stripe",
            location="Singapore",
            relationship_type="former_colleague",
            tags=["python", "fintech"],
        )
        assert "Senior Engineer" in text
        assert "Stripe" in text
        assert "Singapore" in text
        assert "former colleague" in text
        assert "python" in text

    def test_contact_text_missing_fields(self):
        from app.services.embedding_service import build_contact_text

        text = build_contact_text(title=None, company=None)
        assert isinstance(text, str)
        assert len(text) > 0  # should not be empty even with all None

    def test_contact_text_all_none_returns_unknown(self):
        from app.services.embedding_service import build_contact_text

        text = build_contact_text(
            title=None,
            company=None,
            location=None,
            relationship_type=None,
            tags=None,
        )
        assert text == "unknown contact"

    def test_contact_text_has_no_pii(self):
        """Verify embedding text never contains names or emails."""
        from app.services.embedding_service import build_contact_text

        text = build_contact_text(
            title="CTO",
            company="Acme Inc",
            location="NYC",
            relationship_type="manager",
            tags=["leadership"],
        )
        # Function signature doesn't accept name/email — privacy by design
        assert "name" not in text.lower() or "company name" in text.lower()
        assert "@" not in text

    def test_listing_text(self):
        from app.services.embedding_service import build_listing_text

        text = build_listing_text(
            role_level="senior",
            department_category="engineering",
            company_name="Stripe",
        )
        assert "senior" in text
        assert "engineering" in text
        assert "Stripe" in text

    def test_job_text(self):
        from app.services.embedding_service import build_job_text

        text = build_job_text(
            job_title="Backend Engineer",
            company_name="Grab",
            location="Singapore",
        )
        assert "Backend Engineer" in text
        assert "Grab" in text
        assert "Singapore" in text


class TestGenerateEmbeddings:
    """Tests for OpenAI embedding API calls (mocked)."""

    @pytest.mark.asyncio
    async def test_embed_single_text(self):
        from app.services.embedding_service import generate_embeddings

        mock_response = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.embedding = [0.1] * 1536
        mock_response.data = [mock_embedding]

        with patch("app.services.embedding_service._get_openai_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_client

            result = await generate_embeddings(["hello world"])

        assert len(result) == 1
        assert len(result[0]) == 1536

    @pytest.mark.asyncio
    async def test_embed_batch(self):
        from app.services.embedding_service import generate_embeddings

        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(embedding=[0.1] * 1536),
            MagicMock(embedding=[0.2] * 1536),
            MagicMock(embedding=[0.3] * 1536),
        ]

        with patch("app.services.embedding_service._get_openai_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_client

            result = await generate_embeddings(["a", "b", "c"])

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_embed_empty_list(self):
        from app.services.embedding_service import generate_embeddings

        result = await generate_embeddings([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_handles_api_error(self):
        from app.services.embedding_service import generate_embeddings

        with patch("app.services.embedding_service._get_openai_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.embeddings.create = AsyncMock(
                side_effect=Exception("API error")
            )
            mock_get.return_value = mock_client

            result = await generate_embeddings(["hello"])

        assert result == []  # graceful fallback
