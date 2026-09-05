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
| Address | the VPS IP address is enough; a domain is optional, see below |
| Local | `ssh`, `scp`, and a GitHub account that can add repository secrets |

### Two modes

This deployment runs in one of two modes, and the mode is one line in
`/opt/proxy/.env`. Nothing else in the repository differs between them.

| | IP mode | Domain mode |
|---|---|---|
| `JOURNEYMESH_DOMAIN` | `http://51.79.166.97` | `journeymesh.example.com` |
| `PUBLIC_URL` in GitHub | `http://51.79.166.97` | `https://journeymesh.example.com` |
| Scheme | plain HTTP | HTTPS, redirected from port 80 |
| Certificate | none - Let's Encrypt does not issue for a bare IP | issued and renewed automatically |
| HSTS | off, deliberately | on: uncomment it in the Caddyfile |
| Applications this VPS can serve | one | three, one per name |

IP mode is the right configuration when you have no domain: it is not degraded
HTTPS, it is the only thing a bare address supports. Start here, and switch
when you buy a name.

**In domain mode the name must resolve before the proxy first starts.** Caddy
asks Let's Encrypt for a certificate on start-up and Let's Encrypt checks the
DNS, so a wrong record costs a rate limit rather than a retry.

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

## 2. Point the domain at it - domain mode only

Skip this step entirely in IP mode. There is nothing to point.

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

It does **not** touch sshd on this run. Password authentication and root login
are disabled only when you ask for it, in a second run, after key login is
proven — see step 4. That order is deliberate: hardening a machine you cannot
yet log into by key locks you out of it.

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

Now, and only now, close the machine to passwords:

```bash
ssh root@<vps-ip> 'HARDEN_SSH=1 bash /tmp/bootstrap-vps.sh'
```

That second run sets `PasswordAuthentication no` and `PermitRootLogin no`,
validates the configuration with `sshd -t` before reloading, and refuses to do
any of it while the deploy user's `authorized_keys` is empty. Keep the session
you are in open and prove key login from a second terminal before closing it.

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
nano .env          # JOURNEYMESH_DOMAIN - the whole mode decision
docker compose config --quiet && echo "compose file is valid"
docker compose up -d
docker compose logs -f caddy
```

`JOURNEYMESH_DOMAIN` is the only line that matters here:

```ini
JOURNEYMESH_DOMAIN=http://51.79.166.97          # IP mode, plain HTTP
# JOURNEYMESH_DOMAIN=journeymesh.example.com    # domain mode, automatic HTTPS
```

In IP mode Caddy binds port 80 and says nothing about certificates, which is
correct. In domain mode it reports obtaining one. Either way, until
JourneyMesh is deployed the address returns a 502: the proxy is up and the
application is not there yet.

After any change to `.env` or the Caddyfile, reload without dropping
connections:

```bash
docker compose up -d          # picks up a changed .env
docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile
```

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

Note what is **not** here: the public address and the ACME email belong to
`/opt/proxy/.env`, because the scheme and TLS belong to the VPS, not to any
application on it.

With no API keys at all the system still runs end to end. The agents produce
structured results and every unconfirmed price is labelled an **ESTIMATE**.

---

## 7. Configure GitHub

Create the environment first, because everything below lives inside it.

**Settings → Environments → New environment → `production`.** Set its
deployment branches to **Selected branches → `main`**, and add yourself as a
required reviewer if you want a second confirmation before every release.

The release job declares `environment: production`, so these belong to that
environment and not to the repository. That scoping is the point: a repository
secret is readable by every workflow in a public repository's trusted context,
while an environment secret is reachable only from a job that names the
environment and passes its branch rule.

**Environment secrets:**

| Secret | Value |
|---|---|
| `OVH_SSH_PRIVATE_KEY` | the **private** half: `cat ~/.ssh/journeymesh_deploy`, both `-----BEGIN/END-----` lines included |
| `OVH_KNOWN_HOSTS` | `ssh-keyscan -p 22 <vps-ip>` |

`OVH_KNOWN_HOSTS` is not optional paranoia. Without a pinned host key the
workflow would accept whatever answers on that address, and a redirected DNS
record would collect the deploy key.

**Environment variables** (none of these is sensitive):

| Variable | Value |
|---|---|
| `OVH_HOST` | `<vps-ip>` |
| `OVH_USER` | `deploy` |
| `OVH_SSH_PORT` | `22` |
| `OVH_APP_DIR` | `/opt/journeymesh` |
| `PUBLIC_URL` | `http://51.79.166.97` in IP mode, `https://journeymesh.example.com` in domain mode |

The rest of the GitHub side - branch protection on `main`, secret scanning,
push protection, and the Actions permissions - is in
[HARDENING.md](HARDENING.md). On a public repository, push protection is the
one to enable first: it stops a recognised credential at `git push`, before it
is public and has to be rotated.

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
9. **Verifies** `$PUBLIC_URL/api/v1/health` from the internet, whatever scheme
   that variable names, and
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

### Moving from the IP to a domain

Everything below happens in `/opt/proxy`. The application stack, the images
and the database are not involved, and JourneyMesh keeps serving throughout.

1. Point an A record (and AAAA, if you have IPv6) at the VPS, and confirm it
   with `dig +short journeymesh.example.com`.
2. Edit `/opt/proxy/.env`: `JOURNEYMESH_DOMAIN=journeymesh.example.com`, with
   no scheme. That single change turns on automatic HTTPS.
3. Optional: set `ACME_EMAIL` and uncomment the `email` line in the Caddyfile
   for Let's Encrypt expiry warnings.
4. Optional but recommended once HTTPS works: uncomment the
   `Strict-Transport-Security` line in the `(common)` snippet. Do it after you
   have confirmed the certificate, never before — the header pins the name to
   HTTPS in every browser that sees it, for two years.
5. Apply it:

```bash
cd /opt/proxy
docker compose up -d
docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile
docker compose logs -f caddy       # watch the certificate being issued
```

6. Change `PUBLIC_URL` in the GitHub `production` environment to
   `https://journeymesh.example.com`, so the release verification checks the
   address people actually use.

The backend needs no change: it sends HSTS of its own accord once requests
arrive with `X-Forwarded-Proto: https`, which Caddy sets as soon as TLS is on.

### Renewing certificates

You do not. In domain mode Caddy renews about 30 days before expiry and keeps
the certificates in the `caddy-data` volume, which belongs to `/opt/proxy` and
is untouched by any application release. In IP mode there is no certificate to
renew.

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
| `<public url>/health` returns HTML | Expected. That path is the container probe. The public API health path is `/api/v1/health`. |
| The browser warns "Not secure" | Expected in IP mode. There is no certificate for a bare IP; buy a domain and switch to domain mode. |
| A second application on the same IP answers with the first one | Expected. Caddy routes by Host header and a bare IP is one host. IP mode serves one application; the others need names. |
| Migrations fail | `jm run --rm migrate` by hand to see the Alembic error in full. |
| The disk fills up | `docker system prune -af` and check `backups/` — retention is 14 days. |
| Everything is slow | Raise `WEB_CONCURRENCY` only if free memory allows. The default is 1 because this machine is meant to hold three applications. |

---

## What is where

| Path | What it is |
|---|---|
| `deploy/proxy/docker-compose.yml` | the shared reverse proxy; the only stack with host ports |
| `deploy/proxy/Caddyfile` | one routing block per site; HTTP or HTTPS decided by the address in `/opt/proxy/.env` |
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
