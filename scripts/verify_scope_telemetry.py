#!/usr/bin/env python3
"""Verify Phase 3 scope telemetry sequence via PostHog HogQL.

Expected sequence per user/session context:
1) search_scope_experiment_assigned
2) search_scope_selected OR search_scope_auto_selected
3) search_scope_decision

Usage:
  python3 scripts/verify_scope_telemetry.py --days 7 --limit 200

Requires env vars:
  POSTHOG_API_KEY
  POSTHOG_PROJECT_ID
Optional:
  POSTHOG_HOST (default: https://app.posthog.com)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request


def _posthog_query(query: str, host: str, project_id: str, api_key: str) -> dict:
    url = f"{host.rstrip('/')}/api/projects/{project_id}/query/"
    payload = {
        "query": {
            "kind": "HogQLQuery",
            "query": query,
        }
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7, help="Lookback window in days")
    parser.add_argument(
        "--limit", type=int, default=200, help="Max distinct users to inspect"
    )
    args = parser.parse_args()

    api_key = os.getenv("POSTHOG_API_KEY")
    project_id = os.getenv("POSTHOG_PROJECT_ID")
    host = os.getenv("POSTHOG_HOST", "https://app.posthog.com")

    if not api_key or not project_id:
        print("Missing POSTHOG_API_KEY or POSTHOG_PROJECT_ID", file=sys.stderr)
        return 2

    q = f"""
WITH scoped AS (
  SELECT
    distinct_id,
    event,
    timestamp
  FROM events
  WHERE event IN (
    'search_scope_experiment_assigned',
    'search_scope_selected',
    'search_scope_auto_selected',
    'search_scope_decision'
  )
    AND timestamp >= now() - INTERVAL {args.days} DAY
),
summary AS (
  SELECT
    distinct_id,
    minIf(timestamp, event = 'search_scope_experiment_assigned') AS assigned_at,
    minIf(timestamp, event IN ('search_scope_selected', 'search_scope_auto_selected')) AS selected_at,
    minIf(timestamp, event = 'search_scope_decision') AS decided_at,
    countIf(event = 'search_scope_experiment_assigned') AS assigned_count,
    countIf(event = 'search_scope_selected') AS selected_count,
    countIf(event = 'search_scope_auto_selected') AS auto_selected_count,
    countIf(event = 'search_scope_decision') AS decision_count
  FROM scoped
  GROUP BY distinct_id
)
SELECT
  distinct_id,
  assigned_count,
  selected_count,
  auto_selected_count,
  decision_count,
  assigned_at,
  selected_at,
  decided_at,
  (assigned_at IS NOT NULL AND selected_at IS NOT NULL AND decided_at IS NOT NULL AND assigned_at <= selected_at AND selected_at <= decided_at) AS in_order
FROM summary
ORDER BY decided_at DESC NULLS LAST
LIMIT {args.limit}
"""

    result = _posthog_query(q, host, project_id, api_key)
    rows = result.get("results", [])
    if not rows:
        print("No Phase 3 scope telemetry found in window.")
        return 1

    in_order = 0
    out_of_order = 0
    incomplete = 0

    for row in rows:
        assigned_at = row[5]
        selected_at = row[6]
        decided_at = row[7]
        ok = bool(row[8])
        if assigned_at and selected_at and decided_at:
            if ok:
                in_order += 1
            else:
                out_of_order += 1
        else:
            incomplete += 1

    total = len(rows)
    print(f"Checked users: {total}")
    print(f"In-order sequence: {in_order}")
    print(f"Out-of-order sequence: {out_of_order}")
    print(f"Incomplete sequence: {incomplete}")

    # Non-zero if we found ordering issues for quick CI/ops signal.
    if out_of_order > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
