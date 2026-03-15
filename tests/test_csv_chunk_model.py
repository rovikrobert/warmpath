"""Tests for CsvUploadChunk model."""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import CsvUpload, CsvUploadChunk
from tests.conftest import TestSessionLocal, create_test_user_in_db


@pytest_asyncio.fixture
async def db(truncate_tables):
    """Yield a test DB session."""
    async with TestSessionLocal() as session:
        yield session


class TestCsvUploadChunkModel:
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_create_chunk_with_required_fields(self, db):
        """CsvUploadChunk can be created with upload_id, chunk_index, contacts_count."""
        user, _ = await create_test_user_in_db(db)
        upload = CsvUpload(user_id=user.id, filename="test.csv", status="processing")
        db.add(upload)
        await db.flush()

        chunk = CsvUploadChunk(
            upload_id=upload.id,
            chunk_index=0,
            contacts_count=200,
            status="pending",
        )
        db.add(chunk)
        await db.commit()

        result = await db.execute(
            select(CsvUploadChunk).where(CsvUploadChunk.upload_id == upload.id)
        )
        saved = result.scalar_one()
        assert saved.chunk_index == 0
        assert saved.contacts_count == 200
        assert saved.status == "pending"
        assert saved.provider_used is None

    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_csv_upload_has_chunk_tracking_columns(self, db):
        """CsvUpload has total_chunks, chunks_cleaned, chunks_imported columns."""
        user, _ = await create_test_user_in_db(db)
        upload = CsvUpload(
            user_id=user.id,
            filename="test.csv",
            status="processing",
            total_chunks=10,
            chunks_cleaned=5,
            chunks_imported=3,
        )
        db.add(upload)
        await db.commit()

        result = await db.execute(select(CsvUpload).where(CsvUpload.id == upload.id))
        saved = result.scalar_one()
        assert saved.total_chunks == 10
        assert saved.chunks_cleaned == 5
        assert saved.chunks_imported == 3
