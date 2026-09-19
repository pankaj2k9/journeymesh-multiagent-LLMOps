# Deploying Travel Crew AI to an OVHcloud VPS

**Production domain: <https://travelcrewai.com>.** `www.travelcrewai.com` and
every `http://` request redirect to it permanently, so there is exactly one
canonical origin.

Production is **one OVHcloud VPS** running independent Compose projects: a
**shared reverse proxy** that owns ports 80 and 443 for the whole machine, and
one stack per SaaS application, none of which owns a host port. Travel Crew AI
is the first of those applications; the VPS is built to take more without
changing it.

That split is the important part. Only one container on a machine can bind
port 443, so TLS and routing are a property of the *server*, not of any
application on it.

```
Internet
   │  :80  :443
   ▼
┌────────────────────────────── OVHcloud VPS ──────────────────────────────┐
│                                                                          │
│  /opt/proxy              shared-caddy        ← the only public ports      │
│    Caddyfile             (global options, snippets, import sites/*.caddy)│
│    sites/travelcrewai.caddy ─┐                                           │
│    sites/<next-saas>.caddy ──┼──────┐                                    │
│                              │      │                                    │
│               ┌──────────────┴──────┴──── proxy network (external) ───┐  │
│               ▼                     ▼                                 │  │
│  /opt/journeymesh              /opt/<next-saas>                       │  │
│    travelcrewai-web (nginx)       <next-saas>-web                     │  │
│         │  /api                        │                              │  │
│         ▼  ── journeymesh_default ──   ▼  ── <next-saas>_default ──   │  │
│    backend (FastAPI) ─▶ db             its own backend, its own db    │  │
│                                                                       │  │
└──────────────────────────────────────────────────────────────────────────┘
```

```
travelcrewai.com ──▶ shared-caddy ──(proxy network)──▶ travelcrewai-web:80
                                                        nginx: static SPA
                                                        └─ /api/ ─(journeymesh_default)─▶ backend:8000 ─▶ db:5432
```

Two kinds of network, and a container joins the shared one only if Caddy must
reach it:

| Container | `journeymesh_default` | `proxy` | Host port |
|---|---|---|---|
| shared-caddy | no | yes | 80, 443, 443/udp |
| journeymesh-frontend | yes | yes, alias **`travelcrewai-web`** | none |
| journeymesh-backend | yes | **no** | none |
| journeymesh-db | yes | **never** | none |

PostgreSQL publishes nothing at all — not even on loopback. Administrative
access goes through the container.

### About the `journeymesh` names

The product was renamed to Travel Crew AI. Infrastructure identifiers from
before the rename are **kept on purpose**, because they are not user-visible
and changing them is not free:

| Identifier | Why it stays |
|---|---|
| Compose project `journeymesh`, volume `journeymesh_postgres-data` | The project name prefixes the volume. Renaming it starts production on a new, **empty** database. |
| `/opt/journeymesh`, `OVH_APP_DIR` | Referenced by the GitHub environment, cron, and backups on the VPS. |
| Containers `journeymesh-{db,backend,frontend}` | Referenced by the health gates in the release and by operators' habits. Routing never uses them — Caddy dials the alias. |
| GHCR images `journeymesh-{backend,frontend}` | Every earlier commit's image lives under those names; renaming breaks rollback to them. |
| DB user/database `journeymesh`, `JOURNEYMESH_*` nginx variables, `X-JourneyMesh-Session` header, `journeymesh_*` browser storage keys | Renaming would need a data migration, a coordinated backend/frontend release, or would reset every visitor's saved preferences. |

What *is* Travel Crew AI-specific is exactly what a second application would
need its own copy of: the domain, the `travelcrewai-web` alias, and
`/opt/proxy/sites/travelcrewai.caddy`.

---

## What you need

| | |
|---|---|
| VPS | OVHcloud VPS, 2 vCPU / 4 GB RAM / 40 GB NVMe |
| Image | Debian 12 or Ubuntu 24.04 LTS |
| DNS | control of `travelcrewai.com` |
| Local | `ssh`, `scp`, and a GitHub account that can add repository secrets |

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

## 2. Point travelcrewai.com at it

