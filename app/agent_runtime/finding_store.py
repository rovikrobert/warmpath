"""Redis-backed finding lifecycle tracking.

Tracks findings across scans so agents don't re-report known issues.
States: new → known → resolved.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

PREFIX = "agentrt:finding"
# Findings auto-expire after 30 days if not refreshed
FINDING_TTL_SECONDS = 30 * 86400


def _finding_hash(finding: dict[str, Any]) -> str:
    """Deterministic hash from finding title + source_team + category."""
    raw = f"{finding.get('source_team', '')}:{finding.get('category', '')}:{finding.get('title', '')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class FindingStore:
    """Track finding lifecycle across agent scans."""

    def __init__(
        self, redis: aioredis.Redis | None = None, redis_url: str = ""
    ) -> None:
        self._redis = redis
        self._redis_url = redis_url

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    async def classify_findings(
        self, findings: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Split findings into new and already-known.

        Returns (new_findings, known_findings). Each finding gets a
        `finding_hash` and `finding_state` field added.
        """
        r = await self._get_redis()
        new: list[dict[str, Any]] = []
        known: list[dict[str, Any]] = []

        for finding in findings:
            fhash = _finding_hash(finding)
            key = f"{PREFIX}:{fhash}"
            existing = await r.get(key)

            finding["finding_hash"] = fhash

            if existing is None:
                # First time seeing this finding
                finding["finding_state"] = "new"
                record = {
                    "title": finding.get("title", ""),
                    "source_team": finding.get("source_team", ""),
                    "category": finding.get("category", ""),
                    "severity": finding.get("severity", "medium"),
                    "seen_count": 1,
                    "state": "new",
                }
                await r.set(key, json.dumps(record), ex=FINDING_TTL_SECONDS)
                new.append(finding)
            else:
                # Already known — increment seen_count, refresh TTL
                record = json.loads(existing)
                record["seen_count"] = record.get("seen_count", 0) + 1
                record["state"] = "known"
                finding["finding_state"] = "known"
                finding["seen_count"] = record["seen_count"]
                await r.set(key, json.dumps(record), ex=FINDING_TTL_SECONDS)
                known.append(finding)

        return new, known

    async def mark_resolved(self, finding_hash: str) -> bool:
        """Mark a finding as resolved. Returns True if it existed."""
        r = await self._get_redis()
        key = f"{PREFIX}:{finding_hash}"
        existing = await r.get(key)
        if existing is None:
            return False
        record = json.loads(existing)
        record["state"] = "resolved"
        await r.set(key, json.dumps(record), ex=FINDING_TTL_SECONDS)
        return True

    async def get_stats(self) -> dict[str, int]:
        """Return counts of findings by state."""
        r = await self._get_redis()
        cursor = "0"
        stats: dict[str, int] = {"new": 0, "known": 0, "resolved": 0}
        while True:
            cursor, keys = await r.scan(cursor=cursor, match=f"{PREFIX}:*", count=100)
            for key in keys:
                val = await r.get(key)
                if val:
                    record = json.loads(val)
                    state = record.get("state", "new")
                    stats[state] = stats.get(state, 0) + 1
            if cursor == 0 or cursor == "0":
                break
        return stats
