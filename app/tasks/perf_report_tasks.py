"""Daily performance report task.

Collects pg_stat_statements metrics and stores a summary in the
enrichment_cache table for the perf dashboard to surface.
"""

import contextlib
import json
import logging
from datetime import datetime, timedelta, timezone

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


def _collect_pg_stat_statements(session) -> list[dict]:
    """Query pg_stat_statements for top slow queries.

    Returns top 20 queries by total_exec_time, excluding pg_catalog queries.
    Requires pg_stat_statements extension to be enabled in PostgreSQL.
    """
    from sqlalchemy import text

    try:
        result = session.execute(
            text("""
            SELECT
                queryid,
                LEFT(query, 200) AS query_short,
                calls,
                ROUND(total_exec_time::numeric, 2) AS total_time_ms,
                ROUND(mean_exec_time::numeric, 2) AS mean_time_ms,
                ROUND(min_exec_time::numeric, 2) AS min_time_ms,
                ROUND(max_exec_time::numeric, 2) AS max_time_ms,
                rows
            FROM pg_stat_statements
            WHERE userid = (SELECT usesysid FROM pg_user WHERE usename = current_user)
            ORDER BY total_exec_time DESC
            LIMIT 20
            """)
        )
        return [dict(row._mapping) for row in result]
    except Exception as e:
        logger.warning("pg_stat_statements unavailable: %s", e)
        return []


def _collect_table_stats(session) -> list[dict]:
    """Collect table-level stats: row counts, dead tuples, last vacuum/analyze."""
    from sqlalchemy import text

    try:
        result = session.execute(
            text("""
            SELECT
                schemaname,
                relname AS table_name,
                n_live_tup AS live_rows,
                n_dead_tup AS dead_rows,
                ROUND(
                    100.0 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0), 1
                ) AS dead_pct,
                last_vacuum,
                last_autovacuum,
                last_analyze,
                last_autoanalyze,
                seq_scan,
                idx_scan
            FROM pg_stat_user_tables
            WHERE schemaname = 'public'
            ORDER BY n_live_tup DESC
            LIMIT 30
        """)
        )
        rows = []
        for row in result:
            d = dict(row._mapping)
            # Convert datetimes to ISO strings for JSON
            for k in (
                "last_vacuum",
                "last_autovacuum",
                "last_analyze",
                "last_autoanalyze",
            ):
                if d.get(k):
                    d[k] = d[k].isoformat()
            rows.append(d)
        return rows
    except Exception as e:
        logger.warning("Table stats collection failed: %s", e)
        return []


def _collect_index_usage(session) -> list[dict]:
    """Find unused or rarely-used indexes."""
    from sqlalchemy import text

    try:
        result = session.execute(
            text("""
            SELECT
                schemaname,
                relname AS table_name,
                indexrelname AS index_name,
                idx_scan AS scans,
                pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
            FROM pg_stat_user_indexes
            WHERE schemaname = 'public'
            ORDER BY idx_scan ASC
            LIMIT 20
        """)
        )
        return [dict(row._mapping) for row in result]
    except Exception as e:
        logger.warning("Index usage stats failed: %s", e)
        return []


@celery_app.task(name="app.tasks.perf_report_tasks.daily_perf_report")
def daily_perf_report():
    """Generate daily DB performance report and store in enrichment_cache."""
    from sqlalchemy import text

    from app.database import get_sync_db

    logger.info("Generating daily performance report")

    gen = get_sync_db()
    session = next(gen)
    try:
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "slow_queries": _collect_pg_stat_statements(session),
            "table_stats": _collect_table_stats(session),
            "index_usage": _collect_index_usage(session),
        }

        # Store in enrichment_cache with 25-hour TTL (overlaps with next run)
        cache_key = "perf_report_daily"
        existing = session.execute(
            text("SELECT id FROM enrichment_cache WHERE cache_key = :key"),
            {"key": cache_key},
        ).first()

        expires_at = datetime.now(timezone.utc) + timedelta(hours=25)

        if existing:
            session.execute(
                text(
                    "UPDATE enrichment_cache SET data = :data, expires_at = :exp, "
                    "updated_at = NOW() WHERE cache_key = :key"
                ),
                {
                    "data": json.dumps(report, default=str),
                    "exp": expires_at,
                    "key": cache_key,
                },
            )
        else:
            session.execute(
                text(
                    "INSERT INTO enrichment_cache (id, cache_key, source, data, expires_at) "
                    "VALUES (gen_random_uuid(), :key, 'perf_report', :data, :exp)"
                ),
                {
                    "key": cache_key,
                    "data": json.dumps(report, default=str),
                    "exp": expires_at,
                },
            )

        session.commit()

        slow_count = len(report["slow_queries"])
        table_count = len(report["table_stats"])
        logger.info(
            "Daily perf report generated: %d slow queries, %d table stats",
            slow_count,
            table_count,
        )
        return {"slow_queries": slow_count, "table_stats": table_count}
    except Exception:
        session.rollback()
        logger.exception("Failed to generate daily perf report")
        raise
    finally:
        with contextlib.suppress(StopIteration):
            next(gen)
