"""Tests for MCP memory tools — search_memory, save_memory, index_session."""

from __futu[RESEND_KEY_REDACTED] import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server.tools.memory import index_session, save_memory, search_memory

pytestmark = pytest.mark.timeout(10)


def _enabled():
    """Patch helper: always return None (enabled)."""
    return None


class TestMcpSearchMemory:
    @patch("mcp_server.tools.memory._check_enabled", return_value=None)
    @patch("mcp_server.tools.memory._get_session", new_callable=AsyncMock)
    @patch("app.services.memory_service.MemoryService", autospec=False)
    @pytest.mark.asyncio
    async def test_search_memory_returns_results(
        self, MockSvc: MagicMock, mock_session: AsyncMock, mock_check: MagicMock
    ) -> None:
        fake_results = [
            {
                "id": str(uuid.uuid4()),
                "content": "Deploy fix for CSV parser",
                "score": 0.85,
            },
            {
                "id": str(uuid.uuid4()),
                "content": "Redis pool tuning notes",
                "score": 0.72,
            },
        ]
        session = AsyncMock()
        mock_session.return_value = session
        instance = MockSvc.return_value
        instance.recall = AsyncMock(return_value=fake_results)

        result = await search_memory(query="CSV parser fix")
        assert result["count"] == 2
        assert len(result["results"]) == 2
        assert result["results"][0]["score"] == 0.85

    @patch("mcp_server.tools.memory._check_enabled", return_value=None)
    @patch("mcp_server.tools.memory._get_session", new_callable=AsyncMock)
    @patch("app.services.memory_service.MemoryService", autospec=False)
    @pytest.mark.asyncio
    async def test_search_memory_returns_empty_when_no_matches(
        self, MockSvc: MagicMock, mock_session: AsyncMock, mock_check: MagicMock
    ) -> None:
        session = AsyncMock()
        mock_session.return_value = session
        instance = MockSvc.return_value
        instance.recall = AsyncMock(return_value=[])

        result = await search_memory(query="nonexistent topic xyz")
        assert result["count"] == 0
        assert result["results"] == []

    @patch("mcp_server.tools.memory._check_enabled", return_value=None)
    @patch("mcp_server.tools.memory._get_session", new_callable=AsyncMock)
    @patch("app.services.memory_service.MemoryService", autospec=False)
    @pytest.mark.asyncio
    async def test_search_memory_returns_error_dict_on_failure(
        self, MockSvc: MagicMock, mock_session: AsyncMock, mock_check: MagicMock
    ) -> None:
        session = AsyncMock()
        mock_session.return_value = session
        instance = MockSvc.return_value
        instance.recall = AsyncMock(side_effect=RuntimeError("DB connection lost"))

        result = await search_memory(query="anything")
        assert "error" in result
        assert "Search failed" in result["error"]

    @patch("mcp_server.tools.memory._check_enabled", return_value=None)
    @patch("mcp_server.tools.memory._get_session", new_callable=AsyncMock)
    @patch("app.services.memory_service.MemoryService", autospec=False)
    @pytest.mark.asyncio
    async def test_search_memory_passes_team_filter(
        self, MockSvc: MagicMock, mock_session: AsyncMock, mock_check: MagicMock
    ) -> None:
        session = AsyncMock()
        mock_session.return_value = session
        instance = MockSvc.return_value
        instance.recall = AsyncMock(return_value=[{"id": "x"}])

        result = await search_memory(query="deploy", team="agents")
        assert result["count"] == 1
        instance.recall.assert_awaited_once()


