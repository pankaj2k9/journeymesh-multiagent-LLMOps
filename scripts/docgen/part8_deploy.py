"""Containers, Docker Compose, the production VPS, CI/CD, secrets and LangSmith."""

from __future__ import annotations

from docgen.builder import Guide
from docgen.repo import FACTS


def write(g: Guide) -> None:
    _docker(g)
    _compose(g)
    _vps(g)
    _ci(g)
    _cd(g)
    _secrets(g)
    _langsmith_setup(g)


# ---------------------------------------------------------------------------
def _docker(g: Guide) -> None:
    g.h1("Containers", page_break=True)

    g.h2("Why containers")
    g.definition(
        "Container image",
        "A layered, immutable filesystem plus the metadata needed to run a process "
        "from it. Two runs of the same image start from byte-identical filesystems.",
        "A sealed box holding the application and everything it needs to run. It "
        "behaves the same on a laptop, in CI and on a server, because it is the same "
        "box.",
    )
    g.p(
        "For JourneyMesh the decisive property is that the deployment target runs the "
        "same image that was built and health-checked locally. There is no build step "
        "on the server, no dependency resolution at deploy time, and no possibility of "
        "a Python or Node version differing between environments."
    )

    g.h2("The production image: three stages, one artefact")
    g.diagram(
        """
  Stage 1  frontend-builder      node:22-alpine
     npm ci                       exact tree from package-lock.json
     npm run build                -> /build/frontend/dist
                                        |
  Stage 2  backend-builder       python:3.11-slim
     pip install -r requirements.txt -> /opt/venv
                                        |
  Stage 3  application           python:3.11-slim
     apt: libpq5, curl only       no compiler, no npm, no source toolchain
     useradd journeymesh (10001)  the process never runs as root
     COPY /opt/venv          <--- from stage 2
     COPY backend/ .
     COPY .../frontend/dist  <--- from stage 1, into ./static
     rm -rf .env .env.* .git .pytest_cache .ruff_cache .venv htmlcov
     USER journeymesh
     HEALTHCHECK curl /api/v1/health
     ENTRYPOINT docker-entrypoint.sh
     CMD serve
""",
        "The three-stage production build. Only the third stage ships.",
    )

    g.h2("What each stage exists to leave behind")
    g.table(
        ["Stage", "Produces", "Left behind"],
        [
            ["frontend-builder", "The built React bundle",
             "node_modules, the frontend source, every build cache, npm itself"],
            ["backend-builder", "A populated virtual environment",
             "pip's build dependencies and wheel caches"],
            ["application", "The image that runs",
             "Nothing - this is what ships"],
        ],
        caption="Multi-stage build outputs.",
        widths=[1.3, 2.0, 2.5],
    )

    g.h2("Hardening")
    g.bullets([
        "A non-root user with a fixed uid of 10001 owns the application and runs the "
        "process.",
        "The runtime image installs only libpq5 and curl. There is no compiler, no "
        "npm and no source toolchain in the shipped image.",
        "Any developer environment file, VCS data, test cache and coverage output is "
        "removed explicitly in the final layer, and .dockerignore keeps them out of "
        "the build context in the first place.",
        "The image declares a HEALTHCHECK against the same cheap endpoint the hosting "
        "platform probes, so a locally-run container reports the same health the "
        "platform will see.",
    ])

    g.h2("The port, and why it is never hard-coded")
    g.p(
        "The image defaults PORT to 8000 for local use, and the entrypoint reads "
        "`PORT` from the environment with that default. Uvicorn is started with "
        "`--host 0.0.0.0 --port \"$PORT\"`. Binding 127.0.0.1 would make the container "
        "unreachable from outside; hard-coding 8000 would break on any platform that "
        "assigns a port."
    )
    g.code(
        """
PORT="${PORT:-8000}"
...
exec uvicorn app.main:app \\
  --host 0.0.0.0 \\
  --port "$PORT" \\
  ...
""",
        caption="Listing. From backend/docker-entrypoint.sh. Both parts matter: the "
                "bind address and the port.",
    )

    g.h2("The entrypoint's three modes")
    g.table(
        ["Command", "Behaviour"],
        [
            ["`serve` (the default)",
             "Optionally runs migrations, then execs uvicorn. Development mode adds "
             "reload"],
            ["`migrate`",
             "Runs `alembic upgrade head` and exits, so migrations can be run as a "
             "one-off job"],
            ["anything else",
             "Executed verbatim, so `docker compose run backend pytest -q` works"],
        ],
        caption="Entrypoint modes.",
        widths=[1.4, 4.4],
    )
    g.callout(
        "important",
        "`exec` matters. Without it the shell stays as process 1 and does not forward "
        "termination signals, so the platform's graceful shutdown becomes a hard kill "
        "and in-flight requests are dropped.",
    )

    g.h2("The development images")
    g.p(
        "frontend/Dockerfile builds the interface alone and serves it with nginx, "
        "using frontend/nginx.conf.template - which carries the same content security policy "
        "and the same theme-script hash as the Python application, so the two paths "
        "cannot drift. This split arrangement exists for local development and for a "
        "possible future split deployment; production uses the single image."
    )


