#!/usr/bin/env bash
# =============================================================================
# Travel Crew AI - uploaded media backup on the OVHcloud VPS
#
#   /opt/journeymesh/backup_media.sh
#
# Writes a compressed tar of the media volume into /opt/journeymesh/backups and
# deletes archives older than RETENTION_DAYS. Nothing else on the VPS deletes
# anything.
#
# This is a SEPARATE backup from the database, on purpose. A database restore
# should not require a media restore to succeed, and the two have very
# different sizes and change rates: the database is small and changes
# constantly, the media is large and mostly append-only.
#
# The archive is read out of the running container, so this script does not
# need to know where Docker keeps the volume on disk.
#
# Run it nightly from the deploy user's crontab, after the database backup:
#   crontab -e
#   30 3 * * * /opt/journeymesh/backup_media.sh >> /opt/journeymesh/backups/backup.log 2>&1
#
# A backup that has never been restored is a hope, not a backup. See the
# restore command at the bottom of this file, and run it once.
# =============================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/journeymesh}"
BACKUP_DIR="${BACKUP_DIR:-${APP_DIR}/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
COMPOSE_FILE="${COMPOSE_FILE:-${APP_DIR}/docker-compose.prod.yml}"
MEDIA_PATH="${MEDIA_PATH:-/srv/journeymesh/storage/media}"

cd "$APP_DIR"

# shellcheck disable=SC1091
set -a; . "${APP_DIR}/.env"; set +a

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="${BACKUP_DIR}/media-${STAMP}.tar.gz"

# The image tags live in a second file the deploy workflow rewrites. Compose
# needs both to render this file, even for `exec`.
ENV_ARGS=(--env-file "${APP_DIR}/.env")
[ -f "${APP_DIR}/.env.images" ] && ENV_ARGS+=(--env-file "${APP_DIR}/.env.images")

compose() { docker compose -f "$COMPOSE_FILE" "${ENV_ARGS[@]}" "$@"; }

mkdir -p "$BACKUP_DIR"

echo "[backup-media] ${STAMP} archiving ${MEDIA_PATH}"

# Nothing to archive is a valid state on a fresh deployment, and must not be
# reported as a failure by cron every night until someone uploads a picture.
if ! compose exec -T backend sh -c "[ -d '${MEDIA_PATH}' ]"; then
  echo "[backup-media] ${MEDIA_PATH} does not exist yet; nothing to do"
  exit 0
fi

FILE_COUNT="$(compose exec -T backend sh -c "find '${MEDIA_PATH}' -type f | wc -l" | tr -d '[:space:]')"
if [ "${FILE_COUNT:-0}" -eq 0 ]; then
  echo "[backup-media] no uploads yet; nothing to do"
  exit 0
fi

# Write to a temporary name and rename on success, so a half-written archive is
# never mistaken for a usable backup.
compose exec -T backend tar -C "$(dirname "$MEDIA_PATH")" -cf - "$(basename "$MEDIA_PATH")" \
  | gzip -9 > "${TARGET}.partial"
mv "${TARGET}.partial" "$TARGET"

echo "[backup-media] wrote $(du -h "$TARGET" | cut -f1) (${FILE_COUNT} files) to ${TARGET}"

find "$BACKUP_DIR" -name 'media-*.tar.gz' -mtime "+${RETENTION_DAYS}" -print -delete
echo "[backup-media] done; kept the last ${RETENTION_DAYS} days"

# Verify an archive without touching the live volume:
#
#   tar -tzf backups/media-<stamp>.tar.gz | head
#
# Restore into the running container:
#
#   gunzip -c backups/media-<stamp>.tar.gz | docker compose -f docker-compose.prod.yml \
#     --env-file .env --env-file .env.images exec -T backend tar -C /srv/journeymesh/storage -xf -
#
# That overwrites files of the same name and leaves newer uploads in place. To
# restore exactly what was in the archive and nothing else, empty the directory
# first - which is destructive, so take a fresh backup before you do it.
