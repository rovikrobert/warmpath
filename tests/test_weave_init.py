"""Tests for conditional Weave initialization."""

from unittest.mock import MagicMock, patch


class TestWeaveInit:
    """Verify Weave initializes only when mock mode off and API key present."""

    @patch.dict("os.environ", {"AI_MOCK_MODE": "true", "WANDB_API_KEY": "key123"})
    def test_init_weave_skips_in_mock_mode(self):
        from app.utils.weave_init import init_weave

        result = init_weave()

        assert result is False

    @patch.dict(
        "os.environ", {"AI_MOCK_MODE": "false", "WANDB_API_KEY": ""}, clear=False
    )
    def test_init_weave_skips_without_api_key(self):
        from app.utils.weave_init import init_weave

        result = init_weave()

        assert result is False

    @patch.dict(
        "os.environ",
        {
            "AI_MOCK_MODE": "false",
            "WANDB_API_KEY": "key123",
            "WANDB_PROJECT": "test-project",
        },
    )
    def test_init_weave_succeeds_with_key_and_real_mode(self):
        mock_weave = MagicMock()
        with patch.dict("sys.modules", {"weave": mock_weave}):
            from app.utils.weave_init import init_weave

            result = init_weave()

            assert result is True
            mock_weave.init.assert_called_once_with(project_name="test-project")

    @patch.dict(
        "os.environ",
        {"AI_MOCK_MODE": "false", "WANDB_API_KEY": "key123"},
    )
    def test_init_weave_returns_false_on_init_failure(self):
        mock_weave = MagicMock()
        mock_weave.init.side_effect = RuntimeError("connection refused")
        with patch.dict("sys.modules", {"weave": mock_weave}):
            from app.utils.weave_init import init_weave

            result = init_weave()

            assert result is False