# ---------------------------------------------------------------------------
def _compose(g: Guide) -> None:
    g.h1("Docker Compose - the Local Orchestrator", page_break=True)

    g.h2("What Compose is for")
    g.definition(
        "Docker Compose",
        "A tool that declares a set of containers, the network between them, their "
        "configuration and their startup dependencies in one file, and brings the "
        "whole set up or down with a single command.",
        "One file that describes your whole application, so starting it is one "
        "command instead of a page of instructions.",
    )
    g.p(
        "The value is not that it runs containers - Docker does that - but that it "
        "removes the setup instructions entirely. There is no \"install PostgreSQL "
        "16, create a database, create a user, run the migrations, then start two "
        "processes in the right order\" section in this project's README, because "
        "`docker compose up --build` is the whole of it."
    )

    g.h2("The three services")
    g.diagram(
        """
  docker-compose.yml
        |
        +-- frontend   nginx serving the React build
        |              proxies /api -> backend, so the browser has one origin
        |              published on localhost:5173
        |
        +-- backend    FastAPI + LangGraph + the agents
        |              published on localhost:8000
        |              reaches the database at db:5432
        |
        +-- migrate    the backend image, `alembic upgrade head`, then exits
        |
        +-- db         postgres:16-alpine
                       ./db/postgres-data -> /var/lib/postgresql/data

  Browser -> frontend -> backend -> db
""",
        "The local stack. Four services, one command.",
    )

    g.table(
        ["Service", "Built from", "Published", "Health"],
        [
            ["`db`", "`postgres:16-alpine`", "5432", "`pg_isready`"],
            ["`migrate`", "`backend/Dockerfile`", "-",
             "Exits 0, or the stack stops"],
            ["`backend`", "`backend/Dockerfile`", "8000", "`GET /health`"],
            ["`frontend`", "`frontend/Dockerfile`", "5173", "`GET /healthz`"],
        ],
        caption="The compose services.",
        widths=[1.0, 1.7, 1.0, 2.1],
    )

    g.h2("Ordering, and why it is not enough on its own")
    g.p(
        "Compose expresses ordering as conditions rather than delays, which removes "
        "the race a `sleep` only hides:"
    )
    g.table(
        ["Condition", "Means", "Used for"],
        [
            ["`service_healthy`",
             "Wait until the dependency's own health check passes",
             "`migrate` and `backend` wait for `db`; `frontend` waits for "
             "`backend`"],
            ["`service_completed_successfully`",
             "Wait until the dependency exits with status zero",
             "`backend` waits for `migrate`, so the API never starts against a "
             "schema it does not expect"],
        ],
        caption="The two conditions, and what each one removes.",
        widths=[1.5, 2.2, 2.1],
    )
    g.callout(
        "important",
        "Startup order is still not readiness. A database can answer a health probe "
        "a moment before it accepts a connection, and in production there is no "
        "Compose to sequence anything at all. The entrypoint therefore retries the "
        "connection itself for up to sixty seconds. Two independent protections: "
        "the orchestrator sequences, and the application is patient.",
    )

    g.h2("Data that survives")
    g.p(
        "The database is bind-mounted into the repository at "
        "`./db/postgres-data`, so `docker compose down` stops the containers and "
        "leaves the data exactly where it was. Rebuilding images or recreating "
        "containers does not touch it. Wiping it is a separate, deliberate command "
        "that says what it is doing."
    )

    g.h2("Hot reload")
    g.p(
        "`docker-compose.dev.yml` overrides the same three services rather than "
        "adding new ones: the backend builds with `RELOAD=true` and mounts the "
        "source, and the frontend runs the Vite dev server instead of nginx. The "
        "service names, the database and the migration job are identical, so the "
        "development stack and the production-shaped stack differ only in the two "
        "places they have to."
    )
    g.code(
        """
make dev-local
# = docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

#   http://localhost:5173   Vite, hot module replacement
#   http://localhost:8000   uvicorn --reload
#   PostgreSQL on 5432, data in ./db/postgres-data
""",
        caption="Listing. One command for local development.",
    )
    g.callout(
        "note",
        "Reload is a development convenience and never runs in production. The "
        "entrypoint only passes `--reload` when `RELOAD=true`, which the deployment "
        "never sets; production runs multiple workers instead.",
    )

    g.h2("The commands worth knowing")
    g.table(
        ["Command", "Does"],
        [
            ["`docker compose up --build`", "Build and start everything, logs in "
                                            "the foreground"],
            ["`docker compose up -d`", "The same, in the background"],
            ["`docker compose ps`", "What is running, and whether it is healthy"],
            ["`docker compose logs -f`", "Follow everything"],
            ["`docker compose logs -f backend`", "Follow one service"],
            ["`docker compose restart backend`", "Restart one service"],
            ["`docker compose down`", "Stop; the local database data is kept"],
            ["`docker compose config`", "Validate and print the resolved file"],
            ["`docker compose exec db psql -U journeymesh`", "A shell in the "
                                                             "database"],
        ],
        caption="Everyday Compose commands.",
        widths=[2.2, 3.6],
    )

    g.understand([
        "What Compose removes from a project's setup instructions.",
        "The difference between `service_healthy` and "
        "`service_completed_successfully`.",
        "Why ordering alone does not make an application robust.",
        "Why the development overlay overrides services rather than adding them.",
    ])


