"""Tests for finding lifecycle tracking store."""

import pytest
import fakeredis.aioredis

from app.agent_runtime.finding_store import FindingStore, _finding_hash


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def store(fake_redis):
    return FindingStore(redis=fake_redis)


def test_finding_hash_is_deterministic():
    """Same finding produces the same hash."""
    f = {"source_team": "engineering", "category": "lint", "title": "Unused import"}
    assert _finding_hash(f) == _finding_hash(f)


def test_finding_hash_differs_for_different_findings():
    """Different findings produce different hashes."""
    f1 = {"source_team": "engineering", "category": "lint", "title": "Unused import"}
    f2 = {
        "source_team": "engineering",
        "category": "lint",
        "title": "Missing type hint",
    }
    assert _finding_hash(f1) != _finding_hash(f2)


@pytest.mark.asyncio
async def test_first_finding_classified_as_new(store):
    """First occurrence of a finding is classified as 'new'."""
    findings = [
        {"source_team": "engineering", "category": "lint", "title": "Unused import"}
    ]
    new, known = await store.classify_findings(findings)
    assert len(new) == 1
    assert len(known) == 0
    assert new[0]["finding_state"] == "new"
    assert "finding_hash" in new[0]


@pytest.mark.asyncio
async def test_repeated_finding_classified_as_known(store):
    """Second occurrence is classified as 'known' with seen_count."""
    findings = [
        {"source_team": "engineering", "category": "lint", "title": "Unused import"}
    ]
    await store.classify_findings(findings)
    # Second time
    new, known = await store.classify_findings(findings)
    assert len(new) == 0
    assert len(known) == 1
    assert known[0]["finding_state"] == "known"
    assert known[0]["seen_count"] == 2


@pytest.mark.asyncio
async def test_mark_resolved(store):
    """Resolved findings are tracked."""
    findings = [
        {"source_team": "engineering", "category": "lint", "title": "Unused import"}
    ]
    new, _ = await store.classify_findings(findings)
    fhash = new[0]["finding_hash"]
    result = await store.mark_resolved(fhash)
    assert result is True


@pytest.mark.asyncio
async def test_mark_resolved_nonexistent_returns_false(store):
    """Resolving unknown finding returns False."""
    result = await store.mark_resolved("nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_get_stats_counts_by_state(store):
    """Stats correctly count findings by state."""
    f1 = [{"source_team": "eng", "category": "lint", "title": "Issue A"}]
    f2 = [{"source_team": "eng", "category": "lint", "title": "Issue B"}]
    new1, _ = await store.classify_findings(f1)
    await store.classify_findings(f2)
    await store.mark_resolved(new1[0]["finding_hash"])

    stats = await store.get_stats()
    assert stats["resolved"] == 1
    assert stats["new"] == 1  # f2 is still new


@pytest.mark.asyncio
async def test_classify_findings_graceful_on_redis_failure():
    """FindingStore returns empty results if Redis is unavailable."""
    store = FindingStore(redis_url="redis://nonexistent:6379")
    new, known = await store.classify_findings(
        [{"source_team": "eng", "category": "test", "title": "Issue"}]
    )
    assert new == []
    assert known == []


@pytest.mark.asyncio
async def test_get_stats_graceful_on_redis_failure():
    """get_stats returns zeroed dict if Redis is unavailable."""
    store = FindingStore(redis_url="redis://nonexistent:6379")
    stats = await store.get_stats()
    assert stats == {"new": 0, "known": 0, "resolved": 0}


@pytest.mark.asyncio
async def test_mark_resolved_graceful_on_redis_failure():
    """mark_resolved returns False if Redis is unavailable."""
    store = FindingStore(redis_url="redis://nonexistent:6379")
    result = await store.mark_resolved("some_hash")
    assert result is False
