"""Tests for MemoryService — write path (remember) + read path (hybrid recall).

Covers: DB persistence, TTL/expiry, BM25 keyword search (SQLite LIKE fallback),
team filtering, temporal decay ordering, file-tag lookup, and recent-memory queries.
Runs on SQLite (test environment) so BM25 tests exercise the LIKE fallback.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from tests.conftest import TestSessionLocal

pytestmark = [
    pytest.mark.usefixtures("truncate_tables"),
    pytest.mark.timeout(30),
]


@pytest_asyncio.fixture
async def db_session(truncate_tables):
    """Yield a test DB session."""
    async with TestSessionLocal() as session:
        yield session


def _parse_tags(val: object) -> list[str]:
    """Normalize ARRAY column — SQLite returns JSON string, Postgres returns list."""
    if isinstance(val, str):
        return json.loads(val)
    return val if val is not None else []


# ---------------------------------------------------------------------------
# Task 3: Write path — remember()
# ---------------------------------------------------------------------------


class TestRememberStoresInDb:
    """Verify remember() persists a Memory row with correct fields."""

    @pytest.mark.asyncio
    async def test_remember_stores_in_db(self, db_session):
        from app.services.memory_service import MemoryService

        svc = MemoryService(db_session)
        mem_id = await svc.remember(
            content="Found N+1 query in contacts endpoint",
            source_type="agent_scan",
            source_id="architect",
            summary="N+1 query in contacts",
            team="engineering",
            tags=["app/api/contacts.py", "performance"],
            metadata={"finding_id": "ARCH-001"},
            importance=0.8,
        )

        assert isinstance(mem_id, uuid.UUID)

        # Verify row in DB
        from sqlalchemy import select

        from app.models.memory import Memory

        result = await db_session.execute(select(Memory).where(Memory.id == mem_id))
        mem = result.scalar_one()

        assert mem.source_type == "agent_scan"
        assert mem.source_id == "architect"
        assert mem.team == "engineering"
        assert mem.content == "Found N+1 query in contacts endpoint"
        assert mem.summary == "N+1 query in contacts"
        assert _parse_tags(mem.tags) == ["app/api/contacts.py", "performance"]
        assert mem.importance == 0.8
        assert mem.expires_at is None
        assert mem.created_at is not None


class TestRememberWithTtl:
    """Verify TTL sets expires_at correctly."""

    @pytest.mark.asyncio
    async def test_remember_with_ttl_sets_expires_at(self, db_session):
        from app.services.memory_service import MemoryService

        svc = MemoryService(db_session)
        before = datetime.now(timezone.utc)

        mem_id = await svc.remember(
            content="Temporary finding — auto-expire in 24h",
            source_type="session_note",
            source_id="claude_code",
            ttl_hours=24,
        )

        after = datetime.now(timezone.utc)

        from sqlalchemy import select

        from app.models.memory import Memory

        result = await db_session.execute(select(Memory).where(Memory.id == mem_id))
        mem = result.scalar_one()

        assert mem.expires_at is not None
        # expires_at should be ~24h from now
        expected_min = before + timedelta(hours=24)
        expected_max = after + timedelta(hours=24)
        expires = mem.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        assert expected_min <= expires <= expected_max


# ---------------------------------------------------------------------------
# Task 4: Read path — recall() with BM25 (SQLite LIKE fallback)
# ---------------------------------------------------------------------------


class TestBm25SearchFindsByKeyword:
    """Store two memories with different content, search by keyword, verify correct one ranked first."""

    @pytest.mark.asyncio
    async def test_bm25_search_finds_relevant_memory(self, db_session):
        from app.services.memory_service import MemoryService

        svc = MemoryService(db_session)

        # Store two memories with distinct topics
        await svc.remember(
            content="Database query performance is slow on the contacts endpoint, N+1 detected",
            source_type="agent_scan",
            source_id="architect",
            importance=0.7,
        )
        await svc.remember(
            content="Frontend CSS layout broken on mobile Safari browser rendering",
            source_type="agent_scan",
            source_id="frontend_qa",
            importance=0.7,
        )

        # Search for "database query performance"
        results = await svc.recall("database query performance", top_k=5)

        assert len(results) >= 1
        # The database-related memory should be ranked first
        assert (
            "database" in results[0]["content"].lower()
            or "query" in results[0]["content"].lower()
        )


class TestRecallFiltersByTeam:
    """Team filter excludes memories from other teams."""

    @pytest.mark.asyncio
    async def test_recall_filters_by_team(self, db_session):
        from app.services.memory_service import MemoryService

        svc = MemoryService(db_session)

        await svc.remember(
            content="Engineering memory about API refactor",
            source_type="agent_scan",
            source_id="architect",
            team="engineering",
        )
        await svc.remember(
            content="Product memory about API usage patterns",
            source_type="agent_scan",
            source_id="product_lead",
            team="product",
        )

        # Search with team filter
        results = await svc.recall("API", team="engineering")

        assert len(results) >= 1
        for r in results:
            assert r["team"] == "engineering"


class TestRecallExcludesExpired:
    """Expired memories should not appear in search results."""

    @pytest.mark.asyncio
    async def test_recall_excludes_expired_memories(self, db_session):
        from app.models.memory import Memory
        from app.services.memory_service import MemoryService

        svc = MemoryService(db_session)

        # Store a live memory
        await svc.remember(
            content="Active memory about deployment pipeline",
            source_type="session_note",
            source_id="claude_code",
        )

        # Manually insert an expired memory
        expired_mem = Memory(
            source_type="session_note",
            source_id="claude_code",
            content="Expired memory about deployment pipeline and CI",
            importance=0.9,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db_session.add(expired_mem)
        await db_session.commit()

        results = await svc.recall("deployment pipeline")

        # Only the active memory should appear
        assert len(results) == 1
        assert "Active memory" in results[0]["content"]


class TestTemporalDecayBoostsRecent:
    """Recent memories should rank higher than old ones (all else equal)."""

    @pytest.mark.asyncio
    async def test_temporal_decay_boosts_recent_over_old(self, db_session):
        from app.models.memory import Memory
        from app.services.memory_service import MemoryService

        svc = MemoryService(db_session)

        # Recent memory
        await svc.remember(
            content="Fresh insight about Redis caching strategy",
            source_type="agent_scan",
            source_id="architect",
            importance=0.5,
        )

        # Old memory (backdate to 180 days ago)
        old_mem = Memory(
            source_type="agent_scan",
            source_id="architect",
            content="Old insight about Redis caching improvements",
            importance=0.5,
            created_at=datetime.now(timezone.utc) - timedelta(days=180),
        )
        db_session.add(old_mem)
        await db_session.commit()

        results = await svc.recall(
            "Redis caching",
            top_k=5,
            temporal_half_life=90,
        )

        assert len(results) == 2
        # Recent memory should score higher due to temporal decay
        assert "Fresh" in results[0]["content"]
        assert "Old" in results[1]["content"]
        # Verify score ordering
        assert results[0]["score"] > results[1]["score"]


class TestRecallAboutFile:
    """Tag-based file lookup returns memories tagged with a specific path."""

    @pytest.mark.asyncio
    async def test_recall_about_file_finds_tagged_memories(self, db_session):
        from app.services.memory_service import MemoryService

        svc = MemoryService(db_session)

        await svc.remember(
            content="Found security issue in auth middleware",
            source_type="agent_scan",
            source_id="security_agent",
            tags=["app/middleware/auth.py", "security"],
        )
        await svc.remember(
            content="Performance issue in search endpoint",
            source_type="agent_scan",
            source_id="perf_agent",
            tags=["app/api/search.py", "performance"],
        )

        results = await svc.recall_about_file("app/middleware/auth.py")

        assert len(results) == 1
        assert "auth middleware" in results[0]["content"]
        assert "app/middleware/auth.py" in _parse_tags(results[0]["tags"])


class TestRecallRecent:
    """Time-based recent lookup returns memories from the last N days."""

    @pytest.mark.asyncio
    async def test_recall_recent_returns_within_window(self, db_session):
        from app.models.memory import Memory
        from app.services.memory_service import MemoryService

        svc = MemoryService(db_session)

        # Recent memory (created now)
        await svc.remember(
            content="Recent finding from today's scan",
            source_type="agent_scan",
            source_id="architect",
            team="engineering",
        )

        # Old memory (30 days ago)
        old_mem = Memory(
            source_type="agent_scan",
            source_id="architect",
            team="engineering",
            content="Old finding from last month's scan",
            importance=0.5,
            created_at=datetime.now(timezone.utc) - timedelta(days=30),
        )
        db_session.add(old_mem)
        await db_session.commit()

        results = await svc.recall_recent(days=7, team="engineering")

        assert len(results) == 1
        assert "Recent finding" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_recall_recent_without_team_filter(self, db_session):
        from app.services.memory_service import MemoryService

        svc = MemoryService(db_session)

        await svc.remember(
            content="Engineering memory from today",
            source_type="agent_scan",
            source_id="architect",
            team="engineering",
        )
        await svc.remember(
            content="Product memory from today",
            source_type="agent_scan",
            source_id="product_lead",
            team="product",
        )

        results = await svc.recall_recent(days=7)

        assert len(results) == 2


# ---------------------------------------------------------------------------
# Additional edge-case tests
# ---------------------------------------------------------------------------


class TestRecallEmptyQuery:
    """Recall with a query that matches nothing returns empty list."""

    @pytest.mark.asyncio
    async def test_recall_no_matches_returns_empty(self, db_session):
        from app.services.memory_service import MemoryService

        svc = MemoryService(db_session)

        await svc.remember(
            content="Memory about Python FastAPI framework",
            source_type="agent_scan",
            source_id="architect",
        )

        results = await svc.recall("xyznonexistenttopic123")

        assert results == []


class TestRowToDict:
    """Verify _row_to_dict produces correct output shape."""

    @pytest.mark.asyncio
    async def test_row_to_dict_has_expected_keys(self, db_session):
        from app.services.memory_service import MemoryService

        svc = MemoryService(db_session)

        await svc.remember(
            content="Test memory for dict conversion",
            source_type="user_note",
            source_id="manual",
            team="engineering",
            tags=["test"],
            metadata={"key": "value"},
            importance=0.6,
        )

        results = await svc.recall("dict conversion")

        assert len(results) >= 1
        r = results[0]
        expected_keys = {
            "id",
            "source_type",
            "source_id",
            "team",
            "content",
            "summary",
            "tags",
            "metadata",
            "importance",
            "created_at",
            "updated_at",
            "expires_at",
            "score",
        }
        assert expected_keys.issubset(set(r.keys()))
        assert r["source_type"] == "user_note"
        assert r["team"] == "engineering"
        assert r["importance"] == 0.6


class TestMmrDiversifiesResults:
    """MMR re-ranking should diversify results with similar content."""

    @pytest.mark.asyncio
    async def test_mmr_selects_diverse_content(self, db_session):
        from app.services.memory_service import MemoryService

        svc = MemoryService(db_session)

        # Store three similar memories and one different one
        await svc.remember(
            content="Redis caching strategy for contacts endpoint response time",
            source_type="agent_scan",
            source_id="arch",
            importance=0.8,
        )
        await svc.remember(
            content="Redis caching strategy for marketplace endpoint response time",
            source_type="agent_scan",
            source_id="arch",
            importance=0.8,
        )
        await svc.remember(
            content="Redis caching approach for search endpoint latency optimisation",
            source_type="agent_scan",
            source_id="arch",
            importance=0.8,
        )
        await svc.remember(
            content="Database index missing on Redis cache keys table causing slow lookups",
            source_type="agent_scan",
            source_id="data",
            importance=0.8,
        )

        # With MMR lambda=0.5 (strong diversity preference)
        results = await svc.recall("Redis caching", top_k=4, mmr_lambda=0.5)

        assert len(results) >= 2
        # All results should mention Redis or caching
        for r in results:
            content_lower = r["content"].lower()
            assert (
                "redis" in content_lower
                or "caching" in content_lower
                or "cache" in content_lower
            )


class TestRememberWithVectorSearchDisabled:
    """With VECTOR_SEARCH_ENABLED=False, remember() should not attempt embedding."""

    @pytest.mark.asyncio
    async def test_remember_skips_embedding_when_disabled(self, db_session):
        from app.services.memory_service import MemoryService

        svc = MemoryService(db_session)

        with patch("app.services.memory_service.settings") as mock_settings:
            mock_settings.VECTOR_SEARCH_ENABLED = False
            mock_settings.MEMORY_BM25_WEIGHT = 0.4
            mock_settings.MEMORY_VECTOR_WEIGHT = 0.6
            mock_settings.MEMORY_TEMPORAL_HALF_LIFE_DAYS = 90
            mock_settings.MEMORY_MMR_LAMBDA = 0.7
            mock_settings.MEMORY_CANDIDATE_POOL = 50

            with patch.object(
                svc, "_embed_memory", new_callable=AsyncMock
            ) as mock_embed:
                mem_id = await svc.remember(
                    content="Should not trigger embedding",
                    source_type="test",
                    source_id="test",
                )
                mock_embed.assert_not_called()

        assert isinstance(mem_id, uuid.UUID)


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


class TestRecallEmptyStringQuery:
    """Empty or whitespace-only queries return empty results without hitting DB."""

    @pytest.mark.asyncio
    async def test_recall_empty_string_returns_empty(self, db_session):
        from app.services.memory_service import MemoryService

        svc = MemoryService(db_session)
        assert await svc.recall("") == []

    @pytest.mark.asyncio
    async def test_recall_whitespace_only_returns_empty(self, db_session):
        from app.services.memory_service import MemoryService

        svc = MemoryService(db_session)
        assert await svc.recall("   ") == []


class TestRecallAboutFileEmptyPath:
    """Empty file path returns empty results."""

    @pytest.mark.asyncio
    async def test_recall_about_file_empty_string(self, db_session):
        from app.services.memory_service import MemoryService

        svc = MemoryService(db_session)
        assert await svc.recall_about_file("") == []


class TestRememberWithZeroImportance:
    """Importance=0 should still store and retrieve, but rank lower."""

    @pytest.mark.asyncio
    async def test_zero_importance_memory_retrievable(self, db_session):
        from app.services.memory_service import MemoryService

        svc = MemoryService(db_session)
        mem_id = await svc.remember(
            content="Low priority background note about testing patterns",
            source_type="user_note",
            source_id="manual",
            importance=0.0,
        )
        assert isinstance(mem_id, uuid.UUID)

        results = await svc.recall("testing patterns")
        assert len(results) == 1
        assert results[0]["importance"] == 0.0


class TestRememberContentValidation:
    """remember() should handle various content edge cases."""

    @pytest.mark.asyncio
    async def test_very_long_content_stored(self, db_session):
        from app.services.memory_service import MemoryService

        svc = MemoryService(db_session)
        long_content = "keyword " * 5000  # ~40KB of text
        mem_id = await svc.remember(
            content=long_content,
            source_type="test",
            source_id="test",
        )
        assert isinstance(mem_id, uuid.UUID)

        results = await svc.recall("keyword")
        assert len(results) == 1


class TestMmrWithSingleCandidate:
    """MMR re-ranking with a single candidate should just return it."""

    @pytest.mark.asyncio
    async def test_mmr_single_result(self, db_session):
        from app.services.memory_service import MemoryService

        svc = MemoryService(db_session)
        await svc.remember(
            content="Unique finding about singleton pattern",
            source_type="agent_scan",
            source_id="arch",
        )

        results = await svc.recall("singleton pattern", top_k=10)
        assert len(results) == 1


class TestRecallSourceTypeFilter:
    """source_type filter restricts results correctly."""

    @pytest.mark.asyncio
    async def test_source_type_filter(self, db_session):
        from app.services.memory_service import MemoryService

        svc = MemoryService(db_session)
        await svc.remember(
            content="Agent scan found database index issue",
            source_type="agent_scan",
            source_id="arch",
        )
        await svc.remember(
            content="Session note about database migration",
            source_type="session_note",
            source_id="claude",
        )

        results = await svc.recall("database", source_type="agent_scan")
        assert len(results) == 1
        assert results[0]["source_type"] == "agent_scan"
