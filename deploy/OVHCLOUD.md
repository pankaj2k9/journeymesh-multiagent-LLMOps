# Deploying JourneyMesh to an OVHcloud VPS

Every journey, intelligently connected — this one starts with a bare Debian box.

Production is **one OVHcloud VPS** running two independent Compose projects: a
shared reverse proxy that owns ports 80 and 443 for the whole machine, and the
JourneyMesh application stack, which owns no host port at all.

That split is the important part. This VPS is sized to host about three small
SaaS applications, and only one container on a machine can bind port 443. So
TLS is a property of the *server*, not of any application on it.

```
Internet
   │  :80  :443
   ▼
┌──────────────────────── OVHcloud VPS ────────────────────────┐
│                                                              │
│  /opt/proxy          shared-caddy   ← the only public ports  │
│                           │                                  │
│                    ┌──────┴───────── proxy network ───────┐  │
│                    │                  │                │  │  │
│  /opt/journeymesh  ▼                  ▼                ▼  │  │
│    journeymesh-frontend      (saas2-frontend)  (saas3-…)  │  │
│         │  nginx, /api                                    │  │
│         ▼  ─── journeymesh_default network ───            │  │
│    journeymesh-backend  ──▶  journeymesh-db               │  │
│                                                           │  │
└──────────────────────────────────────────────────────────────┘
```

Two networks, and a container is on the second only if something outside its
own stack must reach it:

| Container | `journeymesh_default` | `proxy` | Host port |
|---|---|---|---|
| shared-caddy | no | yes | 80, 443, 443/udp |
| journeymesh-frontend | yes | yes, as `journeymesh-frontend` | none |
| journeymesh-backend | yes | **no** | none |
| journeymesh-db | yes | **never** | none |

PostgreSQL publishes nothing at all — not even on loopback. Administrative
access goes through the container.

---

## What you need

| | |
|---|---|
| VPS | OVHcloud VPS, 2 vCPU / 4 GB RAM / 40 GB NVMe |
| Image | Debian 12 or Ubuntu 24.04 LTS |
| Domain | an A record (and AAAA if the VPS has IPv6) pointing at the VPS |
| Local | `ssh`, `scp`, and a GitHub account that can add repository secrets |

The domain must resolve **before** the proxy first starts. Caddy asks Let's
Encrypt for a certificate on start-up, and Let's Encrypt checks the DNS.

---

## 1. Order and reach the VPS

Create the VPS in the OVHcloud control panel, choosing your SSH key at order
time. OVHcloud emails the root credentials and the IP address.

```bash
ssh root@<vps-ip>
```

If OVHcloud gave you a `ubuntu` or `debian` user instead of root, use
`sudo -i` once you are in.

---

## 2. Point the domain at it

| Type | Name | Value |
|---|---|---|
| A | `journeymesh` (or `@`) | `<vps-ipv4>` |
| AAAA | same | `<vps-ipv6>` if you have one |

Check it before going further. A wrong record costs you a Let's Encrypt rate
limit, not just a retry:

```bash
dig +short journeymesh.example.com
```

---

## 3. Bootstrap the VPS

`deploy/bootstrap-vps.sh` installs Docker, creates the unprivileged `deploy`
user, **creates the shared `proxy` network**, prepares `/opt/proxy` and
`/opt/journeymesh`, opens 22/80/443 and closes everything else. Run it once, as
root. It is safe to run again.

```bash
scp deploy/bootstrap-vps.sh root@<vps-ip>:/tmp/
ssh root@<vps-ip> 'bash /tmp/bootstrap-vps.sh'
```

It turns off SSH password authentication at the end. **Add your key to the
deploy user before you log out**, or you lock yourself out.

If you ever rebuild the machine by hand, the one command that must not be
forgotten is:

```bash
docker network create proxy
```

Every Compose file declares that network `external: true`, so nothing creates
it implicitly and nothing deletes it by accident.

---

## 4. Create the deploy key

This is the key GitHub Actions uses. It is separate from your personal key so
you can revoke one without losing the other, and it has no passphrase because
no human types it.

```bash
ssh-keygen -t ed25519 -C "journeymesh github actions" -f ~/.ssh/journeymesh_deploy -N ""
ssh-copy-id -i ~/.ssh/journeymesh_deploy.pub deploy@<vps-ip>
ssh -i ~/.ssh/journeymesh_deploy deploy@<vps-ip> 'docker ps'
```

That last command must succeed and print an empty container table. If it asks
for a password, the key did not land.

---

## 5. Start the shared reverse proxy

This is done **once for the VPS**, not once per release. Nothing in the
JourneyMesh deployment path ever touches it again — a release must not restart
TLS for applications that have nothing to do with it.

```bash
scp deploy/proxy/docker-compose.yml deploy/proxy/Caddyfile deploy@<vps-ip>:/opt/proxy/
scp deploy/proxy/.env.example deploy@<vps-ip>:/opt/proxy/.env
ssh deploy@<vps-ip>
```