# ---------------------------------------------------------------------------
def _vps(g: Guide) -> None:
    g.h1("The Production VPS", page_break=True)

    g.h2("Why the local Compose file does not run in production")
    g.p(
        "This is the single most important thing to understand about the "
        "deployment, and the question an interviewer is most likely to ask. "
        "Production is a self-hosted OVHcloud VPS running a *second* Compose "
        "file, `deploy/docker-compose.prod.yml`, and not the one used locally."
    )
    g.p(
        "The local file is written for a developer: it builds images from the "
        "working tree, bind-mounts the database into the repository so you can see "
        "it, and publishes ports on your laptop so you can reach each service "
        "directly. Every one of those is wrong in production, where the artefact "
        "must be the one CI verified rather than whatever the working tree "
        "happens to contain, the data must survive outside any directory a "
        "deployment touches, and only the reverse proxy may be reachable."
    )
    g.p(
        "So the *architecture* transfers and the *file* does not. The service "
        "names, the health gates, the ordering and the environment variable names "
        "are identical - which is what makes local debugging transferable - and "
        "the three developer conveniences are replaced."
    )

    g.table(
        ["Local Compose", "Production Compose", "Why it changes"],
        [
            ["`build:` from the Dockerfiles",
             "`image:` pulled from GHCR, tagged with the commit SHA",
             "The artefact CI verified must be the artefact that serves traffic; a "
             "rebuild on the VPS could differ"],
            ["`./db/postgres-data` bind mount",
             "The `postgres-data` named volume",
             "Data must not live inside a directory a deployment rewrites"],
            ["`ports: 5173:80` and `8000:8000`",
             "Only Caddy publishes 80 and 443",
             "An application port on the public internet is a port you have to "
             "defend; PostgreSQL is bound to `127.0.0.1`"],
            ["No TLS",
             "Caddy terminates HTTPS with a Let's Encrypt certificate",
             "It obtains and renews the certificate itself, so there is no cron "
             "job and no renewal to forget"],
            ["`migrate` runs as part of `up`",
             "`migrate` is a profile the release runs explicitly, to completion",
             "A failed migration must stop the release while the old containers "
             "still serve, rather than racing the new ones"],
        ],
        caption="How each local convenience is replaced. Nothing is lost; the "
                "developer affordances become production properties.",
        widths=[1.4, 1.9, 2.5],
    )

    g.h2("The vocabulary")
    g.definition(
        "VPS",
        "A virtual private server: one rented Linux machine with its own IP "
        "address, its own kernel and root access, on which you install and operate "
        "everything yourself.",
        "A computer in a datacentre that nobody else logs into.",
    )
    g.definition(
        "Container registry (GHCR)",
        "A server that stores built Docker images by name and tag. GitHub Actions "
        "pushes to it; the VPS pulls from it. The GitHub Container Registry is "
        "used here because the repository already lives on GitHub, so the "
        "workflow needs no extra credential.",
        "A shelf that CI puts finished images on and the server takes them from.",
    )
    g.definition(
        "Shared reverse proxy (Caddy)",
        "The single process that accepts every public connection on the VPS, "
        "terminates TLS with certificates it obtains and renews itself, and "
        "forwards each domain to a container on a shared Docker network. It is its "
        "own Compose project in `/opt/proxy`, not part of any application.",
        "The building's front door, not one flat's.",
    )
    g.definition(
        "External Docker network",
        "A network created once on the host - `docker network create proxy` - and "
        "declared `external: true` by every stack that joins it. No stack owns it, "
        "so bringing one down never removes it or disturbs the others.",
        "A corridor the flats open onto, which none of them owns.",
    )

    g.h2("The production architecture")
    g.p(
        "This VPS is sized to host about three small SaaS applications, and only "
        "one container on a machine can bind port 443. So TLS is a property of the "
        "*server*, not of any application on it, and the deployment is two "
        "independent Compose projects rather than one."
    )
    g.diagram(
        """
                            Internet
                               |
                               | :80  :443
                               v
 +=============================================================+
 |                     OVHcloud VPS                            |
 |                                                             |
 |  /opt/proxy                                                 |
 |  +--------------------+                                     |
 |  | shared-caddy       |  the only published ports on the    |
 |  | Let's Encrypt      |  whole machine                      |
 |  +---------+----------+                                     |
 |            |                                                |
 |    ....... proxy network (external) ...................     |
 |            |                |                 |             |
 |            v                v                 v             |
 |  +--------------------+  (saas2-frontend) (saas3-frontend)  |
 |  | journeymesh-       |   later            later            |
 |  |   frontend         |  nginx + React build                |
 |  | /healthz           |  proxies /api to the backend        |
 |  +---------+----------+                                     |
 |            |                                                |
 |    ....... journeymesh_default network ................     |
 |            v                                                |
 |  +--------------------+                                     |
 |  | journeymesh-backend|  FastAPI + LangGraph                |
 |  | /health            |  expose 8000, no host port          |
 |  +---------+----------+                                     |
 |            |                                                |
 |            v                                                |
 |  +--------------------+                                     |
 |  | journeymesh-db     |  PostgreSQL 16, named volume        |
 |  |                    |  no host port at all                |
 |  +--------------------+                                     |
 +=============================================================+
""",
        "Two Compose projects on one host. Exactly one container is reachable "
        "from the internet, and it belongs to neither application.",
    )

    g.p(
        "A container joins the shared network only if something outside its own "
        "stack has to reach it. That is one container: nginx."
    )
    g.table(
        ["Container", "Own network", "Shared proxy network", "Host port"],
        [
            ["shared-caddy", "-", "Yes", "80, 443, 443/udp"],
            ["journeymesh-frontend", "Yes",
             "Yes, aliased `journeymesh-frontend`", "None"],
            ["journeymesh-backend", "Yes", "No", "None"],
            ["journeymesh-db", "Yes", "Never", "None"],
        ],
        caption="Reachability, stated as a table because it is the security "
                "boundary. `deploy/docker-compose.prod.yml` publishes nothing, and "
                "a CI check fails the build if that ever changes.",
        widths=[1.6, 1.0, 1.9, 1.3],
    )

    g.table(
        ["Service", "Image", "Health", "Host port"],
        [
            ["frontend", "GHCR, built from `/frontend`", "`/healthz`", "None"],
            ["backend", "GHCR, built from `/backend`", "`/health`", "None"],
            ["db", "`postgres:16-alpine`", "`pg_isready`", "None"],
            ["migrate", "The backend image, `profiles: [migrate]`", "-", "None"],
        ],
        caption="The application stack. `deploy/docker-compose.prod.yml` is "
                "committed, so the production topology is reviewed like code rather "
                "than typed into a dashboard.",
        widths=[1.0, 2.2, 1.2, 1.0],
    )

    g.callout(
        "important",
        "The alias matters more than the container name. The shared Caddyfile "
        "dials `journeymesh-frontend`, which is a network alias declared by the "
        "frontend service - so the container can be renamed without breaking "
        "routing, and three SaaS stacks cannot collide on one name.",
    )

    g.h2("Why the proxy is a separate Compose project")
    g.bullets([
        "It serves every application on the VPS. A JourneyMesh release must not "
        "restart TLS for SaaS 2 and SaaS 3.",
        "It has no `depends_on` pointing at any application, so it starts and "
        "stays up whether or not anything is behind it - a domain with nothing "
        "deployed returns 502, which is the honest answer.",
        "The deploy workflow ships nothing to `/opt/proxy` and restarts nothing "
        "there. A test asserts that.",
        "Adding a SaaS is one domain variable, one Caddyfile block and a reload. "
        "Nothing already running is touched.",
    ])

    g.h2("Why the frontend and backend are separate containers")
    g.bullets([
        "They scale for different reasons. Serving static files is cheap; running "
        "five agents against three providers is not.",
        "They fail for different reasons, and a failed frontend build should not "
        "take the API down with it.",
        "They deploy independently, so a copy change on the About page does not "
        "restart the workflow engine - the release workflow can ship either half "
        "alone.",
        "The interface is a static bundle behind nginx, which is a different kind "
        "of thing from a Python application and is best operated as one.",
    ])
    g.callout(
        "note",
        "The single-container image at the repository root still exists and is "
        "still built in CI. It is the right shape when a host allows only one "
        "process, and it is the reason the SPA fallback lives in the FastAPI "
        "application as well as in nginx. It is not what the VPS runs.",
    )

    g.h2("Ports")
    g.p(
        "`PORT` comes from the environment and the entrypoint binds every "
        "interface. Both halves matter: binding `127.0.0.1` makes the container "
        "unreachable from nginx, which is a different container, and hard-coding "
        "`8000` breaks the moment the port is assigned elsewhere."
    )
    g.code(
        """
PORT="${PORT:-8000}"
...
exec uvicorn app.main:app \\
  --host 0.0.0.0 \\
  --port "$PORT" \\
  --workers "$WORKERS" \\
  --proxy-headers --forwarded-allow-ips '*'
""",
        caption="Listing. `--proxy-headers` is what makes the application see the "
                "browser's scheme and address rather than Caddy's.",
    )

    g.h2("TLS")
    g.p(
        "Caddy requests a certificate for `JOURNEYMESH_DOMAIN` on first start and "
        "renews it roughly thirty days before expiry, unattended. The certificates "
        "live in the `caddy-data` volume, which belongs to `/opt/proxy` and is "
        "untouched by any application release. It is the one volume besides the "
        "database that must not be deleted casually: a fresh start means fresh "
        "certificate requests, and Let's Encrypt rate-limits those per domain per "
        "week."
    )
    g.callout(
        "important",
        "The domain must resolve to the VPS before the first deployment. Let's "
        "Encrypt validates over HTTP on port 80, so DNS and the firewall have to "
        "be right first. Getting it wrong repeatedly costs a rate limit, not just "
        "a retry.",
    )

    g.h2("Health checks")
    g.p(
        "`GET /health` returns `{\"status\": \"healthy\"}` and nothing else. It "
        "calls no model, runs no graph, invokes no MCP tool, contacts no travel "
        "provider, does not talk to LangSmith and does not open a database "
        "connection. Docker restarts an unhealthy container, and the release "
        "workflow waits for every container to report healthy before it declares "
        "success."
    )
    g.callout(
        "important",
        "A health check that touched a provider would fail during that provider's "
        "outage, and Docker would restart a perfectly healthy container - turning "
        "a partial degradation into a total one. `/api/v1/health` remains the "
        "richer, versioned endpoint for humans; `/health` is for the machine.",
    )
    g.p(
        "The container health check cannot prove that DNS resolves or that the "
        "certificate is valid, so the release additionally polls "
        "`https://<domain>/health` from GitHub's runners - from the internet, the "
        "way a browser sees it."
    )

    g.h2("Migrations at deploy time")
    g.p(
        "`alembic upgrade head` runs in a one-shot `migrate` container, to "
        "completion, after the new images are pulled and before the new "
        "application containers are started. If it fails, the release stops there "
        "and the previous containers keep serving. That ordering is what makes a "
        "schema change safe."
    )
    g.diagram(
        """
  build images in Actions, push to GHCR
       |
       v
  ssh to the VPS, pin the SHA tags, docker compose pull
       |
       v
  docker compose run --rm migrate
       |                    |
       | success            | failure
       v                    v
  docker compose up -d   release stops here
       |                 previous containers
       v                 keep serving
  every health check passes
       |
       v
  https://<domain>/health -> 200
""",
        "The release sequence. A failed migration never produces a running "
        "application on the wrong schema.",
    )
    g.bullets([
        "Migrations are additive. Nothing in the deployment path drops a table, "
        "drops a database or downgrades to base - and a test asserts those strings "
        "appear nowhere in the workflow.",
        "A release never recreates the PostgreSQL volume and never reseeds data.",
        "No demo or seed data is written to production.",
        "`deploy/backup.sh` writes a compressed `pg_dump` nightly from the deploy "
        "user's crontab and keeps fourteen days of them.",
    ])


