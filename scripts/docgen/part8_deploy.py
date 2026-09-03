"""Containers, Docker Compose, Railway, CI/CD, secrets and LangSmith."""

from __future__ import annotations

from docgen.builder import Guide
from docgen.repo import FACTS


def write(g: Guide) -> None:
    _docker(g)
    _compose(g)
    _railway(g)
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
def _railway(g: Guide) -> None:
    g.h1("Railway - the Production Platform", page_break=True)

    g.h2("Why Compose does not run in production")
    g.p(
        "This is the single most important thing to understand about the "
        "deployment, and the question an interviewer is most likely to ask. "
        "Railway does not execute `docker-compose.yml`. It is not a Compose host."
    )
    g.p(
        "Compose is a *single-host* orchestrator: one machine, one Docker daemon, "
        "one bridge network, containers that find each other by service name, and "
        "bind mounts into that machine's filesystem. Every one of those assumptions "
        "is wrong for a managed platform, which runs each component independently, "
        "may move it between machines, scales it separately, gives it its own "
        "domain and TLS, and has its own notion of volumes, health and rollout."
    )
    g.p(
        "So the *architecture* transfers and the *file* does not. Each Compose "
        "service becomes a Railway service, and the Compose-specific machinery is "
        "replaced by the platform's own equivalent."
    )

    g.table(
        ["Compose concept", "Railway equivalent", "Why it changes"],
        [
            ["`depends_on: service_healthy`",
             "A health check path per service, plus deploy ordering",
             "Services deploy independently; there is no single daemon sequencing "
             "them"],
            ["`migrate` one-shot service",
             "The backend's pre-deploy command",
             "The platform runs it before the new container takes traffic, and "
             "fails the deploy if it fails"],
            ["`./db/postgres-data` bind mount",
             "The PostgreSQL service's managed volume",
             "There is no host filesystem to bind to"],
            ["`db:5432` on the bridge network",
             "`DATABASE_URL` reference variable over private networking",
             "Services are addressed at `<service>.railway.internal`, and the "
             "credential is resolved rather than written"],
            ["`ports: 5173:80`",
             "A generated public domain with TLS",
             "The platform terminates HTTPS and assigns the container's port"],
            ["`docker compose up --build`",
             "One deploy per service, from the repository",
             "Each service has its own build, its own rollout and its own history"],
        ],
        caption="How each Compose concept translates. Nothing is lost; everything "
                "moves.",
        widths=[1.4, 1.9, 2.5],
    )

    g.h2("The vocabulary")
    g.definition(
        "Railway service",
        "One deployable component within a project: a source (a repository "
        "directory, or a database image), a build, its own environment variables, "
        "its own domain if it needs one, and its own deployment history.",
        "One box in your architecture diagram, running.",
    )
    g.definition(
        "Railway environment",
        "A named, isolated copy of every service in a project, with its own "
        "variables and its own data - `production` and `staging` are environments, "
        "not projects.",
        "The same set of services again, with different settings and different "
        "data.",
    )
    g.definition(
        "Private networking",
        "An internal network joining the services in a project, where each is "
        "reachable at `<service>.railway.internal` without traffic leaving the "
        "platform or crossing the public internet.",
        "A phone line between your own services that nobody outside can dial.",
    )

    g.h2("The production architecture")
    g.diagram(
        """
                            Internet
                               |
          +--------------------+--------------------+
          |                                         |
          v                                         v
 +--------------------+                    +--------------------+
 | frontend service   |      HTTPS / API   | backend service    |
 | nginx + React      | -----------------> | FastAPI + LangGraph|
 | public domain      |   (the browser     | public domain      |
 | /healthz           |    calls this)     | /health            |
 +--------------------+                    +---------+----------+
                                                     |
                                            private networking
                                            postgres.railway.internal
                                                     |
                                                     v
                                           +--------------------+
                                           | PostgreSQL service |
                                           | managed volume     |
                                           | no public domain   |
                                           +--------------------+
""",
        "Three Railway services in one project. Only two are reachable from the "
        "internet.",
    )

    g.table(
        ["Service", "Root directory", "Builder", "Health", "Public"],
        [
            ["frontend", "`/frontend`", "Dockerfile", "`/healthz`", "Yes"],
            ["backend", "`/backend`", "Dockerfile", "`/health`", "Yes"],
            ["Postgres", "-", "Railway image", "Platform-managed", "No"],
        ],
        caption="The three services. `railway.json` in each directory declares the "
                "build and the health check so the configuration is reviewed like "
                "code rather than clicked into a dashboard.",
        widths=[1.0, 1.3, 1.2, 1.2, 0.8],
    )

    g.h2("Why the frontend and backend are separate services")
    g.bullets([
        "They scale for different reasons. Serving static files is cheap; running "
        "five agents against three providers is not.",
        "They fail for different reasons, and a failed frontend build should not "
        "take the API down with it.",
        "They deploy independently, so a copy change on the About page does not "
        "restart the workflow engine.",
        "The interface is a static bundle behind nginx, which is a different kind "
        "of thing from a Python application and is best operated as one.",
    ])
    g.callout(
        "note",
        "The single-container image at the repository root still exists and is "
        "still built in CI. It is the right shape when a platform allows only one "
        "service, and it is the reason the SPA fallback lives in the FastAPI "
        "application as well as in nginx. It is not what the Railway deployment "
        "uses.",
    )

    g.h2("Ports")
    g.p(
        "Railway assigns the port and injects it as `PORT`. The entrypoint reads it "
        "and binds every interface. Both halves matter: binding `127.0.0.1` makes "
        "the container unreachable from the platform's router, and hard-coding "
        "`8000` breaks on any platform that assigns a port."
    )
    g.code(
        """
PORT="${PORT:-8000}"
...
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --workers "$WORKERS" \
  --proxy-headers --forwarded-allow-ips '*'
""",
        caption="Listing. The default is for local use only; production always "
                "supplies PORT.",
    )

    g.h2("Health checks")
    g.p(
        "`GET /health` returns `{\"status\": \"healthy\"}` and nothing else. It "
        "calls no model, runs no graph, invokes no MCP tool, contacts no travel "
        "provider, does not talk to LangSmith and does not open a database "
        "connection. Railway waits for a 200 before routing traffic to a new "
        "deployment, so a container that cannot start never receives a request."
    )
    g.callout(
        "important",
        "A health check that touched a provider would fail during that provider's "
        "outage, and the platform would restart a perfectly healthy container - "
        "turning a partial degradation into a total one. `/api/v1/health` remains "
        "the richer, versioned endpoint for humans; `/health` is for the platform.",
    )
    g.p(
        "A deployment health check is not uptime monitoring. It answers \"is this "
        "new release safe to send traffic to?\", once. Continuous monitoring is a "
        "separate concern and is not implemented here."
    )

    g.h2("Migrations at deploy time")
    g.p(
        "`alembic upgrade head` runs as the backend's **pre-deploy command**: after "
        "the image is built, before the new container takes traffic. If it fails, "
        "the deployment fails and the previous release keeps serving. That ordering "
        "is what makes a schema change safe."
    )
    g.diagram(
        """
  build image
       |
       v
  pre-deploy:  alembic upgrade head
       |                    |
       | success            | failure
       v                    v
  start container      deployment fails
       |               previous release
       v               keeps serving
  /health -> 200
       |
       v
  traffic switches over
""",
        "The deploy sequence. A failed migration never produces a running "
        "application on the wrong schema.",
    )
    g.bullets([
        "Migrations are additive. Nothing in the deployment path drops a table, "
        "drops a database or downgrades to base - and a test asserts those strings "
        "appear nowhere in the workflow.",
        "Deploying an application service does not touch the database. PostgreSQL "
        "is a separate service with its own lifecycle and its own volume.",
        "No demo or seed data is written to production.",
    ])


