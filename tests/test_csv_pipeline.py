"""Tests for V2 CSV streaming pipeline routing."""

import pytest
from unittest.mock import patch, MagicMock


class TestV2PipelineRouting:
    """Test that CSV_PIPELINE_V2 flag routes to the new pipeline."""

    def test_v1_pipeline_used_when_flag_false(self):
        """When CSV_PIPELINE_V2=False, existing monolithic task runs."""
        with (
            patch("app.tasks.csv_processing.settings") as mock_settings,
            patch("app.tasks.csv_processing.asyncio") as mock_asyncio,
        ):
            mock_settings.CSV_PIPELINE_V2 = False
            from app.tasks.csv_processing import process_csv_upload

            # bind=True tasks: Celery provides self automatically via __call__,
            # so we call with just the 3 args. Use .run() to skip Celery dispatch.
            process_csv_upload.run("upload-id", "user-id", "base64data")
            mock_asyncio.run.assert_called_once()

    @pytest.mark.smoke
    def test_v2_pipeline_dispatched_when_flag_true(self):
        """When CSV_PIPELINE_V2=True, parse task is dispatched."""
        with (
            patch("app.tasks.csv_processing.settings") as mock_settings,
            patch("app.tasks.csv_pipeline.csv_parse_task") as mock_parse,
        ):
            mock_settings.CSV_PIPELINE_V2 = True
            mock_parse.delay = MagicMock()
            from app.tasks.csv_processing import process_csv_upload

            process_csv_upload.run("upload-id", "user-id", "base64data")
            mock_parse.delay.assert_called_once_with(
                "upload-id", "user-id", "base64data"
            )


class TestPipelineTasksExist:
    """Verify pipeline task functions are importable and registered."""

    @pytest.mark.smoke
    def test_csv_parse_task_importable(self):
        from app.tasks.csv_pipeline import csv_parse_task

        assert csv_parse_task is not None

    def test_csv_clean_worker_importable(self):
        from app.tasks.csv_pipeline import csv_clean_worker

        assert csv_clean_worker is not None

    def test_csv_import_task_importable(self):
        from app.tasks.csv_pipeline import csv_import_task

        assert csv_import_task is not None