At the DNS provider for `travelcrewai.com`:

| Type | Name | Value |
|---|---|---|
| A | `@` | `<vps-ipv4>` |
| A | `www` | `<vps-ipv4>` |
| AAAA | `@` and `www` | `<vps-ipv6>` — **only** if IPv6 is configured and reachable on the VPS |

A stale or wrong AAAA record is the most common cause of a failed certificate:
Let's Encrypt prefers IPv6 when it exists. If the VPS does not answer on IPv6,
have no AAAA record at all.

**Both names must resolve before Caddy loads the site.** Caddy requests the
certificates as soon as it sees `travelcrewai.com` and `www.travelcrewai.com`,
and failed challenges count against a Let's Encrypt rate limit.

```bash
dig +short travelcrewai.com A
dig +short www.travelcrewai.com A
dig +short travelcrewai.com AAAA     # empty, or the VPS's IPv6
```

---

## 3. Bootstrap the VPS

`deploy/bootstrap-vps.sh` installs Docker, creates the unprivileged `deploy`
user, **creates the shared `proxy` network**, prepares `/opt/proxy`,
`/opt/proxy/sites` and `/opt/journeymesh`, opens 22/80/443 and closes
everything else. Run it once, as root. It is safe to run again: every step
checks before it acts, and an existing network or directory is left alone.

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
ssh-keygen -t ed25519 -C "travelcrewai github actions" -f ~/.ssh/journeymesh_deploy -N ""
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