# ---------------------------------------------------------------------------
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
        "This only works if the platform's own auto-deploy is switched off. If "
        "Railway is also watching the repository, every merge deploys anyway and "
        "the manual workflow is theatre. Disabling it in each service's settings is "
        "part of the setup, not an optional extra.",
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
  Actions -> "Deploy to Railway" -> Run workflow
      |
      +-- refuse unless the branch is main
      +-- refuse unless "deploy" was typed
      +-- print the commit SHA being released
      |
      v
  railway up --ci --service backend
      |
      +-- pre-deploy: alembic upgrade head
      |
      v
  poll <backend>/health until 200
      |
      v
  railway up --ci --service frontend
      |
      v
  poll <frontend>/healthz until 200
      |
      v
  production
""",
        "From a merge to a release. Everything above the dashed decision is "
        "automatic; nothing below it happens without a person.",
    )

    g.h2("The Railway CLI")
    g.p(
        "`railway up --ci` builds and deploys one service from the current "
        "checkout, without the interactive prompts the CLI normally uses. Each "
        "invocation names the project, the environment and the service explicitly, "
        "so a workflow cannot deploy the wrong thing by inheriting a linked "
        "context."
    )
    g.code(
        """
railway up --ci \
  --project "${{ vars.RAILWAY_PROJECT_ID }}" \
  --environment "${RAILWAY_ENVIRONMENT}" \
  --service "${BACKEND_SERVICE}"
