#!/usr/bin/env bash
# =============================================================================
# JourneyMesh - deploy the current image tags on the OVHcloud VPS
#
#   /opt/journeymesh/deploy.sh
#
# The GitHub Actions workflow is the normal release path and runs exactly this
# sequence over SSH. This script exists so the same sequence can be run by hand
# when Actions is unavailable, and so the ordering lives in one reviewable
# place rather than only inside a workflow file.
#
#   pull  ->  migrate (must succeed)  ->  up -d  ->  wait for health
#
# It touches the shared reverse proxy in no way. /opt/proxy has its own
# lifecycle, on purpose: a JourneyMesh release must never restart TLS for the
# other applications on this VPS.
#
# It never runs `down`, and never passes -v. The postgres-data volume is the
# production database.
#
# Options:
#   BACKUP_BEFORE_MIGRATE=1   take a pg_dump before the migration runs. Off by
#                             default so an ordinary release stays fast; turn
#                             it on for any release carrying a schema change
#                             you cannot trivially undo.
#
# `set -euo pipefail` is what makes the ordering a guarantee rather than a
# hope: a failed migration exits here and never reaches `up -d`.
# =============================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/journeymesh}"
COMPOSE_FILE="${COMPOSE_FILE:-${APP_DIR}/docker-compose.prod.yml}"
PROXY_NETWORK="${PROXY_NETWORK:-proxy}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-300}"
BACKUP_BEFORE_MIGRATE="${BACKUP_BEFORE_MIGRATE:-0}"

log() { printf '[deploy] %s\n' "$*"; }

cd "$APP_DIR"

ENV_ARGS=(--env-file "${APP_DIR}/.env")
[ -f "${APP_DIR}/.env.images" ] && ENV_ARGS+=(--env-file "${APP_DIR}/.env.images")

compose() { docker compose -f "$COMPOSE_FILE" "${ENV_ARGS[@]}" "$@"; }

# --- preconditions -----------------------------------------------------------
if ! docker network inspect "$PROXY_NETWORK" >/dev/null 2>&1; then
  echo "[deploy] the '${PROXY_NETWORK}' network does not exist." >&2
  echo "[deploy] it is created once per VPS:  docker network create ${PROXY_NETWORK}" >&2
  echo "[deploy] then start the shared proxy:  cd /opt/proxy && docker compose up -d" >&2
  exit 1
fi

# Keep the tags we are replacing, so a rollback needs no archaeology. Only
# image references are copied here - never .env, which holds the secrets.
if [ -f "${APP_DIR}/.env.images" ]; then
  cp -f "${APP_DIR}/.env.images" "${APP_DIR}/.env.images.previous"
  log "previous release (kept in .env.images.previous):"
  grep -E '^(BACKEND|FRONTEND)_IMAGE=' "${APP_DIR}/.env.images.previous" || true
fi

log "image tags for this release:"
grep -E '^(BACKEND|FRONTEND)_IMAGE=' "${APP_DIR}/.env.images" 2>/dev/null || true

# --- pull --------------------------------------------------------------------
log "pulling images"
compose pull

# --- optional pre-migration backup -------------------------------------------
# A migration is the only irreversible step in a release. An image rollback
# does not undo a dropped column, so for a schema change that matters, take
# the dump first: BACKUP_BEFORE_MIGRATE=1 /opt/journeymesh/deploy.sh
if [ "${BACKUP_BEFORE_MIGRATE}" = "1" ]; then
  log "taking a database backup before migrating"
  "${APP_DIR}/backup.sh"
fi

# --- migrate -----------------------------------------------------------------
# A one-shot container that must exit 0. `run` enables the service's own
# profile, so no --profile flag is needed. `set -e` stops the release here on a
# failure, with the previous containers still serving.
log "applying database migrations"
compose run --rm migrate

# --- start -------------------------------------------------------------------
log "starting the new containers"
compose up -d --remove-orphans
compose ps

# --- verify ------------------------------------------------------------------
log "waiting for health (up to ${HEALTH_TIMEOUT}s)"
deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
while :; do
  unhealthy=""
  for name in journeymesh-db journeymesh-backend journeymesh-frontend; do
    state=$(docker inspect -f '{{.State.Health.Status}}' "$name" 2>/dev/null || echo missing)
    [ "$state" = "healthy" ] || unhealthy="${unhealthy} ${name}=${state}"
  done
  if [ -z "$unhealthy" ]; then
    log "all containers are healthy"
    break
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "[deploy] not healthy in time:${unhealthy}" >&2
    compose logs --tail 80
    exit 1
  fi
  log " waiting:${unhealthy}"
  sleep 10
done

# --- record ------------------------------------------------------------------
# Image references only. Nothing from .env is written here.
{
  echo "released_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "by=manual deploy.sh ($(id -un))"
  grep -E '^(BACKEND|FRONTEND)_IMAGE=' "${APP_DIR}/.env.images" 2>/dev/null || true
  echo "---"
} >> "${APP_DIR}/releases.log"

log "deployed. The shared proxy at /opt/proxy was not touched."
log "to roll back: restore .env.images.previous, then pull and up -d."