> **Is a proxy already running on this VPS?** Then do not follow this step —
> it is for an empty machine. Follow
> [Migrating a running VPS to the shared proxy layout](#migrating-a-running-vps-to-the-shared-proxy-layout)
> instead, which keeps every existing route.

This is done **once for the VPS**, not once per release and not once per
application. Nothing in the Travel Crew AI release path ever touches it — a
release must not restart TLS for applications that have nothing to do with it.

```
/opt/proxy/
├── docker-compose.yml          Caddy itself: ports, volumes, the proxy network
├── Caddyfile                   global options + shared snippets + import sites/*.caddy
├── .env                        ACME_EMAIL, nothing else
├── reload.sh                   validate, check upstreams, reload gracefully
└── sites/
    ├── travelcrewai.caddy      Travel Crew AI's domains and upstream
    └── _template.caddy.example copied for the next SaaS; ignored as it is
```

```bash
scp -r deploy/proxy/docker-compose.yml deploy/proxy/Caddyfile \
  deploy/proxy/reload.sh deploy/proxy/sites deploy@<vps-ip>:/opt/proxy/
scp deploy/proxy/.env.example deploy@<vps-ip>:/opt/proxy/.env
ssh deploy@<vps-ip>
```

On the VPS:

```bash
cd /opt/proxy
chmod 600 .env && chmod +x reload.sh
nano .env                                   # ACME_EMAIL=admin@travelcrewai.com
docker compose config --quiet && echo "compose file is valid"
docker compose up -d
docker compose logs -f caddy                # watch both certificates being obtained
```

Until Travel Crew AI is deployed, `https://travelcrewai.com` answers `502`: the
proxy and the certificate are in place and the application is not there yet.
That is expected, and it affects no other site.

### How the pieces fit

**`Caddyfile`** belongs to the server. It holds the ACME e-mail, three snippets
every site can use, and one line that loads every application:

```caddy
{
	email {$ACME_EMAIL:admin@travelcrewai.com}
}

(common)       { encode, security headers, JSON access log }
(hsts)         { Strict-Transport-Security, one year, no includeSubDomains }
(www_redirect) { permanent redirect to https://<args[0]>{uri} }

import /etc/caddy/sites/*.caddy
```

Snippets are defined above the import on purpose: Caddy expands `import` in
place, so a site file can only use a snippet that already exists.

**`sites/travelcrewai.caddy`** belongs to Travel Crew AI:

```caddy
www.travelcrewai.com {
	import www_redirect travelcrewai.com
}

travelcrewai.com {
	import common
	import hsts
	reverse_proxy travelcrewai-web:80 { ... }
}
```

The upstream is the frontend's alias on the `proxy` network and nginx's
container port — there is no port 3000 here, because the web container is
nginx serving the built React app and proxying `/api/` to the backend.

**The shared `proxy` network** is how Caddy finds the application. Docker's
embedded DNS resolves `travelcrewai-web` to the frontend container because
`deploy/docker-compose.prod.yml` declares it:

```yaml
frontend:
  networks:
    default: {}
    proxy:
      aliases:
        - travelcrewai-web
networks:
  proxy:
    external: true
```

Caddy resolves the name per request, so the frontend can be recreated by a
release without Caddy being reloaded or even noticing.

**HTTPS** needs no configuration. A site address with no scheme turns on
Caddy's automatic HTTPS: certificates for both names from Let's Encrypt (with
ZeroSSL as fallback), a `308` redirect from port 80, and renewal about 30 days
before expiry. Certificates live in the `caddy-data` volume, which belongs to
`/opt/proxy` and is untouched by any application release.

---

## 6. Put the Travel Crew AI environment on the VPS

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

Note what is **not** here: the domain and the ACME e-mail. Routing and TLS
belong to `/opt/proxy`, not to any application on the VPS.

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
| `OVH_HOST` | `<vps-ip>` — the IP, not the domain, so SSH does not depend on DNS |
| `OVH_USER` | `deploy` |
| `OVH_SSH_PORT` | `22` |
| `OVH_APP_DIR` | `/opt/journeymesh` |
| `PUBLIC_URL` | `https://travelcrewai.com` |

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
3. **Ships** the Compose file and the operator scripts. Never anything in `/opt/proxy`.
4. **Checks** the shared `proxy` network exists, before pulling anything, and
   warns if `/opt/proxy/sites/travelcrewai.caddy` is missing.
5. **Pins** the SHA tags in `/opt/journeymesh/.env.images`.
6. **Pulls** those exact tags, using a registry token valid only for this job.
7. **Migrates** — `alembic upgrade head` in a one-shot container. A failure
   stops the release here, with the old containers still serving.
8. **Starts** the new containers and waits for every health check.
9. **Verifies** `https://travelcrewai.com/api/v1/health` from the internet —
   through DNS, the certificate, Caddy, nginx and the backend — and that the
   interface itself is served. Not `/health`: nginx proxies only `/api/`, so the
   container probe path falls through to the SPA and would answer 200 with HTML
   even for a broken backend.
10. **Logs out** of the registry and prunes images older than a week.

The same sequence by hand, if Actions is unavailable:

```bash
ssh deploy@<vps-ip>
cd /opt/journeymesh && ./deploy.sh
```

---

## Verifying HTTPS and routing

Run these after the first deployment, after any change in `/opt/proxy`, and
whenever something looks wrong. Each one isolates a different layer.

```bash
# 1. DNS: both names point at this VPS
dig +short travelcrewai.com
dig +short www.travelcrewai.com

# 2. HTTP -> HTTPS: expect 308 and a https:// Location
curl -sSI http://travelcrewai.com | grep -iE '^(HTTP|location)'

# 3. www -> canonical: expect 301 and Location: https://travelcrewai.com/
curl -sSI https://www.travelcrewai.com | grep -iE '^(HTTP|location)'

# 4. The certificate: issuer, validity, and both names in the SAN
echo | openssl s_client -connect travelcrewai.com:443 -servername travelcrewai.com 2>/dev/null \
  | openssl x509 -noout -issuer -dates -ext subjectAltName

# 5. HSTS and the security headers from the shared snippet
curl -sSI https://travelcrewai.com | grep -iE 'strict-transport|x-content-type|x-frame'

# 6. Through the proxy to the backend: expect "status":"ok"
curl -sS https://travelcrewai.com/api/v1/health

# 7. The interface, and the SPA fallback a refresh depends on
curl -sS https://travelcrewai.com/history | grep -c '<div id="root">'

# 8. The scripted checks: health, SPA routes, API, real PostgreSQL
python scripts/verify_deployment.py https://travelcrewai.com
```

On the VPS, to separate a proxy problem from an application problem:

```bash
# Is the frontend on the proxy network, under the right alias?
docker inspect journeymesh-frontend \
  --format '{{json .NetworkSettings.Networks.proxy.Aliases}}'

# Can Caddy reach it by that name? (bypasses DNS, TLS and the site config)
docker exec shared-caddy wget -qO- http://travelcrewai-web/healthz     # "ok"

# Which containers share the proxy network?
docker network inspect proxy --format '{{range .Containers}}{{.Name}} {{end}}'

# What Caddy is actually running
docker exec shared-caddy wget -qO- http://127.0.0.1:2019/config/ | head -c 600; echo

# Certificate events
docker logs shared-caddy 2>&1 | grep -iE 'certificate obtained|error' | tail
```

---

## Reloading Caddy safely

After adding, editing or removing any file in `/opt/proxy/sites/`:

```bash
/opt/proxy/reload.sh
```

It runs, in order, and stops at the first failure:

1. **`caddy validate`** on the whole configuration — the main Caddyfile with
   every `sites/*.caddy` imported. A typo in one site file stops here, and the
   running configuration, which serves every other application, is untouched.
2. **An upstream check** — every `reverse_proxy` host in `sites/` is resolved
   on the `proxy` network. An unresolvable one is a warning, not a failure: an
   application can be deployed after its site file, and until then Caddy
   answers `502` for that site alone.
3. **`caddy reload`** — graceful. Existing connections are not dropped, and if
   the new configuration fails to load Caddy keeps the old one.

It never restarts or recreates the container. The same by hand:

```bash
cd /opt/proxy
docker compose exec caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose exec caddy caddy reload   --config /etc/caddy/Caddyfile --adapter caddyfile
```

When a reload is **not** enough:

| You changed | Do |
|---|---|
| a file in `sites/` | `./reload.sh` |
| `Caddyfile`, edited in place | `./reload.sh` |
| `Caddyfile`, replaced by a tool that writes a new file (new inode) | `docker compose up -d --force-recreate` — a single-file bind mount keeps showing the old inode |
| `docker-compose.yml` or `.env` | `docker compose up -d` — recreates the container; a second or two without the proxy for every site |

To take one application offline without touching the others, rename its file
so it no longer ends in `.caddy` and reload:

```bash
mv sites/example.caddy sites/example.caddy.disabled && ./reload.sh
```

---

## Adding another SaaS application

Nothing about Travel Crew AI changes — not its Compose file, its images, its
environment, its site file, or its containers.

**1. Deploy the new stack in its own directory** with its own Compose project,
`.env`, database and release workflow — `/opt/<app>/docker-compose.yml`. Its
web container joins the shared network under an alias prefixed with the
application's name; nothing else in the stack joins it, and it publishes no
host port:

```yaml
name: <app>

services:
  web:
    image: ghcr.io/<owner>/<app>-web:<sha>
    expose:
      - "3000"
    networks:
      default: {}
      proxy:
        aliases:
          - <app>-web          # unique across the whole VPS
  api:
    networks: [default]         # not on proxy
  db:
    networks: [default]         # never on proxy

networks:
  default: {}
  proxy:
    external: true              # joins, never creates or removes, the shared network
```

```bash
cd /opt/<app> && docker compose up -d
docker network inspect proxy --format '{{range .Containers}}{{.Name}} {{end}}'
```

Check the alias is not already in use before you pick it. Two containers with
the same alias on one network are load-balanced between, silently.

**2. Point its DNS at the VPS** — bare and `www` — and confirm with `dig`.

**3. Add its site file:**

```bash
cd /opt/proxy
cp sites/_template.caddy.example sites/<app>.caddy
nano sites/<app>.caddy        # the domain, and <app>-web:<container port>
```

Or write it from the repository that owns the application and `scp` it here —
the file is the application's, the directory is the server's.

**4. Reload:**

```bash
/opt/proxy/reload.sh
curl -sSI https://<app-domain> | head -n 1
```

No restart, and no interruption for anything already running. Once HTTPS is
confirmed in a browser, uncomment `import hsts` in its file and reload again.

To remove an application later: delete its site file and reload, then
`docker compose down` in its own directory. The network, the proxy and every
other application are unaffected.

---

## Migrating a running VPS to the shared proxy layout

For a VPS whose `/opt/proxy` still has the earlier single-file design: one
`Caddyfile` with a `{$JOURNEYMESH_DOMAIN}` site block, the domain in
`/opt/proxy/.env`, and no `sites/` directory. The goal is the layout above with
**no route lost, no network or volume recreated, and at most a few seconds**
without the proxy.

### 1. Inspect before changing anything

```bash
ssh deploy@<vps-ip>
cat /opt/proxy/Caddyfile
cat /opt/proxy/.env                    # domains and an e-mail, no secrets
ls -la /opt/proxy /opt
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}'
docker network inspect proxy --format '{{range .Containers}}{{.Name}} {{end}}'
docker volume ls | grep caddy
```

Write down **every site block that is not commented out**, and the value each
`{$…}` variable in it has in `.env`. The Travel Crew AI block becomes
`sites/travelcrewai.caddy`. **Any other live block belongs to another
application and must be carried over** as its own `sites/<app>.caddy`, with the
variable replaced by the literal domain it currently resolves to. The
commented-out SaaS 2 / SaaS 3 blocks were placeholders and can be dropped.

If `docker ps` shows anything else publishing 80 or 443, stop here: the proxy
is not the only thing serving the web on this machine, and that must be
understood first.

### 2. Back up the proxy directory

```bash
sudo cp -a /opt/proxy "/opt/proxy.backup-$(date +%Y%m%d-%H%M%S)"
```

The `caddy-data` and `caddy-config` volumes are **not** touched by anything
below. The Compose project name (`proxy`) and volume names are unchanged, so
the existing certificates and ACME account carry over.

### 3. DNS

Complete [step 2](#2-point-travelcrewaicom-at-it) and confirm both names
resolve to this VPS.

### 4. Release Travel Crew AI first

Merge to `main` and let the release finish. The frontend now carries **both**
aliases on the `proxy` network: `travelcrewai-web`, for the new site file, and
the legacy `journeymesh-frontend`, which the old Caddyfile is still dialling —
so nothing changes for visitors yet.

```bash
docker inspect journeymesh-frontend \
  --format '{{json .NetworkSettings.Networks.proxy.Aliases}}'
# ["travelcrewai-web","journeymesh-frontend", ...]
```

### 5. Stage and validate the new configuration next to the old one

From your machine:

```bash
ssh deploy@<vps-ip> 'mkdir -p /opt/proxy/.incoming'
scp -r deploy/proxy/Caddyfile deploy/proxy/docker-compose.yml \
  deploy/proxy/reload.sh deploy/proxy/sites deploy@<vps-ip>:/opt/proxy/.incoming/
```

On the VPS, add the site file for every other live application you found in
step 1 to `/opt/proxy/.incoming/sites/`. Then validate the complete new
configuration in a throwaway container — no ports, no volumes, the live proxy
untouched:

```bash
docker run --rm \
  -e ACME_EMAIL=admin@travelcrewai.com \
  -v /opt/proxy/.incoming/Caddyfile:/etc/caddy/Caddyfile:ro \
  -v /opt/proxy/.incoming/sites:/etc/caddy/sites:ro \
  caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```

Do not continue until it prints `Valid configuration`.

### 6. Switch

```bash
cd /opt/proxy
mkdir -p sites
cp -n .incoming/sites/* sites/        # -n: never overwrite an existing site file
mv .incoming/Caddyfile .incoming/docker-compose.yml .incoming/reload.sh .
chmod +x reload.sh
rmdir .incoming/sites .incoming 2>/dev/null || rm -rf .incoming

# .env: keep ACME_EMAIL, remove JOURNEYMESH_DOMAIN and any SAAS*_DOMAIN lines -
# domains now live in site files.
nano .env

docker compose config --quiet && docker compose up -d
```

`up -d` recreates the Caddy container once, because the Compose file gained the
`sites/` mount. Expect a second or two without the proxy. It does not recreate
the `proxy` network or the certificate volumes. From now on, routing changes
are `./reload.sh` and never need a recreate.

### 7. Verify

```bash
docker compose logs --tail 50 caddy     # "certificate obtained successfully" for both names
./reload.sh                             # validates, checks every upstream resolves
```

Then run every check in
[Verifying HTTPS and routing](#verifying-https-and-routing), and the equivalent
`curl` for each other application you carried over.

Finally, set `PUBLIC_URL` in the GitHub `production` environment to
`https://travelcrewai.com`, so every release verifies the address people use.

### 8. Tidy up — later, once stable

- Remove the legacy `journeymesh-frontend` alias from
  `deploy/docker-compose.prod.yml`; it takes effect on the next release.
- The old IP address (`http://<vps-ip>`) no longer routes to the application.
  If links to it exist and should keep working, add
  `sites/ip-redirect.caddy`:

  ```caddy
  http://<vps-ip> {
  	redir https://travelcrewai.com{uri} permanent
  }
  ```

  Only one application can own that redirect — a bare IP is one host.

### Rolling the proxy back

```bash
cd /opt/proxy
docker compose down                                  # the proxy only; volumes and network stay
sudo rsync -a --delete /opt/proxy.backup-<stamp>/ /opt/proxy/
docker compose up -d
```

Travel Crew AI keeps its legacy alias until you remove it, so the old
Caddyfile routes to the new release unchanged.

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
| Stop Travel Crew AI | `jm down` — the proxy and the other apps keep running |
| Start Travel Crew AI | `jm up -d` |
| A shell in the API | `jm exec backend bash` |
| psql | `jm exec db psql -U journeymesh -d journeymesh` |
| Proxy status | `px ps` and `px logs -f caddy` |
| Reload routing | `/opt/proxy/reload.sh` |
| Disk usage | `docker system df` |

> **`docker compose down -v` deletes the `postgres-data` and `media-data`
> volumes** - the production database and every uploaded image. Nothing in the
> deployment path runs it, and neither should you. `down` on its own is safe;
> the `-v` is what destroys data.

### What survives a deployment, and what does not

A release replaces the application and leaves the data alone. That split is the
whole reason these are separate volumes rather than directories in the image:

| | Lives in | Replaced on deploy |
| --- | --- | --- |
| Application code | the container image | **yes, every release** |
| Database | `postgres-data` volume | no |
| Uploaded media | `media-data` volume, at `/srv/journeymesh/storage/media` | no |
| Configuration | `/opt/journeymesh/.env` | no |
| Backups | `/opt/journeymesh/backups` | no |

Nothing is ever written to the image at runtime. If you find yourself wanting
to, that file belongs on a volume.

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

### Media backups

Uploaded images are backed up **separately** from the database, by
`deploy/backup_media.sh`. They are a different shape of problem: the database is
small and changes constantly, the media is large and mostly append-only, and a
database restore should never have to wait on a media restore to succeed.

```bash
crontab -e
# nightly at 03:30 UTC, after the database dump
30 3 * * * /opt/journeymesh/backup_media.sh >> /opt/journeymesh/backups/backup.log 2>&1
```

It keeps 30 days of `media-<stamp>.tar.gz` in `/opt/journeymesh/backups`, and
exits quietly when nothing has been uploaded yet rather than mailing you a
failure every night.

**Verify** an archive without touching the live volume, and **restore** it:

```bash
tar -tzf /opt/journeymesh/backups/media-<stamp>.tar.gz | head

gunzip -c /opt/journeymesh/backups/media-<stamp>.tar.gz \
  | jm exec -T backend tar -C /srv/journeymesh/storage -xf -
```

That overwrites files of the same name and leaves newer uploads in place.

### Moving to another VPS

Both volumes have to travel, and neither is in Git:

1. Take a fresh database dump and a fresh media archive (the two commands above).
2. Copy `.env` across by hand. It holds the secrets and is deliberately not in
   the repository or in any backup.
3. Bootstrap the new machine as this document describes, but **stop before the
   first deploy**.
4. Restore the database, then the media, then run the migrations
   (`jm --profile migrate up migrate`).
5. Start the stack and check `/api/v1/health`.
6. Open a page that shows an uploaded image. A database restored without its
   media looks healthy and renders broken pictures, so this is the check that
   actually tells you the move worked.

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
any application release. Deleting that volume means fresh issuance for every
domain on the VPS at once, which can hit Let's Encrypt's weekly limits.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| The workflow fails at "The shared proxy network exists" | The VPS was never bootstrapped, or the network was removed. `docker network create proxy`, then `cd /opt/proxy && docker compose up -d`. |
| The workflow warns `travelcrewai.caddy is missing` | The release succeeded but nothing routes the domain. Install the site file and run `/opt/proxy/reload.sh`. |
| The workflow fails at "Configure SSH" | `OVH_KNOWN_HOSTS` does not match the host, or the public key is not in the deploy user's `authorized_keys`. Re-run `ssh-keyscan`. |
| The workflow fails at "Pull the images" | The `deploy` user is not in the `docker` group. `sudo usermod -aG docker deploy`, then log out and back in. |
| The workflow fails at "Verify the public endpoint" | Run the checks in [Verifying HTTPS and routing](#verifying-https-and-routing) in order; the first that fails names the layer. |
| Caddy loops on certificates | DNS does not resolve to this VPS yet, a stale AAAA record exists, or port 80 is closed. `dig +short travelcrewai.com A`, `… AAAA`, `sudo ufw status`. |
| `reload.sh` fails at validate | The error names the file and line. Nothing was changed; the previous configuration is still serving. |
| `reload.sh` warns an upstream does not resolve | That application's stack is not running, or its web container is not on `proxy` under that alias. |
| `502 Bad Gateway` from travelcrewai.com | Travel Crew AI is down, or its frontend is not on the `proxy` network. `jm ps`, then `docker exec shared-caddy wget -qO- http://travelcrewai-web/healthz`. |
| A Caddy DNS error naming `travelcrewai-web` | The alias in `docker-compose.prod.yml` and the upstream in `sites/travelcrewai.caddy` disagree. They must be the same string. |
| A new site file has no effect | It does not end in `.caddy`, it was not reloaded, or it is outside `/opt/proxy/sites`. |
| A site answers with a different application | Two stacks use the same alias on `proxy`. `docker network inspect proxy`. |
| `www.travelcrewai.com` shows a certificate error | `www` has no A record, or had none when Caddy first tried. Add it, then `./reload.sh`. |
| `/api/v1/health` says `ephemeral_sqlite` | `POSTGRES_PASSWORD` is empty in `/opt/journeymesh/.env`. |
| `<public url>/health` returns HTML | Expected. That path is the container probe. The public API health path is `/api/v1/health`. |
| Migrations fail | `jm run --rm migrate` by hand to see the Alembic error in full. |
| The disk fills up | `docker system prune -af` and check `backups/` — retention is 14 days. |
| Everything is slow | Raise `WEB_CONCURRENCY` only if free memory allows. The default is 1 because this machine holds several applications. |

---

## What is where

| Path | What it is |
|---|---|
| `deploy/proxy/docker-compose.yml` | the shared reverse proxy; the only stack with host ports; names no application |
| `deploy/proxy/Caddyfile` | global options, shared snippets, `import /etc/caddy/sites/*.caddy` |
| `deploy/proxy/sites/travelcrewai.caddy` | Travel Crew AI's domains, redirect and upstream |
| `deploy/proxy/sites/_template.caddy.example` | the starting point for the next SaaS |
| `deploy/proxy/reload.sh` | validate, check upstreams, graceful reload |
| `deploy/proxy/.env.example` | template for `/opt/proxy/.env` (ACME e-mail only) |
| `deploy/docker-compose.prod.yml` | the Travel Crew AI stack; pulls, never builds, publishes nothing |
| `deploy/deploy.sh` | pull, migrate, up, verify — the release, by hand |
| `deploy/bootstrap-vps.sh` | one-time VPS preparation |
| `deploy/backup.sh` | nightly `pg_dump` with retention |
| `deploy/.env.prod.example` | template for `/opt/journeymesh/.env` |
| `/opt/journeymesh/.env` | the real secrets, on the VPS only, `chmod 600` |
| `/opt/journeymesh/.env.images` | the two image tags, rewritten by each release |
| `.github/workflows/ci.yml` | the quality gate, including `caddy validate` of the proxy config; releases nothing |
| `.github/workflows/deploy-production.yml` | the release |
| `deploy/HARDENING.md` | the manual GitHub and VPS hardening checklist |
