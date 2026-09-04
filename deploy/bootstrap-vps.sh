#!/usr/bin/env bash
# =============================================================================
# JourneyMesh - one-time preparation of a fresh OVHcloud VPS
#
# Run it once, as root, on a clean Debian 12 or Ubuntu 22.04/24.04 VPS:
#
#   scp deploy/bootstrap-vps.sh root@<vps-ip>:/tmp/
#   ssh root@<vps-ip> 'bash /tmp/bootstrap-vps.sh'
#
# It installs Docker, creates the unprivileged `deploy` user the GitHub Actions
# workflow logs in as, creates the shared `proxy` network, prepares /opt/proxy
# and /opt/journeymesh, opens 22/80/443 and closes everything else. It does not
# install any application: the deploy workflow does that.
#
# This VPS is designed to host several small SaaS applications. Exactly one
# container - the shared Caddy in /opt/proxy - ever owns a public port.
#
# It is safe to run twice - every step checks before it acts.
# =============================================================================
set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-deploy}"
APP_DIR="${APP_DIR:-/opt/journeymesh}"
PROXY_DIR="${PROXY_DIR:-/opt/proxy}"
PROXY_NETWORK="${PROXY_NETWORK:-proxy}"
SSH_PORT="${SSH_PORT:-22}"

log() { printf '\n[bootstrap] %s\n' "$*"; }

if [ "$(id -u)" -ne 0 ]; then
  echo "run this as root" >&2
  exit 1
fi

# ---- base packages ----------------------------------------------------------
log "installing base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg ufw fail2ban unattended-upgrades

# ---- Docker Engine + Compose plugin -----------------------------------------
if command -v docker >/dev/null 2>&1; then
  log "Docker is already installed: $(docker --version)"
else
  log "installing Docker Engine from Docker's own repository"
  install -m 0755 -d /etc/apt/keyrings
  . /etc/os-release
  curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker

# ---- log rotation for containers --------------------------------------------
# The Compose file sets per-service limits, but a daemon default protects
# anything started by hand as well. A VPS disk filled by logs is the single
# most common way a small deployment falls over.
if [ ! -f /etc/docker/daemon.json ]; then
  log "capping container log size"
  cat > /etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "5" }
}
JSON
  systemctl restart docker
fi

# ---- the deploy user --------------------------------------------------------
if id "$DEPLOY_USER" >/dev/null 2>&1; then
  log "user ${DEPLOY_USER} already exists"
else
  log "creating ${DEPLOY_USER}"
  adduser --disabled-password --gecos "JourneyMesh deploy" "$DEPLOY_USER"
fi
usermod -aG docker "$DEPLOY_USER"

install -d -m 0700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/${DEPLOY_USER}/.ssh"
touch "/home/${DEPLOY_USER}/.ssh/authorized_keys"
chmod 600 "/home/${DEPLOY_USER}/.ssh/authorized_keys"
chown "$DEPLOY_USER:$DEPLOY_USER" "/home/${DEPLOY_USER}/.ssh/authorized_keys"

# ---- the shared reverse-proxy network ---------------------------------------
# One network for the whole machine, created once and never owned by any
# application stack. Every Compose file declares it `external: true`, so
# bringing an application down leaves it - and the other applications - alone.
if docker network inspect "$PROXY_NETWORK" >/dev/null 2>&1; then
  log "the ${PROXY_NETWORK} network already exists"
else
  log "creating the shared ${PROXY_NETWORK} network"
  docker network create "$PROXY_NETWORK"
fi

# ---- the application directories --------------------------------------------
log "preparing ${PROXY_DIR} and ${APP_DIR}"
install -d -m 0750 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$PROXY_DIR"
install -d -m 0750 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$APP_DIR"
install -d -m 0750 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "${APP_DIR}/backups"

# ---- firewall ---------------------------------------------------------------
# Order matters: the SSH rule is added BEFORE `ufw enable`. Enabling a
# default-deny firewall first would drop the session you are typing into.
log "configuring the firewall"
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow "${SSH_PORT}/tcp" comment "ssh"
ufw allow 80/tcp comment "http - acme challenge and redirect"
ufw allow 443/tcp comment "https"
ufw allow 443/udp comment "https - http/3"
ufw --force enable

