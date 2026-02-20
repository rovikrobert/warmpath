#!/usr/bin/env bash
# Entrypoint: runs uvicorn + celery worker + celery beat in one container.
# If any process exits, SIGTERM is sent to all others so Railway restarts.

set -euo pipefail

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

# --- Celery Worker ---
celery -A app.celery_app:celery_app worker \
    --loglevel=info \
    --concurrency=2 \
    --pool=prefork \
    --without-heartbeat \
    --without-mingle \
    --without-gossip &
PIDS+=($!)
echo "[entrypoint] Worker started (PID ${PIDS[0]})"

# --- Celery Beat ---
celery -A app.celery_app:celery_app beat \
    --loglevel=info &
PIDS+=($!)
echo "[entrypoint] Beat started (PID ${PIDS[1]})"

# --- Uvicorn (foreground for healthcheck) ---
uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" &
PIDS+=($!)
echo "[entrypoint] Web started (PID ${PIDS[2]})"

# Wait for any child to exit — then tear down all
wait -n
echo "[entrypoint] A process exited, shutting down all..."
cleanup