On the VPS:

```bash
cd /opt/proxy
chmod 600 .env
nano .env          # ACME_EMAIL and JOURNEYMESH_DOMAIN
docker compose up -d
docker compose logs -f caddy
```

Caddy will report obtaining a certificate. Until JourneyMesh is deployed the
domain returns a 502, which is correct: the proxy is up and the application is
not there yet.

---

## 6. Put the JourneyMesh environment on the VPS

The environment file is the one thing the deployment does **not** ship from the
repository. It holds the production secrets, it lives only on the VPS, and the
deploy workflow never overwrites it.

```bash
scp deploy/docker-compose.prod.yml deploy/deploy.sh deploy/backup.sh \
  deploy@<vps-ip>:/opt/journeymesh/
scp deploy/.env.prod.example deploy@<vps-ip>:/opt/journeymesh/.env
```

On the VPS:

```bash
cd /opt/journeymesh
chmod 600 .env
chmod +x deploy.sh backup.sh
openssl rand -base64 32 | tr -d '/+=' | cut -c1-32   # the database password
nano .env
```

Fill in at least this. Everything else has a working default:

```ini
POSTGRES_PASSWORD=<the string you just generated>
GROQ_API_KEY=<optional - blank means deterministic mode>
```

Note what is **not** here: the domain and the ACME address belong to
`/opt/proxy/.env`, because TLS belongs to the VPS.

With no API keys at all the system still runs end to end. The agents produce
structured results and every unconfirmed price is labelled an **ESTIMATE**.

---

## 7. Configure GitHub

**Settings → Secrets and variables → Actions → Secrets:**

| Secret | Value |
|---|---|
| `OVH_SSH_PRIVATE_KEY` | the **private** half: `cat ~/.ssh/journeymesh_deploy` |
| `OVH_KNOWN_HOSTS` | `ssh-keyscan -p 22 <vps-ip>` |

`OVH_KNOWN_HOSTS` is not optional paranoia. Without a pinned host key the
workflow would accept whatever answers on that address, and a redirected DNS
record would collect the deploy key.

**Variables:**

| Variable | Value |
|---|---|
| `OVH_HOST` | `<vps-ip>` |
| `OVH_USER` | `deploy` |
| `OVH_SSH_PORT` | `22` |
| `OVH_APP_DIR` | `/opt/journeymesh` |
| `PUBLIC_URL` | `https://journeymesh.example.com` |

**Settings → Environments → New environment → `production`.** Add yourself as a
required reviewer if you want a second confirmation before every release.

---

## 8. Release

```
push to main  →  CI  →  (the production environment gate)  →  release
```

CI runs on every push and every pull request. It releases nothing. To release:

1. **Actions → Deploy to production → Run workflow**
2. Scope: `backend-and-frontend`
3. Confirm: type `deploy`

The workflow then:

1. **Gates** — refuses a run off `main`, an unconfirmed run, or missing credentials.
2. **Builds** both images and pushes them to GHCR tagged with the commit SHA.
3. **Ships** the Compose file and the operator scripts. Not `/opt/proxy`.
4. **Checks** the shared `proxy` network exists, before pulling anything.
5. **Pins** the SHA tags in `/opt/journeymesh/.env.images`.
6. **Pulls** those exact tags, using a registry token valid only for this job.
7. **Migrates** — `alembic upgrade head` in a one-shot container. A failure
   stops the release here, with the old containers still serving.
8. **Starts** the new containers and waits for every health check.
9. **Verifies** `https://<your-domain>/api/v1/health` from the internet, and
   that the interface itself is served. Not `/health`: nginx proxies only
   `/api/`, so the container probe path falls through to the SPA and would
   answer 200 with HTML even for a broken backend.
10. **Logs out** of the registry and prunes images older than a week.

The same sequence by hand, if Actions is unavailable:

```bash
ssh deploy@<vps-ip>
cd /opt/journeymesh && ./deploy.sh
```

---

## Operating it

Everything below runs as `deploy@<vps-ip>`. The environment files are long, so
define these once:

```bash
alias jm='docker compose -f /opt/journeymesh/docker-compose.prod.yml \
  --env-file /opt/journeymesh/.env --env-file /opt/journeymesh/.env.images'
alias px='docker compose -f /opt/proxy/docker-compose.yml --env-file /opt/proxy/.env'
```

| Task | Command |
|---|---|
| What is running | `jm ps` |
| Follow the logs | `jm logs -f --tail 100` |
| One service | `jm logs -f backend` / `jm logs -f frontend` |
| Restart the API | `jm restart backend` |
| Stop JourneyMesh | `jm down` — the proxy and the other apps keep running |
| Start JourneyMesh | `jm up -d` |
| A shell in the API | `jm exec backend bash` |
| psql | `jm exec db psql -U journeymesh -d journeymesh` |
| Proxy status | `px ps` and `px logs -f caddy` |
| Reload the Caddyfile | `px exec caddy caddy reload --config /etc/caddy/Caddyfile` |
| Disk usage | `docker system df` |