# ---- ssh hardening ----------------------------------------------------------
# NOT applied by default, and that is deliberate. Turning off password
# authentication before a working key is installed locks you out of a machine
# you may have no console access to. This script runs before any key exists.
#
# The safe sequence is:
#
#   1. finish this script
#   2. install your key and the deploy key (ssh-copy-id)
#   3. open a SECOND ssh session with the key and keep it open
#   4. in that session:  sudo HARDEN_SSH=1 bash /tmp/bootstrap-vps.sh
#   5. from a THIRD session, confirm key login still works
#   6. only then close the original session
#
# Step 3 is the one people skip. Keep the working session open: if the reload
# goes wrong, it is the only way back in.
if [ "${HARDEN_SSH:-0}" = "1" ]; then
  keyfile="/home/${DEPLOY_USER}/.ssh/authorized_keys"
  if [ ! -s "$keyfile" ]; then
    echo "[bootstrap] refusing to harden sshd: ${keyfile} is empty." >&2
    echo "[bootstrap] install the deploy key first, or you will be locked out." >&2
    exit 1
  fi

  log "hardening sshd (password auth off, root login off)"
  cat > /etc/ssh/sshd_config.d/99-journeymesh.conf <<'CONF'
PasswordAuthentication no
PermitRootLogin no
KbdInteractiveAuthentication no
CONF
  # Validate before reloading. A syntax error here would take sshd down.
  sshd -t
  systemctl reload ssh 2>/dev/null || systemctl reload sshd
  log "sshd hardened. Verify key login from another session NOW, before"
  log "closing the one you are in."
else
  log "sshd NOT hardened (default). Re-run with HARDEN_SSH=1 once key login"
  log "is confirmed working - see the notes in this script."
fi

systemctl enable --now fail2ban
dpkg-reconfigure -f noninteractive unattended-upgrades >/dev/null 2>&1 || true

cat <<DONE

[bootstrap] finished.

  Docker            $(docker --version)
  Compose           $(docker compose version --short 2>/dev/null || echo 'plugin missing')
  Deploy user       ${DEPLOY_USER}
  Shared proxy dir  ${PROXY_DIR}
  Application dir   ${APP_DIR}
  Shared network    ${PROXY_NETWORK}
  Firewall          22, 80, 443 open; everything else denied

Next, from your laptop:

  1. Add the deploy key's PUBLIC half to the VPS:
       ssh-copy-id -i ~/.ssh/journeymesh_deploy.pub ${DEPLOY_USER}@<vps-ip>

  2. Install the shared reverse proxy - once, for every application:
       scp deploy/proxy/docker-compose.yml deploy/proxy/Caddyfile \
         ${DEPLOY_USER}@<vps-ip>:${PROXY_DIR}/
       scp deploy/proxy/.env.example ${DEPLOY_USER}@<vps-ip>:${PROXY_DIR}/.env
       ssh ${DEPLOY_USER}@<vps-ip> "chmod 600 ${PROXY_DIR}/.env"
     Fill in ACME_EMAIL and JOURNEYMESH_DOMAIN, then:
       ssh ${DEPLOY_USER}@<vps-ip> "cd ${PROXY_DIR} && docker compose up -d"

  3. Install JourneyMesh:
       scp deploy/docker-compose.prod.yml deploy/deploy.sh deploy/backup.sh \
         ${DEPLOY_USER}@<vps-ip>:${APP_DIR}/
       scp deploy/.env.prod.example ${DEPLOY_USER}@<vps-ip>:${APP_DIR}/.env
       ssh ${DEPLOY_USER}@<vps-ip> "chmod 600 ${APP_DIR}/.env"

  4. Fill in ${APP_DIR}/.env on the VPS - POSTGRES_PASSWORD at minimum.

  5. Point the domain's A record at this VPS, then run the deploy workflow.

  6. LAST, once key login is confirmed from a second session:
       ssh ${DEPLOY_USER}@<vps-ip>   # keep this session open
       sudo HARDEN_SSH=1 bash /tmp/bootstrap-vps.sh
     Then confirm key login from a third session before closing anything.

DONE