def _ci(g: Guide) -> None:
    g.h1("Continuous Integration", page_break=True)

    g.p(
        "CI runs on every pull request and every push to `main`. It is the gate: "
        "four jobs feed a fifth that fails if any of them did, and nothing is "
        "released while it is red."
    )

    g.diagram(
        """
  push / pull request
        |
        +---------------+---------------+---------------+
        |               |               |               |
        v               v               v               v
   frontend         backend         security         (waits)
   npm ci           pip install     no .env committed
   tsc --noEmit     ruff            no credential in the repo
   vitest           pytest          pip-audit
   vite build       offline eval    npm audit (informational)
   assert dist/     alembic --sql
        |               |               |
        +-------+-------+               |
                |                       |
                v                       |
             docker                     |
   backend image  -> start -> /health   |
   frontend image -> start -> /healthz  |
   combined image -> build              |
   docker compose config                |
   three services declared              |
                |                       |
                +-----------+-----------+
                            |
                            v
                      quality gate
                            |
                    pass -> releasable
                    fail -> nothing happens
""",
        "The CI pipeline. Every arrow into the gate must be green.",
    )

    g.h2("What each job actually proves")
    g.table(
        ["Job", "Proves"],
        [
            ["Frontend",
             "Types compile, 64 tests pass, the production build succeeds and "
             "really produced an entry point"],
            ["Backend",
             "Lint is clean, every module imports, 238 tests pass, the offline "
             "evaluation passes at its declared thresholds, and the Alembic "
             "configuration renders offline"],
            ["Security",
             "No environment file is committed, no credential-shaped string appears "
             "anywhere in the repository, and the dependency audit is clean"],
            ["Docker",
             "Both service images build, start and answer their health path; the "
             "combined image builds; both compose files parse and declare the three "
             "expected services"],
        ],
        caption="The four jobs.",
        widths=[1.0, 4.8],
    )

    g.callout(
        "important",
        "The compose validation is not decoration. A compose file that does not "
        "parse is a broken local development environment for everyone who clones "
        "the repository, and it is the kind of breakage that is invisible until "
        "someone tries to start work.",
    )

    g.h2("Why the Docker job starts the containers")
    g.p(
        "Building an image proves the Dockerfile is valid. Starting it and asking "
        "it for its health path proves the entrypoint works, the port binding is "
        "right, the dependencies are actually present in the runtime stage and the "
        "application can reach a running state. Those are the failures that "
        "otherwise appear for the first time during a deployment."
    )