> **`docker compose down -v` deletes the `postgres-data` volume, which is the
> production database.** Nothing in the deployment path runs it, and neither
> should you. `down` on its own is safe; the `-v` is what destroys data.

### Adding the second and third SaaS

Nothing about JourneyMesh changes.

1. Give the new application's frontend an alias on the `proxy` network, say
   `saas2-frontend`, and keep everything else on its own default network.
2. Add `SAAS2_DOMAIN` to `/opt/proxy/.env`.
3. Uncomment the SaaS 2 block in `/opt/proxy/Caddyfile`.
4. `px exec caddy caddy reload --config /etc/caddy/Caddyfile`.

No restart, no downtime for anything already running.

### Backups

`deploy/backup.sh` is shipped on every release and runs `pg_dump` **inside** the
database container, so it needs no host port. Schedule it once:

```bash
crontab -e
# nightly at 03:15 UTC
15 3 * * * /opt/journeymesh/backup.sh >> /opt/journeymesh/backups/backup.log 2>&1
```

It keeps 14 days of compressed dumps in `/opt/journeymesh/backups`. Copy them
off the VPS — a backup on the machine it protects is not a backup. OVHcloud's
snapshots cover the whole disk and complement this: a snapshot restores the
machine, a dump restores one table.

**Restore** into a scratch database at least once, so you know the file works:

```bash
jm exec -T db createdb -U journeymesh journeymesh_restore_test
gunzip -c /opt/journeymesh/backups/journeymesh-<stamp>.sql.gz \
  | jm exec -T db psql -U journeymesh -d journeymesh_restore_test
```

### Rolling back

Every release is an immutable image tagged with its commit SHA, so a rollback
is a tag change and a restart — no rebuild, no git revert:

```bash
cd /opt/journeymesh
nano .env.images          # set both tags back to the previous commit SHA
jm pull && jm up -d
```

Migrations do not roll back with the image. If the bad release added a column,
the previous image ignores it; if it dropped one, restore from a dump.

### Renewing certificates

You do not. Caddy renews about 30 days before expiry and keeps the certificates
in the `caddy-data` volume, which belongs to `/opt/proxy` and is untouched by
any application release.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| The workflow fails at "The shared proxy network exists" | The VPS was never bootstrapped, or the network was removed. `docker network create proxy`, then `cd /opt/proxy && docker compose up -d`. |
| The workflow fails at "Configure SSH" | `OVH_KNOWN_HOSTS` does not match the host, or the public key is not in the deploy user's `authorized_keys`. Re-run `ssh-keyscan`. |
| The workflow fails at "Pull the images" | The `deploy` user is not in the `docker` group. `sudo usermod -aG docker deploy`, then log out and back in. |
| Caddy loops on certificates | DNS does not resolve to this VPS yet, or port 80 is closed. `dig +short <domain>` and `sudo ufw status`. |
| `502 Bad Gateway` from the domain | JourneyMesh is down, or its frontend is not on the `proxy` network. `jm ps`, then `docker network inspect proxy`. |
| `504` or a Caddy DNS error naming `journeymesh-frontend` | The alias and the Caddyfile disagree. They must be the same string. |
| `/api/v1/health` says `ephemeral_sqlite` | `POSTGRES_PASSWORD` is empty in `/opt/journeymesh/.env`. |
| `https://<domain>/health` returns HTML | Expected. That path is the container probe. The public API health path is `/api/v1/health`. |
| Migrations fail | `jm run --rm migrate` by hand to see the Alembic error in full. |
| The disk fills up | `docker system prune -af` and check `backups/` — retention is 14 days. |
| Everything is slow | Raise `WEB_CONCURRENCY` only if free memory allows. The default is 1 because this machine is meant to hold three applications. |

---

## What is where

| Path | What it is |
|---|---|
| `deploy/proxy/docker-compose.yml` | the shared reverse proxy; the only stack with host ports |
| `deploy/proxy/Caddyfile` | TLS and one routing block per domain |
| `deploy/proxy/.env.example` | template for `/opt/proxy/.env` |
| `deploy/docker-compose.prod.yml` | the JourneyMesh stack; pulls, never builds, publishes nothing |
| `deploy/deploy.sh` | pull, migrate, up, verify — the release, by hand |
| `deploy/bootstrap-vps.sh` | one-time VPS preparation |
| `deploy/backup.sh` | nightly `pg_dump` with retention |
| `deploy/.env.prod.example` | template for `/opt/journeymesh/.env` |
| `/opt/journeymesh/.env` | the real secrets, on the VPS only, `chmod 600` |
| `/opt/journeymesh/.env.images` | the two image tags, rewritten by each release |
| `.github/workflows/ci.yml` | the quality gate; releases nothing |
| `.github/workflows/deploy-production.yml` | the release |
| `deploy/HARDENING.md` | the manual GitHub and VPS hardening checklist |
