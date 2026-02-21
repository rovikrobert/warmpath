#!/usr/bin/env bash
# Entrypoint for Railway multi-service deployment.
# SERVICE_ROLE env var controls which process starts (one per service):
#   web    — uvicorn only (default, binds $PORT)
#   worker — celery worker only
#   beat   — celery beat only
#   scan   — run agent team scans, then exit (Railway Cron)
#
# Each role uses `exec` to replace the shell — the target process
# becomes PID 1 and receives SIGTERM/SIGINT directly from the runtime.
# No background processes, no zombies.

set -euo pipefail

ROLE="${SERVICE_ROLE:-web}"
CONCURRENCY="${CELERY_CONCURRENCY:-2}"

# Handle SIGTERM/SIGINT during pre-exec setup (e.g. alembic migrations).
# Once `exec` runs, this trap is replaced by the target process's own handler.
trap 'echo "[entrypoint] Caught signal during setup, exiting..."; exit 1' SIGTERM SIGINT

echo "[entrypoint] SERVICE_ROLE=$ROLE, PID=$$"

# Run Alembic migrations only for web service (before uvicorn starts).
# Other services skip migrations to avoid race conditions on parallel deploys.
if [ "$ROLE" = "web" ]; then
    echo "[entrypoint] Running Alembic migrations..."
    alembic upgrade head
    echo "[entrypoint] Alembic migrations complete"
fi

case "$ROLE" in
    web)
        echo "[entrypoint] Starting uvicorn (port=${PORT:-8000})"
        exec uvicorn app.main:app \
            --host 0.0.0.0 \
            --port "${PORT:-8000}"
        ;;
    worker)
        echo "[entrypoint] Starting celery worker (concurrency=$CONCURRENCY)"
        exec celery -A app.celery_app:celery_app worker \
            --loglevel=info \
            --concurrency="$CONCURRENCY" \
            --pool=prefork \
            --without-heartbeat \
            --without-mingle \
            --without-gossip
        ;;
    beat)
        echo "[entrypoint] Starting celery beat"
        exec celery -A app.celery_app:celery_app beat \
            --loglevel=info
        ;;
    scan)
        echo "[entrypoint] Running agent scans"
        exec python3 scripts/run_agent_scans.py
        ;;
    *)
        echo "[entrypoint] Unknown SERVICE_ROLE: $ROLE (expected: web, worker, beat, scan)"
        exit 1
        ;;
esac