""",
        caption="Listing. The deployment step. The token is in the environment; it "
                "is never an argument, and never printed.",
    )

    g.h2("Authentication")
    g.definition(
        "Railway project token",
        "A credential scoped to one project and one environment, which can deploy "
        "that project's services and nothing else.",
        "A key to one building, not to every building you own.",
    )
    g.table(
        ["Name", "Kind", "Why"],
        [
            ["`RAILWAY_TOKEN`", "GitHub Actions **secret**",
             "It can deploy. A project token rather than an account token, so a "
             "leak is bounded to this project"],
            ["`RAILWAY_PROJECT_ID`", "Repository **variable**",
             "An identifier, not a credential"],
            ["`RAILWAY_ENVIRONMENT`", "Repository variable", "`production`"],
            ["`RAILWAY_BACKEND_SERVICE`", "Repository variable", "The service name"],
            ["`RAILWAY_FRONTEND_SERVICE`", "Repository variable", "The service name"],
            ["`RAILWAY_BACKEND_URL`", "Repository variable",
             "Polled for health after deploying"],
            ["`RAILWAY_FRONTEND_URL`", "Repository variable", "As above"],
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
        "`set -e` semantics: a failed command fails the job. A failed Railway "
        "deployment fails the workflow rather than being reported as success.",
        "It polls each health endpoint and fails if the service never becomes "
        "healthy.",
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
            ["The build fails", "Railway keeps the previous release",
             "Read the build log in the Railway dashboard"],
            ["Health never returns 200", "The workflow fails after its polling "
                                         "window",
             "Check the service logs; the previous release is still serving"],
            ["The frontend deploys but the API is unreachable",
             "`VITE_API_BASE_URL`, `CORS_ORIGINS` or the CSP `connect-src` "
             "disagree with the real URLs",
             "Align all three, then redeploy the frontend - the API URL is "
             "compiled in at build time"],
        ],
        caption="Failure modes of the release path.",
        widths=[1.4, 2.3, 2.1],
    )

    g.understand([
        "Why Railway cannot run docker-compose.yml, and what replaces each part.",
        "The difference between a Railway project, service and environment.",
        "What `*.railway.internal` is and which service uses it.",
        "Why `/health` must be cheap and what it does not prove.",
        "Why migrations run pre-deploy rather than at start-up.",
        "The difference between CI and CD, and why CD here is a button.",
        "Why a project token is preferable to an account token.",
    ])


def _secrets(g: Guide) -> None:
    g.h1("Secrets Across the Whole Pipeline", page_break=True)

    g.table(
        ["Secret", "Lives in", "Never in"],
        [
            ["`DATABASE_URL`",
             "A Railway reference variable in production; a local `.env` for "
             "development",
             "Git, the React bundle, logs, traces, the database"],
            ["`GROQ_API_KEY`", "Railway service variables",
             "Git, the bundle, logs, traces"],
            ["`TAVILY_API_KEY`", "Railway service variables",
             "Git, the bundle, logs"],
            ["`AVIATIONSTACK_API_KEY`", "Railway service variables",
             "Git, the bundle, logs"],
            ["`OPENWEATHER_API_KEY`", "Railway service variables",
             "Git, the bundle, logs"],
            ["`LANGSMITH_API_KEY`", "Railway service variables",
             "Git, the bundle, logs"],
            ["`RAILWAY_TOKEN`", "A GitHub Actions secret only",
             "Git, any Railway variable, any log line, the job summary"],
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