# ---------------------------------------------------------------------------
def _cd(g: Guide) -> None:
    g.h1("Continuous Delivery, by Hand", page_break=True)

    g.h2("CI and CD are different things")
    g.table(
        ["", "Continuous integration", "Continuous delivery"],
        [
            ["Answers", "Is this change correct?", "Should this change be live?"],
            ["Triggered by", "Every push and pull request", "A person"],
            ["Workflow", "`ci.yml`", "`deploy.yml`"],
            ["Fails means", "The change is not ready", "Production was not "
                                                       "changed"],
            ["Runs", "Automatically, always", "`workflow_dispatch` only"],
        ],
        caption="The two halves of the pipeline.",
        widths=[1.0, 2.4, 2.4],
    )

    g.definition(
        "workflow_dispatch",
        "A GitHub Actions trigger that only fires when a person - or an API call "
        "on their behalf - starts the workflow from the Actions tab, optionally "
        "supplying inputs.",
        "A button. Nothing runs until somebody presses it.",
    )

    g.h2("Why production is released by hand")
    g.p(
        "Deploying on every push to `main` is a defensible choice for a service "
        "with strong tests and easy rollback. It is the wrong choice here, for "
        "reasons worth being able to state:"
    )
    g.numbered([
        "A merge is a statement about code, not about timing. Releasing should be a "
        "separate decision, made when someone is available to watch it.",
        "Migrations run at deploy time. A schema change deserves a person's "
        "attention at the moment it is applied.",
        "The evaluation suite is deterministic but the system is not: a person "
        "checking the deployed result is a real control.",
        "It makes the pipeline honest. \"CI passed\" and \"this is in production\" "
        "become two distinct, visible facts.",
    ])
    g.callout(
        "warning",
        "This only works if nothing else is watching the repository. There is no "
        "auto-deploy to switch off here - the VPS pulls only when the workflow "
        "tells it to - but a webhook or a git-pull cron on the server would make "
        "the manual workflow theatre. Nothing on the VPS reaches out to GitHub.",
    )

    g.h2("The release path")
    g.diagram(
        """
  developer
      |
      v
  push / merge to main
      |
      v
  GitHub Actions CI          frontend | backend | security | docker
      |                              \    |    /    /
      v                               quality gate
  CI passes
      |
      |   ... a person decides ...
      v
  Actions -> "Deploy to OVHcloud VPS" -> Run workflow
      |
      +-- refuse unless the branch is main
      +-- refuse unless "deploy" was typed
      +-- refuse unless every VPS secret and variable is set
      +-- print the commit SHA being released
      |
      v
  build backend and frontend images in parallel
  push to ghcr.io/<owner>/journeymesh-*:<sha>
      |
      v
  ssh to the VPS  (host key pinned by VPS_KNOWN_HOSTS)
      |
      +-- ship docker-compose.prod.yml, deploy.sh, backup.sh
      +-- refuse if the shared proxy network is missing
      +-- pin the SHA tags in .env.images
      +-- docker compose pull
      |
      v
  docker compose run --rm migrate
      |
      v
  docker compose up -d, wait for every health check
      |
      v
  poll https://<domain>/health from the internet
      |
      v
  docker logout, prune images older than a week
      |
      v
  production
""",
        "From a merge to a release. Everything above the dashed decision is "
        "automatic; nothing below it happens without a person.",
    )

    g.h2("Why the VPS never builds")
    g.p(
        "Both images are built on GitHub\'s runners and pushed to GHCR tagged with "
        "the commit SHA. The VPS pulls those exact tags. It never has a checkout, "
        "never runs a build and never needs a compiler, which means three things "
        "at once: the artefact CI verified is the artefact that serves traffic, a "
        "release is a pull rather than a fifteen-minute build on a small machine, "
        "and a rollback is a tag change rather than a rebuild."
    )
    g.code(
        """
# in .env.images on the VPS, rewritten by every release
BACKEND_IMAGE=ghcr.io/<owner>/journeymesh-backend:9f2c1ab...
FRONTEND_IMAGE=ghcr.io/<owner>/journeymesh-frontend:9f2c1ab...

# a rollback, in full
nano .env.images        # put back the previous SHA
docker compose -f docker-compose.prod.yml --env-file .env \\
  --env-file .env.images pull && docker compose ... up -d
""",
        caption="Listing. Immutable tags are what make the rollback a two-line "
                "operation with no git history involved.",
    )
    g.callout(
        "note",
        "Migrations do not roll back with the image. If the bad release added a "
        "column the previous image ignores it; if it dropped one, the fix is a "
        "restore from the nightly dump. This is why migrations are additive.",
    )

    g.h2("Authentication")
    g.definition(
        "Deploy key",
        "An SSH key pair created for one purpose, whose private half is a GitHub "
        "Actions secret and whose public half is in the deploy user\'s "
        "`authorized_keys` on the VPS. It is separate from any human\'s key, so "
        "either can be revoked without disturbing the other.",
        "A key cut for the delivery driver, not a copy of yours.",
    )
    g.definition(
        "Host key pinning",
        "`VPS_KNOWN_HOSTS` holds the server\'s public host key, and the workflow "
        "runs with `StrictHostKeyChecking yes`. SSH refuses to connect to anything "
        "that answers with a different key.",
        "Checking the face at the door, not just the address on the envelope.",
    )
    g.table(
        ["Name", "Kind", "Why"],
        [
            ["`VPS_SSH_KEY`", "GitHub Actions **secret**",
             "It can log in and run Docker. Scoped to the unprivileged deploy "
             "user, not root"],
            ["`VPS_KNOWN_HOSTS`", "GitHub Actions **secret**",
             "Without it, a redirected DNS record would collect the deploy key"],
            ["`GITHUB_TOKEN`", "Provided by Actions, not stored",
             "Logs the VPS in to GHCR for the length of the job, then logs out, so "
             "no long-lived registry password lives on the server"],
            ["`VPS_HOST`, `VPS_USER`, `VPS_PORT`", "Repository **variables**",
             "An address and a username identify; they do not grant access"],
            ["`VPS_APP_DIR`", "Repository variable", "`/opt/journeymesh`"],
            ["`PUBLIC_URL`", "Repository variable",
             "Polled for health after the release, from the internet"],
        ],
        caption="Secrets are for things that grant access; variables are for things "
                "that merely identify.",
        widths=[1.7, 1.6, 2.5],
    )

    g.h2("What the workflow guarantees")
    g.bullets([
        "It refuses to run from any branch but `main`.",
        "It refuses to run unless the operator types `deploy`, so a mis-click "
        "cannot release.",
        "It prints the commit SHA, author and subject being released.",
        "Every remote script runs under `bash -euo pipefail`, so a failed command "
        "on the VPS fails the job rather than being reported as success.",
        "It waits for every container health check, then polls the public HTTPS "
        "endpoint, and fails if either never becomes healthy.",
        "It pins the SSH host key, so it will not hand the deploy key to an "
        "impostor.",
        "It never writes the production environment file - `/opt/journeymesh/.env` "
        "is owned by the VPS and holds the only copy of the production secrets.",
        "It never echoes a secret - the token is read from the environment into the "
        "CLI and never interpolated into a log line or the job summary.",
        "It contains no destructive database operation, and a test asserts that.",
    ])

    g.h2("When something fails")
    g.table(
        ["Failure", "What happens", "What to do"],
        [
            ["CI fails", "Nothing is released; the deploy workflow is a separate "
                         "manual action and simply is not run",
             "Fix the change and push again"],
            ["The confirm field is wrong", "The job stops at the first step",
             "Re-run with `deploy` typed"],
            ["The migration fails", "The deployment fails; the previous release "
                                    "keeps serving",
             "Fix the revision, push, re-run CI, release again"],
            ["The image build fails", "Nothing reaches the VPS; the running "
                                       "containers are untouched",
             "Read the build job log in Actions"],
            ["SSH is refused", "The job stops before anything is pulled",
             "`VPS_KNOWN_HOSTS` is stale or the deploy key is not installed; "
             "re-run `ssh-keyscan`"],
            ["Caddy cannot get a certificate",
             "The containers run but HTTPS does not answer",
             "The domain does not resolve to the VPS, or port 80 is closed"],
            ["Health never returns 200", "The workflow fails after its polling "
                                         "window",
             "Check the service logs; the previous release is still serving"],
            ["The frontend loads but the API is unreachable",
             "nginx cannot reach the backend container, or the CSP `connect-src` "
             "disagrees with the real origin",
             "`docker compose logs frontend backend`. Same-origin is the default: "
             "`VITE_API_BASE_URL` should stay empty"],
        ],
        caption="Failure modes of the release path.",
        widths=[1.4, 2.3, 2.1],
    )

    g.understand([
        "Why the local Compose file is not the production one, and what each "
        "difference buys.",
        "Why images are built in CI and pulled by the VPS, never built on it.",
        "Why every release is an immutable SHA tag, and what that makes a "
        "rollback.",
        "Why `/health` must be cheap, and why a container health check is not "
        "enough on its own.",
        "Why migrations run to completion before the new containers start.",
        "The difference between CI and CD, and why CD here is a button.",
        "Why the SSH host key is pinned, and what goes wrong without it.",
    ])


