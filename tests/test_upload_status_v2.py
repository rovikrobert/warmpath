"""Tests for extended upload status response with chunk progress."""

from app.schemas.contact import CsvUploadResponse


class TestExtendedUploadStatus:
    def test_schema_includes_chunk_fields(self):
        """CsvUploadResponse includes total_chunks, chunks_cleaned, chunks_imported."""
        data = CsvUploadResponse(
            id="00000000-0000-0000-0000-000000000001",
            status="processing",
            filename="test.csv",
            row_count=10000,
            processed_count=5000,
            error_count=0,
            total_chunks=50,
            chunks_cleaned=25,
            chunks_imported=10,
            progress_phase="cleaning",
            created_at="2026-02-21T00:00:00Z",
        )
        dumped = data.model_dump()
        assert dumped["total_chunks"] == 50
        assert dumped["chunks_cleaned"] == 25
        assert dumped["chunks_imported"] == 10

    def test_schema_chunk_fields_default_to_none(self):
        """Chunk fields are optional and default to None for V1 uploads."""
        data = CsvUploadResponse(
            id="00000000-0000-0000-0000-000000000001",
            status="completed",
            filename="test.csv",
            row_count=100,
            processed_count=100,
            error_count=0,
            created_at="2026-02-21T00:00:00Z",
        )
        dumped = data.model_dump()
        assert dumped["total_chunks"] is None
        assert dumped["chunks_cleaned"] is None
        assert dumped["chunks_imported"] is None
