"""Tests for AgentMemory sync bridge — agents/shared/memory_bridge.py.

All tests mock the MemoryService so no real DB is needed.
"""

from __futu[RESEND_KEY_REDACTED] import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.shared.memory_bridge import AgentMemory

pytestmark = pytest.mark.timeout(10)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def agent_memory() -> AgentMemory:
    return AgentMemory(team="agents", agent="architect")


def _fake_session_factory() -> MagicMock:
    """Return a mock async session factory whose __call__ returns an async ctx manager."""
    session = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock()
    factory.return_value = ctx
    return factory


# ---------------------------------------------------------------------------
# remember()
# ---------------------------------------------------------------------------


class TestRemember:
    @patch("agents.shared.memory_bridge.AgentMemory._is_enabled", return_value=True)
    @patch("app.services.memory_service.MemoryService")
    @patch("app.database._get_session_factory")
    def test_remember_calls_service(
        self,
        mock_factory: MagicMock,
        mock_svc_cls: MagicMock,
        mock_enabled: MagicMock,
        agent_memory: AgentMemory,
    ) -> None:
        """remember() delegates to MemoryService.remember with correct params."""
        # Wire up the factory mock
        factory = _fake_session_factory()
        mock_factory.return_value = factory

        mock_instance = MagicMock()
        mock_instance.remember = AsyncMock(return_value=uuid.uuid4())
        mock_svc_cls.return_value = mock_instance

        agent_memory.remember(
            "Found 3 circular imports",
            summary="circular imports detected",
            tags=["app/services/foo.py"],
            metadata={"count": 3},
            importance=0.8,
            ttl_hours=72,
        )

        mock_instance.remember.assert_awaited_once_with(
            "Found 3 circular imports",
            source_type="agent_scan",
            source_id="architect",
            summary="circular imports detected",
            team="agents",
            tags=["app/services/foo.py"],
            metadata={"count": 3},
            importance=0.8,
            ttl_hours=72,
        )

    @patch("agents.shared.memory_bridge.AgentMemory._is_enabled", return_value=True)
    @patch("app.database._get_session_factory")
    def test_remember_falls_back_on_error(
        self,
        mock_factory: MagicMock,
        mock_enabled: MagicMock,
        agent_memory: AgentMemory,
    ) -> None:
        """DB unavailable => no exception raised, returns None."""
        mock_factory.side_effect = RuntimeError("DB is down")

        # Should NOT raise
        result = agent_memory.remember("some content")
        assert result is None


# ---------------------------------------------------------------------------
# recall()
# ---------------------------------------------------------------------------


class TestRecall:
    @patch("agents.shared.memory_bridge.AgentMemory._is_enabled", return_value=True)
    @patch("app.services.memory_service.MemoryService")
    @patch("app.database._get_session_factory")
    def test_recall_returns_results(
        self,
        mock_factory: MagicMock,
        mock_svc_cls: MagicMock,
        mock_enabled: MagicMock,
        agent_memory: AgentMemory,
    ) -> None:
        """recall() returns what MemoryService.recall returns."""
        factory = _fake_session_factory()
        mock_factory.return_value = factory

        expected = [
            {"id": str(uuid.uuid4()), "content": "circular imports", "score": 0.9},
            {"id": str(uuid.uuid4()), "content": "import cycle", "score": 0.7},
        ]
        mock_instance = MagicMock()
        mock_instance.recall = AsyncMock(return_value=expected)
        mock_svc_cls.return_value = mock_instance

        results = agent_memory.recall("circular imports", top_k=3)

        assert results == expected
        mock_instance.recall.assert_awaited_once_with(
            "circular imports",
            top_k=3,
            team="agents",
            source_type="agent_scan",
        )

    @patch("agents.shared.memory_bridge.AgentMemory._is_enabled", return_value=True)
    @patch("app.database._get_session_factory")
    def test_recall_returns_empty_on_error(
        self,
        mock_factory: MagicMock,
        mock_enabled: MagicMock,
        agent_memory: AgentMemory,
    ) -> None:
        """Error => empty list, no exception."""
        mock_factory.side_effect = RuntimeError("DB is down")

        results = agent_memory.recall("anything")
        assert results == []

    @patch("agents.shared.memory_bridge.AgentMemory._is_enabled", return_value=True)
    @patch("app.services.memory_service.MemoryService")
    @patch("app.database._get_session_factory")
    def test_recall_uses_custom_team(
        self,
        mock_factory: MagicMock,
        mock_svc_cls: MagicMock,
        mock_enabled: MagicMock,
        agent_memory: AgentMemory,
    ) -> None:
        """recall(team=...) passes a different team filter."""
        factory = _fake_session_factory()
        mock_factory.return_value = factory

        mock_instance = MagicMock()
        mock_instance.recall = AsyncMock(return_value=[])
        mock_svc_cls.return_value = mock_instance

        agent_memory.recall("test query", team="data_team")

        mock_instance.recall.assert_awaited_once_with(
            "test query",
            top_k=5,
            team="data_team",
            source_type="agent_scan",
        )


