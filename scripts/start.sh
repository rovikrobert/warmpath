#!/usr/bin/env bash
# Entrypoint: runs uvicorn, celery worker, celery beat — or a subset.
# SERVICE_ROLE env var controls which processes start:
#   web    — uvicorn only
#   worker — celery worker only
#   beat   — celery beat only
#   scan   — run agent team scans + CoS daily brief, then exit (for Railway Cron)
#   all    — all three (default, single-container mode)

set -euo pipefail

ROLE="${SERVICE_ROLE:-all}"
CONCURRENCY="${CELERY_CONCURRENCY:-2}"
PIDS=()

cleanup() {
    echo "[entrypoint] Shutting down..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait
    exit 0
}

trap cleanup SIGTERM SIGINT

case "$ROLE" in
    web)
        echo "[entrypoint] Starting web only (role=$ROLE)"
        exec uvicorn app.main:app \
            --host 0.0.0.0 \
            --port "${PORT:-8000}"
        ;;
    worker)
        echo "[entrypoint] Starting worker only (role=$ROLE, concurrency=$CONCURRENCY)"
        exec celery -A app.celery_app:celery_app worker \
            --loglevel=info \
            --concurrency="$CONCURRENCY" \
            --pool=prefork \
            --without-heartbeat \
            --without-mingle \
            --without-gossip
        ;;
    beat)
        echo "[entrypoint] Starting beat only (role=$ROLE)"
        exec celery -A app.celery_app:celery_app beat \
            --loglevel=info
        ;;
    scan)
        echo "[entrypoint] Running agent scans (role=$ROLE)"
        exec python3 scripts/run_agent_scans.py
        ;;
    all)
        echo "[entrypoint] Starting all services (role=$ROLE, concurrency=$CONCURRENCY)"

        celery -A app.celery_app:celery_app worker \
            --loglevel=info \
            --concurrency="$CONCURRENCY" \
            --pool=prefork \
            --without-heartbeat \
            --without-mingle \
            --without-gossip &
        PIDS+=($!)
        echo "[entrypoint] Worker started (PID ${PIDS[0]})"

        celery -A app.celery_app:celery_app beat \
            --loglevel=info &
        PIDS+=($!)
        echo "[entrypoint] Beat started (PID ${PIDS[1]})"

        echo "[entrypoint] Exec'ing uvicorn as PID 1..."
        exec uvicorn app.main:app \
            --host 0.0.0.0 \
            --port "${PORT:-8000}"
        ;;
    *)
        echo "[entrypoint] Unknown SERVICE_ROLE: $ROLE (expected: web, worker, beat, all)"
        exit 1
        ;;
esac
