#!/usr/bin/env bash
# JourneyMesh backend container entrypoint.
#
#   serve     wait for the database (when configured), migrate, then run the API
#   migrate   apply Alembic migrations and exit
#   <other>   executed verbatim, so `docker compose run backend pytest -q` works
set -euo pipefail

PORT="${PORT:-8000}"
WORKERS="${WEB_CONCURRENCY:-2}"
RUN_MIGRATIONS="${RUN_MIGRATIONS:-true}"
DB_WAIT_SECONDS="${DB_WAIT_SECONDS:-60}"

log() { printf '[entrypoint] %s\n' "$*"; }

wait_for_database() {
  if [ -z "${DATABASE_URL:-}" ]; then
    log "DATABASE_URL is not set - the API will use its ephemeral in-memory database."
    return 1
  fi

  if ! python -c 'import psycopg' >/dev/null 2>&1; then
    log "the psycopg driver is not installed - cannot reach PostgreSQL."
    return 1
  fi

  log "waiting for the database (up to ${DB_WAIT_SECONDS}s)..."
  local waited=0
  until python - <<'PYEOF' 2>/dev/null
import os
import sys

import psycopg

url = os.environ["DATABASE_URL"]
for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgres://"):
    if url.startswith(prefix):
        url = "postgresql://" + url.split("://", 1)[1]
        break

try:
    with psycopg.connect(url, connect_timeout=3):
        pass
except Exception:
    sys.exit(1)
PYEOF
  do
    waited=$((waited + 2))
    if [ "$waited" -ge "$DB_WAIT_SECONDS" ]; then
      log "the database did not become reachable in ${DB_WAIT_SECONDS}s"
      return 1
    fi
    log "  still waiting (${waited}s)"
    sleep 2
  done

  log "database is reachable"
  return 0
}

run_migrations() {
  log "applying Alembic migrations"
  alembic upgrade head
  log "migrations are up to date"
}

case "${1:-serve}" in
  serve)
    if wait_for_database && [ "$RUN_MIGRATIONS" = "true" ]; then
      run_migrations
    fi
    log "starting the API on port ${PORT}"
    if [ "${RELOAD:-false}" = "true" ]; then
      exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload --no-server-header
    fi
    exec uvicorn app.main:app \
      --host 0.0.0.0 \
      --port "$PORT" \
      --workers "$WORKERS" \
      --no-server-header \
      --proxy-headers \
      --forwarded-allow-ips '*'
    ;;
  migrate)
    wait_for_database || { log "cannot migrate without a reachable database"; exit 1; }
    run_migrations
    ;;
  *)
    exec "$@"
    ;;
esac