class TestMcpSaveMemory:
    @patch("mcp_server.tools.memory._check_enabled", return_value=None)
    @patch("mcp_server.tools.memory._get_session", new_callable=AsyncMock)
    @patch("app.services.memory_service.MemoryService", autospec=False)
    @pytest.mark.asyncio
    async def test_save_memory_stores_successfully(
        self, MockSvc: MagicMock, mock_session: AsyncMock, mock_check: MagicMock
    ) -> None:
        fake_id = uuid.uuid4()
        session = AsyncMock()
        mock_session.return_value = session
        instance = MockSvc.return_value
        instance.remember = AsyncMock(return_value=fake_id)

        result = await save_memory(
            content="Alembic migration requires single head",
            summary="Alembic heads check",
            team="agents",
            tags=["alembic", "migration"],
            importance=0.8,
        )
        assert result["status"] == "saved"
        assert result["id"] == str(fake_id)

    @patch("mcp_server.tools.memory._check_enabled", return_value=None)
    @patch("mcp_server.tools.memory._get_session", new_callable=AsyncMock)
    @patch("app.services.memory_service.MemoryService", autospec=False)
    @pytest.mark.asyncio
    async def test_save_memory_returns_error_dict_on_failure(
        self, MockSvc: MagicMock, mock_session: AsyncMock, mock_check: MagicMock
    ) -> None:
        session = AsyncMock()
        mock_session.return_value = session
        instance = MockSvc.return_value
        instance.remember = AsyncMock(side_effect=RuntimeError("DB write failed"))

        result = await save_memory(content="test content")
        assert "error" in result
        assert "Save failed" in result["error"]

    @patch("mcp_server.tools.memory._check_enabled", return_value=None)
    @patch("mcp_server.tools.memory._get_session", new_callable=AsyncMock)
    @patch("app.services.memory_service.MemoryService", autospec=False)
    @pytest.mark.asyncio
    async def test_save_memory_with_ttl(
        self, MockSvc: MagicMock, mock_session: AsyncMock, mock_check: MagicMock
    ) -> None:
        fake_id = uuid.uuid4()
        session = AsyncMock()
        mock_session.return_value = session
        instance = MockSvc.return_value
        instance.remember = AsyncMock(return_value=fake_id)

        result = await save_memory(content="Temporary note", ttl_hours=24)
        assert result["status"] == "saved"


class TestMcpIndexSession:
    @patch("mcp_server.tools.memory._check_enabled", return_value=None)
    @patch("mcp_server.tools.memory._get_session", new_callable=AsyncMock)
    @patch("app.services.memory_service.MemoryService", autospec=False)
    @pytest.mark.asyncio
    async def test_index_session_stores_summary_and_learnings(
        self, MockSvc: MagicMock, mock_session: AsyncMock, mock_check: MagicMock
    ) -> None:
        session = AsyncMock()
        mock_session.return_value = session
        instance = MockSvc.return_value
        instance.remember = AsyncMock(return_value=uuid.uuid4())

        result = await index_session(
            session_summary="Fixed CSV parser encoding bug",
            key_learnings=[
                "UTF-8 BOM must be stripped before parsing",
                "Formula injection sanitization runs before encoding fix",
            ],
        )
        assert result["status"] == "indexed"
        assert result["memories_created"] == 3

    @patch("mcp_server.tools.memory._check_enabled", return_value=None)
    @patch("mcp_server.tools.memory._get_session", new_callable=AsyncMock)
    @patch("app.services.memory_service.MemoryService", autospec=False)
    @pytest.mark.asyncio
    async def test_index_session_summary_only(
        self, MockSvc: MagicMock, mock_session: AsyncMock, mock_check: MagicMock
    ) -> None:
        session = AsyncMock()
        mock_session.return_value = session
        instance = MockSvc.return_value
        instance.remember = AsyncMock(return_value=uuid.uuid4())

        result = await index_session(session_summary="Reviewed marketplace indexer")
        assert result["status"] == "indexed"
        assert result["memories_created"] == 1

    @patch("mcp_server.tools.memory._check_enabled", return_value=None)
    @patch("mcp_server.tools.memory._get_session", new_callable=AsyncMock)
    @patch("app.services.memory_service.MemoryService", autospec=False)
    @pytest.mark.asyncio
    async def test_index_session_returns_error_dict_on_failure(
        self, MockSvc: MagicMock, mock_session: AsyncMock, mock_check: MagicMock
    ) -> None:
        session = AsyncMock()
        mock_session.return_value = session
        instance = MockSvc.return_value
        instance.remember = AsyncMock(
            side_effect=RuntimeError("Session factory unavailable")
        )

        result = await index_session(session_summary="test")
        assert "error" in result
        assert "Index failed" in result["error"]