def _secrets(g: Guide) -> None:
    g.h1("Secrets Across the Whole Pipeline", page_break=True)

    g.table(
        ["Secret", "Lives in", "Never in"],
        [
            ["`POSTGRES_PASSWORD`",
             "`/opt/journeymesh/.env` on the VPS, `chmod 600`; a local `.env` for "
             "development",
             "Git, the React bundle, logs, traces"],
            ["`DATABASE_URL`",
             "Assembled by the production Compose file from `POSTGRES_*`; a local "
             "`.env` for development",
             "Git, the React bundle, logs, traces, the database"],
            ["`GROQ_API_KEY`", "`/opt/journeymesh/.env` on the VPS",
             "Git, the bundle, logs, traces"],
            ["`TAVILY_API_KEY`", "`/opt/journeymesh/.env` on the VPS",
             "Git, the bundle, logs"],
            ["`AVIATIONSTACK_API_KEY`", "`/opt/journeymesh/.env` on the VPS",
             "Git, the bundle, logs"],
            ["`OPENWEATHER_API_KEY`", "`/opt/journeymesh/.env` on the VPS",
             "Git, the bundle, logs"],
            ["`LANGSMITH_API_KEY`", "`/opt/journeymesh/.env` on the VPS",
             "Git, the bundle, logs"],
            ["`VPS_SSH_KEY`", "A GitHub Actions secret only",
             "Git, the VPS, any log line, the job summary"],
        ],
        caption="Where each secret lives and where it must never appear.",
        widths=[1.6, 2.1, 2.1],
    )

    g.h2("The five defences")
    g.numbered([
        "`.gitignore` excludes `.env` and every variant of it.",
        "`.env.example` ships with every secret blank, and the settings layer treats a "
        "blank value as absent rather than as an empty string.",
        "CI fails the build if an environment file is committed or if a "
        "credential-shaped string appears anywhere outside the excluded workflow, "
        "compose and test paths.",
        "The output guard scans every response for key-shaped strings and PostgreSQL "
        "URLs before it is stored or returned.",
        "The Tool Guard strips a fixed set of forbidden argument names before any tool "
        "call leaves the process, and records only that a redaction happened.",
    ])

    g.callout(
        "warning",
        "The secret scan had to be tightened during development because it matched its "
        "own regular expression and the de-literalised fixtures used in the test "
        "suite. The patterns now require a realistic key body, and test fixtures are "
        "constructed by concatenation so that no credential-shaped literal exists in "
        "the repository at all.",
    )


