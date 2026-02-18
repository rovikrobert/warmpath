"""Tests for ops team live data checks (7 CoS audit gaps)."""
from __future__ import annotations

import pytest


class TestOpsSharedDb:
    """ops_team.shared.db — graceful sync session factory."""

    def test_get_session_returns_none_without_database_url(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        import importlib
        import ops_team.shared.db as db_mod
        importlib.reload(db_mod)
        assert db_mod.get_session() is None

    def test_get_session_returns_session_with_database_url(self, monkeypatch):
        """When DATABASE_URL is set and _get_sync_engine works, return a session."""
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test_ops.db")

        from unittest.mock import patch
        from sqlalchemy import create_engine

        test_engine = create_engine("sqlite:///test_ops.db")

        import importlib
        import ops_team.shared.db as db_mod
        importlib.reload(db_mod)

        with patch("app.database._get_sync_engine", return_value=test_engine):
            session = db_mod.get_session()
            assert session is not None
            session.close()

        test_engine.dispose()
        import os
        if os.path.exists("test_ops.db"):
            os.remove("test_ops.db")

    def test_get_session_returns_none_on_engine_failure(self, monkeypatch):
        """If _get_sync_engine raises, get_session returns None gracefully."""
        monkeypatch.setenv("DATABASE_URL", "[DATABASE_URL_REDACTED]")

        from unittest.mock import patch

        import importlib
        import ops_team.shared.db as db_mod
        importlib.reload(db_mod)

        with patch(
            "app.database._get_sync_engine",
            side_effect=Exception("connection refused"),
        ):
            assert db_mod.get_session() is None
