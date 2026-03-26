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


class TestV2CompanyLinking:
    """Test that the V2 importer links contacts to Company rows."""

    @pytest.mark.asyncio
    async def test_import_links_contacts_to_existing_company(self, truncate_tables):
        """V2 import sets company_id when company already exists in cache."""
        import uuid as _uuid

        from app.models.company import Company
        from app.models.contact import Contact
        from app.tasks.csv_pipeline import _link_companies_for_upload
        from tests.conftest import TestSessionLocal, create_test_user_in_db

        async with TestSessionLocal() as db:
            user, _ = await create_test_user_in_db(db)

            # Pre-existing company
            company = Company(name="Stripe")
            db.add(company)
            await db.flush()

            upload_id = _uuid.uuid4()
            contact = Contact(
                user_id=user.id,
                full_name="Alice Smith",
                current_company="Stripe, Inc.",
                csv_upload_id=upload_id,
                source="csv",
            )
            db.add(contact)
            await db.flush()

            # Cache mirrors what the importer builds: name.lower() -> id
            cache: dict[str, _uuid.UUID | None] = {"stripe": company.id}

            await _link_companies_for_upload(db, upload_id, cache)

            await db.refresh(contact)
            assert contact.company_id == company.id

    @pytest.mark.asyncio
    async def test_import_creates_new_company_for_unknown_name(self, truncate_tables):
        """V2 import creates a Company row when name is not in cache."""
        import uuid as _uuid

        from sqlalchemy import select

        from app.models.company import Company
        from app.models.contact import Contact
        from app.tasks.csv_pipeline import _link_companies_for_upload
        from tests.conftest import TestSessionLocal, create_test_user_in_db

        async with TestSessionLocal() as db:
            user, _ = await create_test_user_in_db(db)

            upload_id = _uuid.uuid4()
            contact = Contact(
                user_id=user.id,
                full_name="Bob Jones",
                current_company="Acme Corp",
                csv_upload_id=upload_id,
                source="csv",
            )
            db.add(contact)
            await db.flush()

            cache: dict[str, _uuid.UUID | None] = {}

            await _link_companies_for_upload(db, upload_id, cache)

            await db.refresh(contact)
            assert contact.company_id is not None

            # Verify the company was created and added to cache
            assert "acme" in cache
            assert cache["acme"] == contact.company_id

            # Verify actual Company row exists
            result = await db.execute(
                select(Company).where(Company.id == contact.company_id)
            )
            company = result.scalar_one()
            assert company.name == "Acme"

    @pytest.mark.asyncio
    async def test_import_skips_contacts_without_current_company(self, truncate_tables):
        """Contacts with no current_company get company_id=None without error."""
        import uuid as _uuid

        from app.models.contact import Contact
        from app.tasks.csv_pipeline import _link_companies_for_upload
        from tests.conftest import TestSessionLocal, create_test_user_in_db

        async with TestSessionLocal() as db:
            user, _ = await create_test_user_in_db(db)

            upload_id = _uuid.uuid4()
            contact = Contact(
                user_id=user.id,
                full_name="Carol Doe",
                current_company=None,
                csv_upload_id=upload_id,
                source="csv",
            )
            db.add(contact)
            await db.flush()

            cache: dict[str, _uuid.UUID | None] = {}

            # Should not raise
            await _link_companies_for_upload(db, upload_id, cache)

            await db.refresh(contact)
            assert contact.company_id is None
