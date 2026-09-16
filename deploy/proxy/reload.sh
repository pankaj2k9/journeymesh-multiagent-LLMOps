#!/usr/bin/env bash
# =============================================================================
# Shared reverse proxy - validate, then reload Caddy without downtime
#
#   /opt/proxy/reload.sh
#
# Run it after adding, editing or removing a file in /opt/proxy/sites/.
#
#   1. validate  the full configuration - the main Caddyfile plus every
#                sites/*.caddy - is parsed and provisioned by Caddy itself.
#                A mistake stops here and the running configuration is
#                untouched, so one bad site file cannot take TLS down for
#                every application on the VPS.
#   2. check     every reverse_proxy upstream resolves on the `proxy` network.
#                A warning, not a failure: an application may be deployed
#                after its site file is added, and Caddy answers 502 for it
#                until then without affecting the other sites.
#   3. reload    graceful: existing connections are not dropped, and Caddy
#                keeps the old configuration if the new one fails to load.
#
# It never restarts or recreates the container, and never touches the
# certificate volume or the network.
# =============================================================================
set -euo pipefail

PROXY_DIR="${PROXY_DIR:-$(cd "$(dirname "$0")" && pwd)}"
CONFIG=/etc/caddy/Caddyfile

log() { printf '[proxy] %s\n' "$*"; }

cd "$PROXY_DIR"

caddy_exec() { docker compose exec -T caddy "$@"; }

if [ -z "$(docker compose ps --status running --quiet caddy 2>/dev/null)" ]; then
  echo "[proxy] the shared Caddy is not running. Start it first:" >&2
  echo "[proxy]   cd ${PROXY_DIR} && docker compose up -d" >&2
  exit 1
fi

log "site files:"
ls -1 sites/*.caddy 2>/dev/null | sed 's/^/[proxy]   /' || log "  (none)"

log "validating ${CONFIG} and every sites/*.caddy"
caddy_exec caddy validate --config "$CONFIG" --adapter caddyfile

log "checking upstreams resolve on the proxy network"
upstreams=$(grep -hoE '^[[:space:]]*reverse_proxy[[:space:]]+[A-Za-z0-9._-]+:[0-9]+' sites/*.caddy 2>/dev/null \
  | awk '{print $2}' | cut -d: -f1 | sort -u || true)
for host in $upstreams; do
  # getent uses the container resolver (Docker DNS); busybox nslookup exits
  # non-zero there even for names that resolve.
  if caddy_exec getent hosts "$host" >/dev/null 2>&1; then
    log "  ok       ${host}"
  else
    log "  WARNING  ${host} does not resolve - is its stack running and joined to 'proxy'?"
  fi
done

log "reloading gracefully"
caddy_exec caddy reload --config "$CONFIG" --adapter caddyfile

log "reloaded. Verify each site, e.g.:"
log "  curl -sSI https://travelcrewai.com | head -n 1"