# ---------------------------------------------------------------------------
def _langsmith_setup(g: Guide) -> None:
    g.h1("LangSmith Configuration", page_break=True)

    g.h2("What it gives you")
    g.p(
        "LangSmith records each graph run as a tree: the entry branch, the supervisor's "
        "decision, each specialist, each tool call, the guardrails and the evaluation. "
        "For an agentic system that is the difference between \"the answer was wrong\" "
        "and \"the supervisor selected four agents, the hotel agent's provider timed "
        "out, and the budget was therefore computed from estimates\"."
    )

    g.h2("Configuration")
    g.table(
        ["Variable", "Purpose", "Required?"],
        [
            ["`LANGSMITH_TRACING`", "Turns tracing on", "No; defaults off"],
            ["`LANGSMITH_API_KEY`", "Authenticates to the service",
             "Only if tracing is on"],
            ["`LANGSMITH_PROJECT`", "Groups runs", "No"],
            ["`LANGSMITH_ENDPOINT`", "An alternative host", "No"],
        ],
        caption="LangSmith variables. `langsmith_enabled` is true only when tracing is "
                "on and a key is present.",
        widths=[1.6, 2.6, 1.6],
    )

    g.h2("Modularity is enforced, not intended")
    g.bullets([
        "`configure()` is called once at start-up and is a no-op when tracing is off.",
        "`span()` is the only tracing call anywhere in the domain layer, and becomes a "
        "no-op context manager when tracing is unavailable.",
        "The tracing import is loaded through a `_load_trace()` seam, so a missing or "
        "broken library degrades to the no-op rather than raising at import time.",
        "A test asserts that a full journey completes with tracing disabled, and "
        "another asserts it completes with tracing enabled and a fabricated key.",
    ])
    g.callout(
        "note",
        "That seam exists because of a real defect: an early test injected a fake "
        "`langsmith.run_helpers` module, which broke an unrelated langchain_core import "
        "with a `get_tracing_context` error. Loading the tracing function through a "
        "seam the test can patch fixed it without weakening the real code path.",
    )

    g.h2("What is sent")
    g.p(
        "Only allowlisted metadata: trip and request identifiers, agent and node names, "
        "revision numbers, durations, guardrail rule names and evaluation dimension "
        "names. Values are redacted for personal data and truncated. The traveller's "
        "free text, tool arguments and provider payloads are never sent."
    )

    g.understand([
        "Why the production image has three stages and what each one leaves behind.",
        "Why the port comes from the environment and the bind address is 0.0.0.0.",
        "Why deployment is triggered by CI completion rather than by a push.",
        "Why the platform's own auto-deploy must be off.",
        "Which secrets live where, and the five defences that keep them there.",
        "Why LangSmith can never fail a journey.",
    ])
