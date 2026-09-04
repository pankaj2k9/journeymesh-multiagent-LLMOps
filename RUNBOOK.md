# JourneyMesh — Runbook

Operational guide for the two environments this project has: a local
development stack on your machine, and production on an OVHcloud VPS.

It answers "it is broken, what now?". For what the system *is*, read
[README.md](README.md); for the manual GitHub and VPS hardening steps, read
[deploy/HARDENING.md](deploy/HARDENING.md).

> **This file is committed to a public repository.** Every value in it is a
> placeholder. Never paste a real key, password, token or private key here, and
> never into an issue or a workflow log.

---

## Contents

- [Local development](#local-development)
  - [Prerequisites](#prerequisites)
  - [First-time startup](#first-time-startup)
  - [URLs](#urls)
  - [Common commands](#common-commands)
  - [How hot reload works](#how-hot-reload-works)
  - [MCP: disabled, local, remote](#mcp-disabled-local-remote)
  - [Database access](#database-access)
  - [Migrations](#migrations)
  - [Resetting the development database](#resetting-the-development-database)
  - [Common development errors](#common-development-errors)
- [Production](#production)
  - [Architecture](#architecture)
  - [Directories](#directories)
  - [Status and health](#status-and-health)
  - [Logs](#logs)
  - [Restarting one service](#restarting-one-service)
  - [Deployment](#deployment)
  - [Manual deployment](#manual-deployment)
  - [Migration failure](#migration-failure)
  - [Rollback](#rollback)
  - [Backup](#backup)
  - [Restore](#restore)
  - [Disk, RAM and CPU](#disk-ram-and-cpu)
  - [Caddy and TLS](#caddy-and-tls)
  - [GHCR authentication](#ghcr-authentication)
  - [SSH and deployment access](#ssh-and-deployment-access)
  - [MCP in production](#mcp-in-production)
  - [External provider failures](#external-provider-failures)
  - [Incident checklist](#incident-checklist)
- [MCP and human-in-the-loop](#mcp-and-human-in-the-loop)
- [Security incidents](#security-incidents)

---

# Local development

## Prerequisites

| | |
|---|---|
| Docker | Engine 24+ with the Compose v2 plugin (`docker compose version`) |
| Make | GNU make, preinstalled on macOS and Linux |
| Git | any recent version |
| Environment | `.env.dev`, created for you on first run |

Nothing else. No Python virtualenv, no Node install, no local PostgreSQL. Every
process runs in a container.

## First-time startup

```bash
cp .env.dev.example .env.dev
make dev-local
```

`make dev-local` creates `.env.dev` for you if you skip the first line, and
tells you it did. Every value in it is optional: with no API keys at all the
stack runs end to end, the agents produce structured results, and every
unconfirmed price is labelled an `ESTIMATE`.

The first run builds two images and takes a few minutes. Later runs are
seconds.

## URLs

| | |
|---|---|
| Frontend | <http://localhost:5173> |
| Backend | <http://localhost:8000> |
| API docs | <http://localhost:8000/docs> |
| Health | <http://localhost:8000/health> |
| Verbose health | <http://localhost:8000/api/v1/health?verbose=true> |
| PostgreSQL | `127.0.0.1:5432`, loopback only |

The verbose health endpoint is the one to read when something is configured but
not behaving: it reports which providers are live, which MCP transports are in
use, and whether the database is real or the in-memory fallback.

## Common commands

| Command | What it does |
|---|---|
| `make dev-local` | Start everything. Migrates first, then starts the app. |
| `make dev-local-down` | Stop it. **Keeps the database.** |
| `make dev-local-restart` | Restart one service (`s=frontend` to pick) |
| `make dev-local-logs` | Follow every service |
| `make dev-backend-logs` | Follow the API |
| `make dev-frontend-logs` | Follow Vite |
| `make dev-db-logs` | Follow PostgreSQL |
| `make dev-ps` | Container status and ports |
| `make dev-migrate` | Apply Alembic migrations |
| `make dev-migration m="..."` | Autogenerate a revision |
| `make dev-shell` | Shell in the API container (`s=db` for PostgreSQL) |
| `make dev-db` | `psql` into the development database |
| `make dev-test` | Backend suite inside the dev image |
| `make dev-clean` | Remove containers and dev images. Keeps the database. |
| `make dev-reset-db` | **Destructive.** Deletes the development database. |

## How hot reload works

Neither half needs `docker compose build` after a source change. Only a
*dependency* change does — a new package in `requirements.txt` or
`package.json`.

**Backend.** `docker-compose.dev.yml` bind-mounts `./backend` over
`/srv/journeymesh` and sets `RELOAD=true`. The existing entrypoint branches on
that and execs:

```
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

uvicorn's WatchFiles reloader notices the write and restarts the server
process. You will see this in `make dev-backend-logs`:

```
WARNING:  WatchFiles detected changes in 'app/main.py'. Reloading...
INFO:     Started server process [31]
```

The virtualenv lives at `/opt/venv`, outside the mount, so bind-mounting the
source does not shadow the installed dependencies.

**Frontend.** `./frontend` is bind-mounted over `/app` and Vite runs in dev
mode. An anonymous volume keeps the container's own `node_modules`, because the
host's are built for the host's platform and would break the container.
`CHOKIDAR_USEPOLLING=true` is set, because bind mounts on macOS and Windows do
not deliver inotify events and the dev server would silently stop noticing
edits. You will see:

```
[vite] hmr update /src/pages/AboutPage.tsx
```

**The `/api` contract is the same as production.** In production nginx proxies
`/api` to the backend; here the Vite dev server does. Either way the browser
calls its own origin, `VITE_API_BASE_URL` stays empty, and no code branches on
which environment it is in. The proxy target comes from `DEV_API_PROXY_TARGET`,
which `docker-compose.dev.yml` sets to `http://backend:8000`. That variable is
read by Node when Vite loads its config and is deliberately **not** prefixed
`VITE_`, so it is never compiled into the browser bundle.

## MCP: disabled, local, remote

The application accepts exactly three transport values. Anything else is read
as `disabled`:

| Value | What happens |
|---|---|
| `disabled` | The in-process adapter. No subprocess, no network. The default. |
| `stdio` | A local MCP server is started as a child process and spoken to over its stdin and stdout. |
| `streamable_http` | A remote MCP server at `MCP_*_URL`. `http` and `streamable-http` are accepted spellings of the same thing. |

**Only `weather` ships a local server.** The backend starts
`python -m app.mcp.weather_server`. Setting `stdio` for `search` or `aviation`
does nothing useful — they have no local server, so the client falls back to
the in-process adapter.

**Local MCP** — exercises a real subprocess and a real MCP session:

```ini
# .env.dev
MCP_WEATHER_TRANSPORT=stdio
OPENWEATHER_API_KEY=<your key>
```

The child process gets a deliberately minimal environment: the MCP SDK's safe
default plus an allowlist of the provider variables an MCP server actually
reads. `DATABASE_URL`, the LangSmith key and everything else stay behind.

**Remote MCP** — exercises the network transport:

```ini
MCP_WEATHER_TRANSPORT=streamable_http
MCP_WEATHER_URL=http://host.docker.internal:9001/mcp
```

Use `host.docker.internal` for a server on your host machine, or the container
name for one on the same Compose network.

Restart the backend after either change: `make dev-local-restart`.

**A misconfigured transport does not fail loudly.** An unreachable server
degrades to the in-process adapter so a journey still completes. The symptom is
deterministic data where you expected live data, not an error. Confirm what is
actually in use:

```bash
curl -s 'http://localhost:8000/api/v1/health?verbose=true' | python3 -m json.tool
```

## Database access

```bash
make dev-db                       # psql inside the container
```

Or from a host tool — TablePlus, DBeaver, `psql` — on `127.0.0.1:5432` with the
development credentials from `.env.dev`. The port is bound to loopback only, so
nothing on your network can reach it.

## Migrations

```bash
make dev-migrate                            # apply everything pending
make dev-migration m="add trips.locale"     # autogenerate a revision
```

`make dev-local` runs the migration itself, before starting the application,
and stops if it fails. This is the same one-shot `migrate` container production
runs, using the same entrypoint — there is one migration mechanism, not two.

The generated revision lands in `backend/alembic/versions/` on your machine
through the bind mount. **Read it before committing.** Autogenerate is a
starting point, not an answer: it misses renames, server defaults and data
migrations.

## Resetting the development database

```bash
make dev-reset-db
```

Destructive, and it asks you to type `reset` first. It deletes the
`journeymesh-dev_postgres-data` volume and every journey in it. Production is a
different machine and a different volume and is unaffected.

`make dev-local-down` does **not** do this. It stops containers and keeps the
data, which is what you want ninety-nine times out of a hundred.

## Common development errors

### Port already in use

```
Error response from daemon: ports are not available: ... bind: address already in use
```

Something already owns 5173, 8000 or 5432. A local PostgreSQL install on 5432
is the usual culprit. Find it, then change the port in `.env.dev`:

```bash
lsof -nP -iTCP:5432 -sTCP:LISTEN     # macOS / Linux
```

```ini
# .env.dev
POSTGRES_PORT=5433
```

### Backend unhealthy

```bash
make dev-backend-logs
```

Read the first traceback, not the last. Usual causes: a syntax error in a file
you just saved (the reloader shows it and keeps the old process running), a
missing dependency after a `requirements.txt` change (`make dev-local` rebuilds
— a code change does not need it, a dependency change does), or the database
not being ready.

### PostgreSQL unhealthy

```bash
make dev-db-logs
```

If it reports an incompatible data directory, the volume was created by a
different PostgreSQL major version. `make dev-reset-db` and start again.

### Migration failure

`make dev-local` stops before starting the application, on purpose. Run it
alone to see the full Alembic error:

```bash
make dev-migrate
```

If a revision is half-applied, inspect the version table:

```bash
make dev-db
journeymesh=# select * from alembic_version;
```

### Frontend cannot reach the backend

Check the request in the browser's network tab. It should go to
`localhost:5173/api/...`, not `localhost:8000/...`. If it goes directly to
port 8000, `VITE_API_BASE_URL` has been set somewhere; it must stay empty.

If the request goes to `/api` and returns 502 or hangs, the Vite proxy cannot
reach the backend. Confirm the container is up (`make dev-ps`) and that
`DEV_API_PROXY_TARGET` is `http://backend:8000` — `127.0.0.1:8000` inside the
frontend container means the frontend container itself.

### Vite hot reload not working

Edits appear when you refresh but not automatically. The dev server is not
seeing file events. Confirm `CHOKIDAR_USEPOLLING=true` reached the container:

```bash
docker compose -f docker-compose.dev.yml --env-file .env.dev exec frontend env | grep CHOKIDAR
```

If it is set and reload still does not happen, the browser may have lost the
HMR websocket — check the browser console for `[vite] server connection lost`
and reload the page once.

### Docker volume permission issues

On Linux the container user is uid 10001 and your host files are owned by you,
so a file the container needs to *write* — a new Alembic revision — can fail
with `Permission denied`. Generate it as your own user instead:

```bash
docker compose -f docker-compose.dev.yml --env-file .env.dev run --rm \
  --user "$(id -u):$(id -g)" --entrypoint alembic backend \
  revision --autogenerate -m "your message"
```

macOS and Windows do not have this problem: Docker Desktop maps ownership for
you.

### MCP process cannot start

With `MCP_WEATHER_TRANSPORT=stdio`, look for the child process failing in
`make dev-backend-logs`. Test it directly:

```bash
make dev-shell
$ python -m app.mcp.weather_server        # should wait for JSON-RPC on stdin
```

An MCP stdio server owns stdout: the client parses it as JSON-RPC, one message
per line. Anything else printed there corrupts the stream. If you add logging
to a tool, send it to **stderr**.

### MCP remote endpoint unavailable

The journey still completes using the in-process adapter and the result carries
a note saying the server was unreachable. Check the URL is reachable *from the
container*, not just from your host:

```bash
make dev-shell
$ python -c "import httpx; print(httpx.get('http://host.docker.internal:9001/mcp').status_code)"
```

A `421 Misdirected Request` means the MCP server rejected the `Host` header.
The Python MCP SDK's HTTP transport has DNS-rebinding protection and only
accepts hosts it has been told to allow — reach it on an allowed name, or
configure the server's allowed hosts.

### API key missing

Everything works; the data is deterministic and every price is labelled
`ESTIMATE`. That is the designed behaviour, not a fault. Confirm what the
application thinks it has:

```bash
curl -s 'http://localhost:8000/api/v1/health?verbose=true' | python3 -m json.tool
```

It reports each provider as configured or not configured, never the value.

### Provider rate limit

A free-tier key exhausted for the day shows as a provider failure in the logs
and a fall back to deterministic data. Wait, or unset the key to make the
behaviour explicit while you work on something else.

### LangSmith disabled or misconfigured

Tracing needs `LANGSMITH_TRACING=true` **and** a key. With one but not the
other, nothing is traced and nothing fails — tracing is never load-bearing. The
verbose health endpoint reports which half is missing.

---

# Production

## Architecture

```
Internet
   │  :80  :443
   ▼
┌──────────────────── OVHcloud VPS ────────────────────┐
│  /opt/proxy       shared-caddy   ← only public ports │
│                        │                             │
│                 ┌──────┴─── proxy network ────┐      │
│  /opt/journeymesh      ▼                      │      │
│              journeymesh-frontend  (nginx)    │      │
│                        │  /api                       │
│                        ▼  ── journeymesh_default ──  │
│              journeymesh-backend  (FastAPI)          │
│                        │                             │
│                        ▼                             │
│              journeymesh-db  (PostgreSQL 16)         │
└──────────────────────────────────────────────────────┘
```

Only Caddy publishes a host port. The backend and the database publish nothing
at all — not even on loopback.

## Directories

| Path | What it is |
|---|---|
| `/opt/proxy` | the shared reverse proxy, its own Compose project |
| `/opt/journeymesh` | the application stack |
| `/opt/journeymesh/.env` | every application secret. Owned by `deploy`, mode `600`. |
| `/opt/journeymesh/.env.images` | the two image references, rewritten by each release |
| `/opt/journeymesh/.env.images.previous` | the tags the last release replaced |
| `/opt/journeymesh/releases.log` | what was deployed, when, by whom |
| `/opt/journeymesh/backups` | nightly `pg_dump` output |

Define these once per session, and every command below is short:

```bash
alias jm='docker compose -f /opt/journeymesh/docker-compose.prod.yml \
  --env-file /opt/journeymesh/.env --env-file /opt/journeymesh/.env.images'
alias px='docker compose -f /opt/proxy/docker-compose.yml --env-file /opt/proxy/.env'
```

## Status and health

```bash
jm ps
px ps
```

```bash
# from the VPS, inside the container network
jm exec backend curl -fsS http://127.0.0.1:8000/health
jm exec frontend curl -fsS http://127.0.0.1/healthz

# from anywhere, the way a browser sees it
curl -fsS https://<your-domain>/api/v1/health
```

`/health` is the container probe and is not proxied publicly: nginx forwards
only `/api/`, so `https://<domain>/health` returns the application shell with a
200. The public API health path is `/api/v1/health`.

## Logs

```bash
jm logs -f --tail 100            # everything
jm logs -f backend
jm logs -f frontend
jm logs -f db
px logs -f caddy                 # TLS, routing, certificate renewal
```

Never run `docker compose config` while sharing a screen or pasting output: it
renders the database password.

## Restarting one service

```bash
jm restart backend               # not the whole stack
jm restart frontend
```

Restarting the application never touches `/opt/proxy`. That is the point of
keeping them separate: TLS for every application on the box must not depend on
one of them.

## Deployment

```
merge to main
   → CI (lint, tests, scans, image build validation)
   → build images, push to GHCR tagged with the full commit SHA
   → production GitHub Environment  (approval, if a reviewer is configured)
   → ssh as deploy@vps
   → docker compose pull
   → docker compose run --rm migrate      ← a failure stops here
   → docker compose up -d
   → health checks, then a public HTTPS check
```

The VPS never builds and never holds a checkout. See
[deploy/OVHCLOUD.md](deploy/OVHCLOUD.md).

## Manual deployment

When GitHub Actions is unavailable. The image tags in `.env.images` must
already point at images that exist in GHCR.

```bash
ssh deploy@<vps-ip>
cd /opt/journeymesh
./deploy.sh
```

That script does exactly what the workflow does, in the same order: check the
`proxy` network exists, keep the previous tags, pull, migrate, `up -d`, wait
for health. For a release carrying a schema change you cannot trivially undo:

```bash
BACKUP_BEFORE_MIGRATE=1 ./deploy.sh
```

By hand, step by step:

```bash
cd /opt/journeymesh
jm pull
jm run --rm migrate          # must exit 0
jm up -d --remove-orphans
jm ps
```

## Migration failure

The release stops before the new containers start. The previous release is
still serving traffic, and the database is in whatever state Alembic reached.

1. Read the full error: `jm run --rm migrate`
2. Check where Alembic thinks it is:
   ```bash
   jm exec db psql -U journeymesh -d journeymesh -c 'select * from alembic_version;'
   ```
3. **Do not** run `up -d` to "see if it works". That starts the application
   against a schema it does not expect, which turns a stopped deployment into a
   corrupted one.
4. Fix the revision, push, let CI pass, release again.

If the migration partially applied and the revision is not idempotent, restore
from the most recent dump before retrying.

## Rollback

Every release is an immutable image tagged with its commit SHA, so a rollback
is a tag change, not a rebuild.

**Through GitHub Actions**, which is the safer path because it also runs the
health checks: run the *Deploy to production* workflow with `image_tag` set to
the previous git SHA. Build and CI are skipped; it pulls an image that already
exists.

**On the VPS:**

```bash
cd /opt/journeymesh
cat .env.images.previous          # what the last release replaced
cp .env.images.previous .env.images
jm pull && jm up -d
```

> **A rollback does not undo a migration.** If the bad release added a column,
> the older image ignores it and the rollback is clean. If it dropped, renamed
> or retyped one, the older image will fail against the current schema and the
> only route back is a restore from a dump. This is why migrations are additive
> and why `BACKUP_BEFORE_MIGRATE=1` exists. Never assume an application
> rollback is safe after a destructive schema change — check what the migration
> actually did first.

## Backup

`deploy/backup.sh` runs nightly from the deploy user's crontab. It runs
`pg_dump` **inside** the database container, so it needs no host port.

```bash
crontab -l                        # confirm it is scheduled
/opt/journeymesh/backup.sh        # run one now
ls -lh /opt/journeymesh/backups
```

It keeps 14 days of compressed dumps and deletes nothing else.

**Copy them off the VPS.** A backup on the machine it protects is not a backup:

```bash
# from your laptop
rsync -av deploy@<vps-ip>:/opt/journeymesh/backups/ ~/journeymesh-backups/
```

OVHcloud's snapshots complement this rather than replacing it. A snapshot
restores the machine; a dump restores one table.

## Restore

Restore into a **scratch database first**, always. A backup that has never been
restored is a hope, not a backup.

```bash
cd /opt/journeymesh
jm exec -T db createdb -U journeymesh journeymesh_restore_test
gunzip -c backups/journeymesh-<stamp>.sql.gz \
  | jm exec -T db psql -U journeymesh -d journeymesh_restore_test
jm exec -T db psql -U journeymesh -d journeymesh_restore_test -c '\dt'
```

To restore over the live database — destructive, and the dump was taken with
`--clean --if-exists`, so it drops what it replaces:

```bash
jm stop backend                   # stop writes first
gunzip -c backups/journeymesh-<stamp>.sql.gz \
  | jm exec -T db psql -U journeymesh -d journeymesh
jm start backend
```

## Disk, RAM and CPU

```bash
df -h                             # 40 GB total; watch /
docker system df                  # images, containers, volumes, build cache
free -h
docker stats --no-stream
```

This is a 2 vCPU / 4 GB machine expected to host three small applications, so
memory is the constraint. `WEB_CONCURRENCY` defaults to 1 for that reason;
raise it only if free memory allows.

Reclaiming space, least destructive first:

```bash
docker image prune -af --filter 'until=168h'    # images older than a week
docker builder prune -af                        # build cache
```

Never `docker system prune --volumes` — that deletes the database and Caddy's
certificates.

### Oversized logs

Every service caps its own logs, and the daemon has a default cap, but check:

```bash
sudo du -sh /var/lib/docker/containers/* | sort -h | tail -5
```

A container producing hundreds of megabytes a day is usually stuck in a
restart loop. Find out why before truncating anything.

## Caddy and TLS

Certificates are obtained and renewed by Caddy itself. There is no cron job and
nothing to renew by hand.

```bash
px logs -f caddy
px exec caddy caddy validate --config /etc/caddy/Caddyfile
px exec caddy caddy reload --config /etc/caddy/Caddyfile   # after an edit
```

| Symptom | Check |
|---|---|
| Certificate never issued | `dig +short <domain>` points at this VPS? Port 80 open? `sudo ufw status` |
| `502 Bad Gateway` | The application is down, or its frontend is not on the `proxy` network: `jm ps`, `docker network inspect proxy` |
| Caddy resolves nothing | The frontend's network alias and the Caddyfile upstream must be the same string |
| Rate limited by Let's Encrypt | Too many failed attempts. Wait, and use the staging endpoint (commented in the Caddyfile) while debugging DNS. |

Do not delete the `caddy-data` volume casually: it holds the certificates and
the ACME account key, and a fresh start means fresh issuance for every domain
at once.

## GHCR authentication

Only relevant if the packages are private.

During a release the workflow logs the VPS in with the job's own token and logs
out at the end, so nothing long-lived is stored. If you need to pull outside a
release:

```bash
read -rs GHCR_TOKEN               # a token with read:packages and nothing else
echo "$GHCR_TOKEN" | docker login ghcr.io -u <github-username> --password-stdin
unset GHCR_TOKEN
chmod 600 ~/.docker/config.json
```

`denied` or `unauthorized` on `jm pull` means the login expired or the token
lacks `read:packages`. Never put a token in a Compose file or in git.

## SSH and deployment access

| Symptom | Cause |
|---|---|
| Workflow fails at "Configure SSH" | `OVH_KNOWN_HOSTS` does not match the server's host key, or the deploy key is not in `authorized_keys`. Re-run `ssh-keyscan -p <port> <host>` and update the secret. |
| Host key changed | The VPS was rebuilt. Verify the new fingerprint from the OVHcloud console before trusting it, then update the secret. |
| Workflow fails at "Refuse to deploy as root" | `OVH_USER` points at root. Use `deploy`. |
| `permission denied` running docker | The deploy user is not in the `docker` group: `sudo usermod -aG docker deploy`, then log out and back in. |
| Cannot write to `/opt/journeymesh` | `sudo chown -R deploy:deploy /opt/journeymesh` |

## MCP in production

The same three transports as development, set in `/opt/journeymesh/.env`:

```ini
MCP_WEATHER_TRANSPORT=disabled          # or stdio, or streamable_http
MCP_WEATHER_URL=
```

`stdio` starts a child process inside the backend container. That is fine on
this machine but it is another process per call, on 4 GB — prefer `disabled`
or `streamable_http` in production unless you have measured it.

An unreachable MCP server degrades to the in-process adapter rather than
failing the journey, so the symptom is deterministic data, not an error:

```bash
curl -s 'https://<your-domain>/api/v1/health?verbose=true' | python3 -m json.tool
jm logs backend | grep -i 'remote MCP call failed'
```

Restart the backend after changing any transport: `jm up -d backend`.

## External provider failures

None of these takes the application down. Each degrades to deterministic
output, and the result says so.

| Provider | Symptom | Check |
|---|---|---|
| Groq | Every plan is deterministic | Key set? Rate limited? `jm logs backend \| grep -i groq` |
| Tavily | Search results are generic | `grep -i tavily` in the backend logs |
| OpenWeather | Forecasts labelled `ESTIMATE` | `grep -i openweather` |
| AviationStack | Flights labelled `ESTIMATE` | `grep -i aviation` |
| LangSmith | No traces appear | Needs `LANGSMITH_TRACING=true` *and* a key. Never load-bearing. |

The verbose health endpoint reports each provider as configured or not
configured, and never reports a value.

## Incident checklist

1. **Confirm the user-facing failure.** `curl -fsS https://<domain>/api/v1/health` and load the interface. Know what is actually broken before touching anything.
2. **Container status.** `jm ps` and `px ps`. Anything restarting, unhealthy, or missing?
3. **Health endpoints.** Backend `/health`, frontend `/healthz`, public `/api/v1/health`.
4. **Logs.** `jm logs --tail 200 backend`. First error, not last.
5. **Database.** `jm exec db pg_isready -U journeymesh`, then `jm exec db psql -U journeymesh -d journeymesh -c 'select count(*) from trips;'`
6. **External providers.** The table above. A provider outage degrades, it does not break.
7. **MCP transport.** Verbose health, plus `grep -i 'remote MCP call failed'`.
8. **Disk and memory.** `df -h`, `free -h`, `docker system df`. A full disk looks like everything failing at once.
9. **Was it the deployment?** `tail -20 /opt/journeymesh/releases.log`. If the timing matches, roll back — see [Rollback](#rollback) — and read the migration caveat first.
10. **Record the root cause.** What broke, what you changed, what would have caught it. A runbook entry that did not exist is the most valuable output of an incident.

---

---

# MCP and human-in-the-loop

Two mechanisms carry most of JourneyMesh's behaviour, and both are easier to
operate once you know why they are shaped the way they are. This section is
written to be read start to finish.

## 1. What MCP is doing here

The Model Context Protocol is a wire protocol for tool calling. A *server*
advertises tools and executes them; a *client* discovers and invokes them. It
matters because it decouples a tool's implementation from the agent that uses
it: JourneyMesh's weather agent asks for a forecast and receives a forecast,
without knowing whether that came from a subprocess on the same machine, an
HTTPS call to a vendor, or a local Python function.

JourneyMesh uses three MCP servers and keeps a built-in adapter behind each
one:

| Provider | Transport | Where it runs | Falls back to |
|---|---|---|---|
| Search | `streamable_http` | Tavily's hosted server | in-process search adapter |
| Aviation | `stdio` | a subprocess in the backend container | in-process reference tables |
| Weather | `stdio` | a subprocess in the backend container | in-process climate model |

## 2. Why Tavily uses streamable HTTP

Tavily hosts the server. There is nothing to install and nothing to run, so
the only sensible transport is the network one. `streamable_http` is MCP's
HTTP transport: one long-lived HTTP connection carrying JSON-RPC in both
directions.

The awkward part is authentication. Tavily takes the API key as a **query
parameter**, which makes the endpoint URL itself a credential:

```
https://mcp.tavily.com/mcp/?tavilyApiKey=<secret>
```

That single fact drives three design decisions, all in
`app/mcp/security.py` and `app/core/config.py`:

- The URL is **built at use time** from `TAVILY_API_KEY`. It is never stored
  in a variable, never written to an environment file, and you never paste
  your key into a URL.
- Every place the URL could escape - a log line, an exception, the health
  endpoint, a LangSmith trace - passes it through `redact_url`, which masks
  any credential-shaped query parameter by name.
- `MCP_SEARCH_URL` still exists, for someone pointing at a self-hosted
  server, and is redacted identically.

## 3. Why AviationStack uses stdio and uv

AviationStack's MCP server is published as a Python package, not a hosted
service. Running it means running a process.

`uvx` (from `uv`) fetches a package into an isolated environment and runs it,
so the server never becomes a dependency of this application and cannot
conflict with one. That isolation is doing real work here: the package
requires Python **3.13** while JourneyMesh runs on **3.11**, and it needs
`mcp` 1.x pinned in its own environment. Neither constraint reaches us.

Both the 3.13 interpreter and the package are installed **at image build
time** (`backend/Dockerfile`), so a flight lookup on the VPS is a local
process start rather than a download. The VPS needs nothing installed on the
host.

## 4. Why weather uses our own FastMCP server

The weather server is ours: `app/mcp/weather_server.py`, built on FastMCP,
exposing `current_weather` and `weather_forecast`. It calls OpenWeather when
`OPENWEATHER_API_KEY` is set and falls back to a deterministic climate model
when it is not - and it labels the difference, always. Live observations are
`LIVE`; anything modelled is `ESTIMATE`. Neither is ever presented as the
other.

It exists as an MCP server rather than a plain function because it is the
honest demonstration of the pattern: the same code is reachable in-process and
over MCP, and swapping transports changes nothing an agent can observe.

## 5. How the stdio child processes work

`stdio` means the client starts the server as a **child process** and speaks
JSON-RPC over its stdin and stdout. One message per line, on stdout, and
nothing else - which is why `weather_server.main()` moves every log handler to
stderr before serving. A single stray log line on stdout corrupts the stream
and the client fails to decode it.

There are two session strategies, in `app/mcp/lifecycle.py`:

**Managed** (weather). `StdioSessionManager` starts the subprocess from the
FastAPI lifespan, keeps it warm, restarts it if it dies, and terminates it on
shutdown. So the normal workflow is exactly:

```bash
uvicorn app.main:app --reload      # local
docker compose up -d               # production
```

and the child appears by itself in the same process tree. No systemd unit, no
second container, no port, no HTTP route, no terminal to keep open. It is
started with `sys.executable`, so the interpreter is always the one running
the application - never `python3`, never a Conda path, never an absolute path
baked in for one machine.

**Per call** (aviation, and any fallback). A session is opened and closed
around one invocation. This is what tests use, what runs before the lifespan
has started, and what probes use so they never disturb live traffic. A
third-party server is deliberately left here: a package that misbehaves should
not hold a process open for the life of the application.

Either way the child is reaped. `stdio_client` is an async context manager
that terminates the process on exit, and the managed path holds it in an
`AsyncExitStack` that the lifespan unwinds.

## 6. Why we pass environment variables to child processes

The MCP SDK deliberately does **not** inherit the parent environment. With
`env=None` a child receives only `HOME` and `PATH`. That default is right - a
subprocess has no business seeing the database password - but taken literally
it means the weather server starts with no `OPENWEATHER_API_KEY` and silently
produces estimates. That reads as a broken provider rather than a
configuration gap, which is the worst kind of bug.

`stdio_child_environment()` in `app/mcp/client.py` therefore builds the child
environment explicitly: the SDK's safe default, plus the variables a launcher
needs (`PATH`, `UV_CACHE_DIR`, TLS bundle), plus an **allowlist** of provider
credentials, plus whatever that server's own config declares.

`DATABASE_URL`, `LANGSMITH_API_KEY` and `GROQ_API_KEY` are not on the list and
do not travel. A test asserts that.

## 7. How fallback works

Every MCP tool has an in-process implementation behind it. When an MCP call
cannot be made or cannot be trusted, that implementation answers instead:

```
agent -> MCPClient -> adapter -> MCP server
                 \
                  '-> in-process adapter (fallback)
```

Four things trigger a fallback, and they are different on purpose:

1. **The server is not enabled.** No key, no launcher, or explicitly disabled.
   Decided once, at configuration time.
2. **The adapter declines.** Some tools have no faithful remote equivalent -
   see §8 - so they never attempt the call.
3. **The call fails.** Timeout, transport error, authentication failure. The
   error is redacted, recorded per server, and the local adapter answers.
4. **The response cannot be interpreted.** The server replied in a shape the
   adapter does not recognise. Declining beats half-parsing a payload that
   becomes a wrong price.

In every case the result carries a note saying the local adapter was used, and
the source label stays honest.

## 8. When an adapter declines, and why

`app/mcp/providers/` translates between JourneyMesh's tool contract and each
server's own. Two tools deliberately decline:

- **`search_hotels`** does more than search: it bands prices by travel style
  and builds the candidate records the budget agent reads. A raw list of web
  results cannot substitute without inventing nightly rates.
- **`search_flights`** produces priced options. AviationStack's route endpoint
  has no fares at all, so assembling one from the other would mean inventing
  the number a traveller is most likely to act on.

Both use their local implementations, which call the same vendors for the
parts they can verify and label the rest `ESTIMATE`. This is why the health
endpoint can say a server is reachable while some tools still answer locally -
that is correct behaviour, not a degraded one.

## 9. How provider isolation works

One MCP server failing must tell you nothing about the others. Concretely:

```
Tavily     = working   ->  search keeps working
Weather    = failed    ->  weather falls back, labelled ESTIMATE
Aviation   = working   ->  aviation keeps working
```

The isolation is structural. Each call opens its own session, catches its own
exceptions and records its own failure. `probe_all` uses
`asyncio.gather(..., return_exceptions=True)`, so one server timing out cannot
cancel the probe of another. Nothing shares a connection, a lock or a retry
budget across servers.

## 10. Local development versus the VPS

The configuration is identical. What differs is what is installed.

| | Local | VPS (Docker) |
|---|---|---|
| Weather | subprocess of the uvicorn process | subprocess in the backend container |
| Aviation | needs `uv` on your machine; otherwise falls back | pre-installed in the image, works offline |
| Search | needs `TAVILY_API_KEY`; otherwise falls back | same |
| Interpreter | `sys.executable` | `sys.executable` |

Nothing is machine-specific, and no path is hard-coded. Check what a given
deployment actually resolved to:

```bash
curl -s 'http://localhost:8000/api/v1/health/mcp?probe=true' | python3 -m json.tool
```

## 11. How LangGraph `interrupt()` works

`interrupt(value)` raises a control-flow signal that LangGraph catches. The
checkpointer records the state *and* the fact that this node is mid-execution,
and `ainvoke` returns with `__interrupt__` set instead of a finished state.

JourneyMesh calls it in `_human_review_node` in `app/graph/travel_graph.py`.
The payload is built by `app/graph/human_review.py` and contains what a
reviewer needs to decide: the draft itinerary, the budget, the evaluation
scores, which agents ran, and which actions are available.

One subtlety worth knowing, because it caused a real bug during development:
**a node's state changes are persisted from its return value**, and
`interrupt()` raises rather than returning. Anything written in the same node
before the pause is discarded. That is why "awaiting review" is set by a
separate `review_gate` node immediately before, so the checkpoint, the database
and the API all agree the journey is waiting while it actually is.

## 12. How `Command(resume=...)` works

`graph.ainvoke(Command(resume=value), config)` continues the paused run. The
*same* node call resumes and `interrupt()` returns `value`, as though it had
simply been a slow function. Everything after the interrupt runs exactly once,
with the decision in hand.

JourneyMesh sends:

```python
Command(resume={"action": "approve"})
Command(resume={"action": "request_changes", "feedback": "cheaper hotels"})
```

from `TravelWorkflow.approve()` and `.revise()`. The conditional edge after
`human_review` then routes to `final_response` or back through
`supervisor_revision`, which re-runs only the agents the change affects and
returns to review.

This is the difference from ending the graph and re-entering it: a resume
genuinely continues, so nothing has to be reconstructed and nothing is
replanned that the traveller did not ask to change.

There is one documented fallback. If no pending interrupt exists for a thread -
a `MemorySaver` after a restart, or a restored database with no checkpoint row -
the decision is applied to the state and the graph is re-entered instead. It is
logged when it happens.

## 13. How checkpoints make this possible

The pause lives in the checkpointer, not in a Python object. A different
process, a restarted worker, or a new `TravelWorkflow` instance reading the
same checkpointer can continue a run somebody else started. A test asserts
exactly that.

PostgreSQL is used in production (`langgraph-checkpoint-postgres`), and
`MemorySaver` is the local and test fallback - which is why a local restart
loses pauses and a production one does not.

## 14. `trip_id` and `thread_id`

`trip_id` is the business identifier: the primary key, the URL segment, the
thing the frontend knows. `thread_id` is LangGraph's identifier for a
checkpointed conversation.

They are the same value. `TravelWorkflow.config()` is the whole mapping:

```python
{"configurable": {"thread_id": trip_id}}
```

Keeping them equal means one identifier to reason about and no second ID
exposed to the frontend. They are separate *names* only because they belong to
different layers.

## 15. How secrets are protected

| Secret | Where it lives | How it is kept out of the open |
|---|---|---|
| `TAVILY_API_KEY` | environment | URL built at use time, `redact_url` everywhere it could escape |
| `OPENWEATHER_API_KEY` | environment | passed to the child by allowlist, never logged |
| `AVIATION_STACK_API_KEY` | environment | same, under either spelling |
| `DATABASE_URL`, `GROQ_API_KEY`, `LANGSMITH_API_KEY` | environment | never passed to any child process |

Enforced in three places: `MCPServerConfig.describe()` redacts before anything
is returned by an endpoint, `safe_error()` redacts before anything is logged or
traced, and `stdio_child_environment()` allowlists rather than inherits. Tests
assert a Tavily key cannot appear in the verbose health output, the MCP probe,
or an error message.

## 16. Troubleshooting each provider

Start here, always:

```bash
curl -s 'http://localhost:8000/api/v1/health/mcp?probe=true' | python3 -m json.tool
```

`?probe=true` actually connects. Without it you get configuration only, which
is cheap but cannot tell you whether something works.

**Search reports `enabled: false`.** No `TAVILY_API_KEY`. The
`unavailable_reason` field says so. Search still works through the in-process
adapter; results are labelled `SEARCH_DERIVED`.

**Search reports `reachable: false`.** The key is set but Tavily rejected or
could not be reached. Check the redacted `error`. A `401` means the key; a
timeout means the network.

**Aviation reports `enabled: false`.** Either no API key, or neither
`aviationstack-mcp` nor `uvx` is on `PATH`. Inside the container both are
present; on a laptop, install `uv`. The reason field distinguishes the two.

**Aviation is reachable but flights still say `ESTIMATE`.** Expected. See §8 -
`search_flights` declines on purpose because the remote server has no fares.

**Weather reports `reachable: false`.** The subprocess did not start. Check
that `app/mcp/weather_server.py` is present and run it by hand to see the
error:

```bash
docker compose exec backend python -m app.mcp.weather_server
```

It should wait silently for JSON-RPC on stdin. A traceback is your answer.

**Weather is reachable but everything is `ESTIMATE`.** No
`OPENWEATHER_API_KEY`, or the key was rejected. This is designed behaviour and
correctly labelled - it is not a fault.

**A journey is stuck awaiting review.** Check whether the interrupt is still
pending. If the checkpoint is gone the approve endpoint still completes, via
the fallback in §12, and logs that it did.

---

# Security incidents

The repository is public and its Actions logs are public. Assume any credential
that reached a commit, a log or an issue is compromised.

**Rotate first, clean up second.** History rewriting takes time and the old
value is valid the whole while.

**Never print a secret while troubleshooting.** No `cat .env`, no `env`, no
`printenv`, no `docker compose config`, no `set -x` around a command that
carries one. Check that a variable is *set*, never what it contains:

```bash
jm exec backend sh -c '[ -n "$GROQ_API_KEY" ] && echo set || echo empty'
```

### Suspected leaked provider API key

Groq, Tavily, OpenWeather, AviationStack, LangSmith.

1. Revoke and reissue in that provider's console. Revoke first — a reissued key
   does not disable the old one.
2. Update `/opt/journeymesh/.env` on the VPS.
3. `jm up -d backend` — only the backend reads provider keys.
4. Check the provider's usage dashboard for calls you did not make.
5. Confirm it is not in git: see the history check below.

### Suspected leaked GitHub token

1. **Settings → Developer settings → Personal access tokens** → delete it.
2. If it had `write:packages`, review the GHCR package versions for tags you
   did not publish and delete them.
3. On the VPS: `docker logout ghcr.io`.
4. Review **Settings → Security log** for actions you did not take.

### Suspected leaked SSH deployment key

1. Remove the public half from the VPS immediately — this is the step that
   actually closes the door:
   ```bash
   ssh deploy@<vps-ip>
   nano ~/.ssh/authorized_keys          # delete the compromised line
   ```
2. Generate a replacement, install it, verify it works from a second session.
3. Update the `OVH_SSH_PRIVATE_KEY` secret in the `production` environment.
4. Review `sudo last -20` and `sudo journalctl -u ssh --since '7 days ago' | grep Accepted`.

### Unauthorized VPS login

1. Do not reboot — you would lose volatile evidence.
2. `who`, `sudo last -30`, `sudo journalctl -u ssh --since '7 days ago' | grep -i accepted`
3. `sudo ss -tulpn` for listeners you do not recognise; `docker ps -a` for
   containers you did not start.
4. Rotate **every** credential on the machine: `/opt/journeymesh/.env` in full,
   the deploy key, any GHCR token.
5. If you cannot account for the access, rebuild the VPS from scratch and
   restore the database from a dump taken *before* the suspected intrusion.
   Reinstalling on top of a compromised host is not a remediation.

### Database credential compromise

```bash
cd /opt/journeymesh
jm exec db psql -U journeymesh -d journeymesh \
  -c "ALTER USER journeymesh WITH PASSWORD '<new-strong-password>';"
nano .env                          # update POSTGRES_PASSWORD to match
jm up -d
jm exec backend curl -fsS http://127.0.0.1:8000/health
```

The database publishes no host port, so the realistic exposure path is
`/opt/journeymesh/.env` itself. Confirm it is still `-rw------- deploy deploy`.

### Checking whether a secret reached git

Names only — never print the value:

```bash
docker run --rm -v "$PWD:/repo:ro" zricethezav/gitleaks:latest \
  git /repo --redact --no-banner
```

CI runs this on every pull request over the full history. If something is
found, rotate the credential first, then rewrite history with
`git filter-repo`, then force-push. Understand that force-pushing a public
repository does not recall forks, clones or anything a crawler already fetched
— which is exactly why rotation comes first.
