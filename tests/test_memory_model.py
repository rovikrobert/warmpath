"""Tests for the Memory model."""

import json
import uuid

import pytest
import pytest_asyncio

from tests.conftest import TestSessionLocal

pytestmark = pytest.mark.timeout(10)


@pytest_asyncio.fixture
async def db_session(truncate_tables):
    """Yield a test DB session."""
    async with TestSessionLocal() as session:
        yield session


def _parse_tags(val: object) -> list[str]:
    """Normalize ARRAY column — SQLite returns JSON string, Postgres returns list."""
    if isinstance(val, str):
        return json.loads(val)
    return val


class TestMemoryModel:
    """Verify Memory model creates and reads correctly."""

    @pytest.mark.asyncio
    async def test_create_memory(self, db_session):
        from app.models.memory import Memory

        mem = Memory(
            source_type="agent_scan",
            source_id="architect",
            team="engineering",
            content="Found N+1 query in contacts endpoint",
            summary="N+1 query in contacts",
            tags=["app/api/contacts.py", "performance", "high"],
            metadata_={"finding_id": "ARCH-001", "severity": "high"},
            importance=0.8,
        )
        db_session.add(mem)
        await db_session.commit()
        await db_session.refresh(mem)

        assert mem.id is not None
        assert isinstance(mem.id, uuid.UUID)
        assert mem.source_type == "agent_scan"
        assert mem.team == "engineering"
        assert mem.content == "Found N+1 query in contacts endpoint"
        assert _parse_tags(mem.tags) == [
            "app/api/contacts.py",
            "performance",
            "high",
        ]
        assert mem.importance == 0.8
        assert mem.created_at is not None
        assert mem.expires_at is None

    @pytest.mark.asyncio
    async def test_memory_defaults(self, db_session):
        from app.models.memory import Memory

        mem = Memory(
            source_type="user_note",
            source_id="manual",
            content="Remember to check Railway logs",
        )
        db_session.add(mem)
        await db_session.commit()
        await db_session.refresh(mem)

        assert mem.importance == 0.5
        assert mem.team is None
        assert mem.expires_at is None