class TestMcpFeatureFlagGating:
    """MCP tools return error when MEMORY_SERVICE_ENABLED=False."""

    @patch("mcp_server.tools.memory._check_enabled", return_value={"error": "disabled"})
    @pytest.mark.asyncio
    async def test_search_memory_gated_when_disabled(
        self, mock_check: MagicMock
    ) -> None:
        result = await search_memory(query="test")
        assert "error" in result
        assert "disabled" in result["error"]

    @patch("mcp_server.tools.memory._check_enabled", return_value={"error": "disabled"})
    @pytest.mark.asyncio
    async def test_save_memory_gated_when_disabled(self, mock_check: MagicMock) -> None:
        result = await save_memory(content="test")
        assert "error" in result

    @patch("mcp_server.tools.memory._check_enabled", return_value={"error": "disabled"})
    @pytest.mark.asyncio
    async def test_index_session_gated_when_disabled(
        self, mock_check: MagicMock
    ) -> None:
        result = await index_session(session_summary="test")
        assert "error" in result


class TestMcpInputValidation:
    """MCP tools validate inputs before hitting the DB."""

    @patch("mcp_server.tools.memory._check_enabled", return_value=None)
    @pytest.mark.asyncio
    async def test_search_empty_query_returns_empty(
        self, mock_check: MagicMock
    ) -> None:
        result = await search_memory(query="")
        assert result["count"] == 0
        assert result["results"] == []

    @patch("mcp_server.tools.memory._check_enabled", return_value=None)
    @pytest.mark.asyncio
    async def test_save_empty_content_returns_error(
        self, mock_check: MagicMock
    ) -> None:
        result = await save_memory(content="")
        assert "error" in result
        assert "empty" in result["error"].lower()

    @patch("mcp_server.tools.memory._check_enabled", return_value=None)
    @pytest.mark.asyncio
    async def test_index_empty_summary_returns_error(
        self, mock_check: MagicMock
    ) -> None:
        result = await index_session(session_summary="")
        assert "error" in result
        assert "empty" in result["error"].lower()


class TestMcpMemoryIntegration:
    """Tests that verify the async plumbing between MCP tools and MemoryService."""

    @patch("mcp_server.tools.memory._check_enabled", return_value=None)
    @patch("mcp_server.tools.memory._get_session", new_callable=AsyncMock)
    @patch("app.services.memory_service.MemoryService", autospec=False)
    @pytest.mark.asyncio
    async def test_search_memory_calls_recall(
        self,
        MockSvc: MagicMock,
        mock_get_session: AsyncMock,
        mock_check: MagicMock,
    ) -> None:
        """Verify search_memory creates a session and calls svc.recall()."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        fake_results = [{"id": str(uuid.uuid4()), "content": "test", "score": 0.9}]
        instance = MockSvc.return_value
        instance.recall = AsyncMock(return_value=fake_results)

        result = await search_memory(query="test query")

        assert result["count"] == 1
        assert result["results"] == fake_results
        mock_session.close.assert_awaited_once()

    @patch("mcp_server.tools.memory._check_enabled", return_value=None)
    @patch("mcp_server.tools.memory._get_session", new_callable=AsyncMock)
    @patch("app.services.memory_service.MemoryService", autospec=False)
    @pytest.mark.asyncio
    async def test_save_memory_calls_remember(
        self,
        MockSvc: MagicMock,
        mock_get_session: AsyncMock,
        mock_check: MagicMock,
    ) -> None:
        """Verify save_memory creates a session and calls svc.remember()."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session
        fake_id = uuid.uuid4()

        instance = MockSvc.return_value
        instance.remember = AsyncMock(return_value=fake_id)

        result = await save_memory(content="important insight")

        assert result["status"] == "saved"
        assert result["id"] == str(fake_id)
        instance.remember.assert_awaited_once()
        mock_session.close.assert_awaited_once()

    @patch("mcp_server.tools.memory._check_enabled", return_value=None)
    @patch("mcp_server.tools.memory._get_session", new_callable=AsyncMock)
    @patch("app.services.memory_service.MemoryService", autospec=False)
    @pytest.mark.asyncio
    async def test_index_session_creates_multiple_memories(
        self,
        MockSvc: MagicMock,
        mock_get_session: AsyncMock,
        mock_check: MagicMock,
    ) -> None:
        """Verify index_session calls remember once per learning + once for summary."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        instance = MockSvc.return_value
        instance.remember = AsyncMock(return_value=uuid.uuid4())

        result = await index_session(
            session_summary="Session summary",
            key_learnings=["learning 1", "learning 2"],
        )

        assert result["status"] == "indexed"
        assert result["memories_created"] == 3
        # 1 summary + 2 learnings = 3 calls to remember
        assert instance.remember.await_count == 3
        mock_session.close.assert_awaited_once()