# ---------------------------------------------------------------------------
# recall_about_file()
# ---------------------------------------------------------------------------


class TestRecallAboutFile:
    @patch("agents.shared.memory_bridge.AgentMemory._is_enabled", return_value=True)
    @patch("app.services.memory_service.MemoryService")
    @patch("app.database._get_session_factory")
    def test_recall_about_file_returns_results(
        self,
        mock_factory: MagicMock,
        mock_svc_cls: MagicMock,
        mock_enabled: MagicMock,
        agent_memory: AgentMemory,
    ) -> None:
        """recall_about_file() delegates to MemoryService.recall_about_file."""
        factory = _fake_session_factory()
        mock_factory.return_value = factory

        expected = [{"id": str(uuid.uuid4()), "content": "issues in foo.py"}]
        mock_instance = MagicMock()
        mock_instance.recall_about_file = AsyncMock(return_value=expected)
        mock_svc_cls.return_value = mock_instance

        results = agent_memory.recall_about_file("app/services/foo.py", top_k=3)

        assert results == expected
        mock_instance.recall_about_file.assert_awaited_once_with(
            "app/services/foo.py", top_k=3
        )

    @patch("agents.shared.memory_bridge.AgentMemory._is_enabled", return_value=True)
    @patch("app.database._get_session_factory")
    def test_recall_about_file_returns_empty_on_error(
        self,
        mock_factory: MagicMock,
        mock_enabled: MagicMock,
        agent_memory: AgentMemory,
    ) -> None:
        """Error => empty list, no exception."""
        mock_factory.side_effect = RuntimeError("DB is down")

        results = agent_memory.recall_about_file("any/file.py")
        assert results == []


# ---------------------------------------------------------------------------
# Feature flag gating
# ---------------------------------------------------------------------------


class TestFeatureFlagGating:
    """AgentMemory methods return early when MEMORY_SERVICE_ENABLED=False."""

    @patch("app.config.settings")
    def test_remember_noop_when_disabled(
        self, mock_settings: MagicMock, agent_memory: AgentMemory
    ) -> None:
        mock_settings.MEMORY_SERVICE_ENABLED = False

        # Should not raise or attempt DB access
        result = agent_memory.remember("ignored content")
        assert result is None

    @patch("app.config.settings")
    def test_recall_returns_empty_when_disabled(
        self, mock_settings: MagicMock, agent_memory: AgentMemory
    ) -> None:
        mock_settings.MEMORY_SERVICE_ENABLED = False

        results = agent_memory.recall("any query")
        assert results == []

    @patch("app.config.settings")
    def test_recall_about_file_returns_empty_when_disabled(
        self, mock_settings: MagicMock, agent_memory: AgentMemory
    ) -> None:
        mock_settings.MEMORY_SERVICE_ENABLED = False

        results = agent_memory.recall_about_file("any/file.py")
        assert results == []
