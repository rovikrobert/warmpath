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

start_worker() {
    celery -A app.celery_app:celery_app worker \
        --loglevel=info \
        --concurrency="$CONCURRENCY" \
        --pool=prefork \
        --without-heartbeat \
        --without-mingle \
        --without-gossip "$@"
}

start_beat() {
    celery -A app.celery_app:celery_app beat \
        --loglevel=info "$@"
}

start_web() {
    uvicorn app.main:app \
        --host 0.0.0.0 \
        --port "${PORT:-8000}" "$@"
}

case "$ROLE" in
    web)
        echo "[entrypoint] Starting web only (role=$ROLE)"
        start_web  # foreground
        ;;
    worker)
        echo "[entrypoint] Starting worker only (role=$ROLE, concurrency=$CONCURRENCY)"
        start_worker  # foreground
        ;;
    beat)
        echo "[entrypoint] Starting beat only (role=$ROLE)"
        start_beat  # foreground
        ;;
    scan)
        echo "[entrypoint] Running agent scans (role=$ROLE)"
        python3 scripts/run_agent_scans.py
        echo "[entrypoint] Scans complete, exiting."
        exit 0
        ;;
    all)
        echo "[entrypoint] Starting all services (role=$ROLE, concurrency=$CONCURRENCY)"

        start_worker &
        PIDS+=($!)
        echo "[entrypoint] Worker started (PID ${PIDS[0]})"

        start_beat &
        PIDS+=($!)
        echo "[entrypoint] Beat started (PID ${PIDS[1]})"

        start_web &
        PIDS+=($!)
        echo "[entrypoint] Web started (PID ${PIDS[2]})"

        # Wait for any child to exit — then tear down all
        wait -n
        echo "[entrypoint] A process exited, shutting down all..."
        cleanup
        ;;
    *)
        echo "[entrypoint] Unknown SERVICE_ROLE: $ROLE (expected: web, worker, beat, all)"
        exit 1
        ;;
esac
