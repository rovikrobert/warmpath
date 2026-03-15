"""Test agent auto-repair feed item generation."""

from unittest.mock import patch, MagicMock


def test_create_repair_feed_item_queues_celery_task():
    """Feed item creation should dispatch a Celery task."""
    mock_task = MagicMock()
    with patch("app.tasks.feed_tasks.create_feed_item_task", mock_task, create=True):
        import importlib
        import app.services.agent_feed as agent_feed_mod

        importlib.reload(agent_feed_mod)
        result = agent_feed_mod.create_repair_feed_item(
            admin_user_id="user-123",
            fixed_count=2,
            pr_url="https://github.com/org/repo/pull/50",
            finding_titles=["Lint issue A", "Format issue B"],
        )
        assert result == {"status": "queued"}
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args[1]
        assert call_kwargs["item_type"] == "agent_auto_repair"
        assert call_kwargs["priority"] == 30


def test_create_repair_feed_item_handles_exception():
    """Should return None gracefully when the Celery task raises."""
    mock_task = MagicMock()
    mock_task.delay.side_effect = RuntimeError("celery unavailable")
    with patch("app.tasks.feed_tasks.create_feed_item_task", mock_task, create=True):
        import importlib
        import app.services.agent_feed as agent_feed_mod

        importlib.reload(agent_feed_mod)
        result = agent_feed_mod.create_repair_feed_item(
            admin_user_id="user-123",
            fixed_count=1,
        )
        assert result is None


def test_create_repair_feed_item_truncates_long_title_list():
    """Should truncate finding titles to first 3 + count."""
    mock_task = MagicMock()
    with patch("app.tasks.feed_tasks.create_feed_item_task", mock_task, create=True):
        import importlib
        import app.services.agent_feed as agent_feed_mod

        importlib.reload(agent_feed_mod)
        result = agent_feed_mod.create_repair_feed_item(
            admin_user_id="user-123",
            fixed_count=5,
            finding_titles=["A", "B", "C", "D", "E"],
        )
        assert result == {"status": "queued"}
        call_kwargs = mock_task.delay.call_args[1]
        assert "(+2 more)" in call_kwargs["body"]
