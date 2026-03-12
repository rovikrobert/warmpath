"""Test DB instrumentation middleware."""

from app.middleware.db_instrumentation import _request_db_stats, get_db_stats


def test_context_var_default_is_none():
    assert get_db_stats() is None


def test_context_var_set_and_get():
    token = _request_db_stats.set({"query_count": 5, "total_db_time_ms": 42.0})
    try:
        stats = get_db_stats()
        assert stats["query_count"] == 5
        assert stats["total_db_time_ms"] == 42.0
    finally:
        _request_db_stats.reset(token)
