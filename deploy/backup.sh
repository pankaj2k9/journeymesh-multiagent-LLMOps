#!/usr/bin/env bash
# =============================================================================
# JourneyMesh - PostgreSQL backup on the OVHcloud VPS
#
#   /opt/journeymesh/backup.sh
#
# Writes a compressed pg_dump into /opt/journeymesh/backups and deletes dumps
# older than RETENTION_DAYS. Nothing else on the VPS deletes anything.
#
# The dump runs INSIDE the database container, so it does not need - and does
# not have - a host port on 5432. `-T` disables TTY allocation, which is what
# makes this work unattended from cron.
#
# Run it nightly from the deploy user's crontab:
#   crontab -e
#   15 3 * * * /opt/journeymesh/backup.sh >> /opt/journeymesh/backups/backup.log 2>&1
#
# A backup that has never been restored is a hope, not a backup. See the
# restore command at the bottom of this file, and run it once.
# =============================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/journeymesh}"
BACKUP_DIR="${BACKUP_DIR:-${APP_DIR}/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
COMPOSE_FILE="${COMPOSE_FILE:-${APP_DIR}/docker-compose.prod.yml}"

cd "$APP_DIR"

# shellcheck disable=SC1091
set -a; . "${APP_DIR}/.env"; set +a

USER_NAME="${POSTGRES_USER:-journeymesh}"
DB_NAME="${POSTGRES_DB:-journeymesh}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="${BACKUP_DIR}/${DB_NAME}-${STAMP}.sql.gz"

# The image tags live in a second file the deploy workflow rewrites. Compose
# needs both to render this file, even for `exec`.
ENV_ARGS=(--env-file "${APP_DIR}/.env")
[ -f "${APP_DIR}/.env.images" ] && ENV_ARGS+=(--env-file "${APP_DIR}/.env.images")

compose() { docker compose -f "$COMPOSE_FILE" "${ENV_ARGS[@]}" "$@"; }

mkdir -p "$BACKUP_DIR"

echo "[backup] ${STAMP} dumping ${DB_NAME}"
# Dump to a temporary name and rename on success, so a half-written file is
# never mistaken for a usable backup.
compose exec -T db pg_dump -U "$USER_NAME" -d "$DB_NAME" --no-owner --clean --if-exists \
  | gzip -9 > "${TARGET}.partial"
mv "${TARGET}.partial" "$TARGET"

echo "[backup] wrote $(du -h "$TARGET" | cut -f1) to ${TARGET}"

find "$BACKUP_DIR" -name "${DB_NAME}-*.sql.gz" -mtime "+${RETENTION_DAYS}" -print -delete
echo "[backup] done; kept the last ${RETENTION_DAYS} days"

# Restore, into a scratch database first so you know the file works:
#
#   docker compose -f docker-compose.prod.yml --env-file .env --env-file .env.images \
#     exec -T db createdb -U journeymesh journeymesh_restore_test
#   gunzip -c backups/journeymesh-<stamp>.sql.gz | docker compose -f docker-compose.prod.yml \
#     --env-file .env --env-file .env.images exec -T db psql -U journeymesh -d journeymesh_restore_test
#
# Restoring over the live database is the same command with -d journeymesh,
# and the dump was taken with --clean --if-exists, so it drops what it
# replaces. Stop the backend first.
