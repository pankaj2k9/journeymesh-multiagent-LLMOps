"""Containers, compose, CI/CD, Render, Neon wiring and LangSmith configuration."""

from __future__ import annotations

from docgen.builder import Guide
from docgen.repo import FACTS


def write(g: Guide) -> None:
    _docker(g)
    _compose(g)
    _cicd(g)
    _render(g)
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
        "using frontend/nginx.conf - which carries the same content security policy "
        "and the same theme-script hash as the Python application, so the two paths "
        "cannot drift. This split arrangement exists for local development and for a "
        "possible future split deployment; production uses the single image."
    )


# ---------------------------------------------------------------------------
def _compose(g: Guide) -> None:
    g.h1("Docker Compose", page_break=True)

    g.p(
        "The root docker-compose.yml brings up PostgreSQL, runs migrations and starts "
        "the application, in that order, with the ordering enforced by the compose "
        "file rather than by a developer remembering it."
    )

    g.diagram(
        """
  db  (postgres)
    healthcheck: pg_isready
        |
        |  depends_on: condition = service_healthy
        v
  migrate  (the application image, command: migrate)
    alembic upgrade head, then exits 0
        |
        |  depends_on: condition = service_completed_successfully
        v
  backend  (the application image, command: serve)
    healthcheck: curl /api/v1/health
""",
        "Compose service ordering. Each arrow is a condition, not a delay.",
    )

    g.table(
        ["Condition", "Means", "Replaces"],
        [
            ["`service_healthy`",
             "Wait until the dependency's own healthcheck passes",
             "A sleep, and the race it hides"],
            ["`service_completed_successfully`",
             "Wait until the dependency exits with status zero",
             "Running migrations inside the server's start-up and hoping"],
        ],
        caption="The two compose conditions used, and what each removes.",
        widths=[1.7, 2.4, 1.7],
    )

    g.h2("The commands")
    g.table(
        ["Command", "Does"],
        [
            ["`make docker-build`", "Build the images"],
            ["`make docker-up`", "Start the full stack"],
            ["`make docker-dev`", "Start with the development overlay"],
            ["`make docker-down`", "Stop it"],
            ["`make docker-logs`", "Follow the logs"],
            ["`make docker-migrate`", "Run migrations against the compose database"],
            ["`make docker-test`", "Run the test suite inside the image"],
            ["`make docker-shell`", "A shell in the running container"],
            ["`make docker-db`", "A psql session against the compose database"],
            ["`make docker-clean`", "Remove containers and volumes"],
            ["`make image`", "Build the single production image"],
            ["`make image-run`", "Run the production image locally"],
        ],
        caption="Docker-related Make targets.",
        widths=[1.7, 4.1],
    )

    g.callout(
        "note",
        "Docker was not available in the environment where this repository was "
        "developed, so the images have not been built locally. The `docker` job in "
        "CI is what proves the build. Image build status: not verified locally; see "
        "the CI run for the authoritative result.",
    )


# ---------------------------------------------------------------------------
def _cicd(g: Guide) -> None:
    g.h1("Continuous Integration and Deployment", page_break=True)

    g.h2("The pipeline")
    g.diagram(
        """
  developer                git push / pull request
      |
      v
  +---------------------------------------------------------------+
  |  CI  (.github/workflows/ci.yml)                                |
  |                                                                |
  |   frontend   npm ci -> tsc --noEmit -> vitest -> vite build    |
  |              -> assert dist/index.html exists -> upload dist   |
  |                                                                |
  |   backend    pip install -> ruff -> import check               |
  |              -> unit and integration tests                     |
  |              -> guardrail and security tests                   |
  |              -> evaluation tests -> observability tests        |
  |              -> offline evaluation suite                       |
  |              -> alembic upgrade head --sql                     |
  |                                                                |
  |   security   no .env may be committed                          |
  |              no deploy hook or credential in the repository    |
  |              python dependency audit                           |
  |                                                                |
  |   docker     build the production image                        |
  +-----------------------------|---------------------------------+
                                |  on main, and only if CI succeeded
                                v
  +---------------------------------------------------------------+
  |  Deploy  (.github/workflows/deploy.yml)                        |
  |    verify RENDER_DEPLOY_HOOK_URL is configured                 |
  |    POST the hook  (the URL is never echoed)                    |
  |    poll /api/v1/health until it reports ok                     |
  |    write a job summary                                         |
  +-----------------------------|---------------------------------+
                                v
                        Render Docker web service
                                |
                                v
                        Neon PostgreSQL  (DATABASE_URL)
""",
        "The full path from a push to a running deployment.",
    )

    g.h2("The CI jobs")
    g.table(
        ["Job", "Gate it provides"],
        [
            ["Frontend",
             "Types compile, tests pass, the production build succeeds and actually "
             "produced an entry point"],
            ["Backend",
             "Lint is clean, every module imports, every test suite passes, the "
             "offline evaluation passes, and the migration configuration renders"],
            ["Security",
             "No environment file is committed, no credential-shaped string appears in "
             "the repository, and the dependency audit is clean"],
            ["Docker",
             "The production image builds from a clean context"],
        ],
        caption="What each CI job actually proves.",
        widths=[1.1, 4.7],
    )
    g.p(
        f"There are {len(FACTS.workflows)} workflow files: "
        + ", ".join(f"`{name}`" for name in FACTS.workflows) + "."
    )

    g.h2("Why deployment is a separate workflow")
    g.p(
        "Deploy is triggered by the completion of the CI workflow on main, not by a "
        "push. It checks two conditions before doing anything: that the run was on "
        "main, and that CI concluded successfully. A pull request therefore cannot "
        "reach it at all. A manual dispatch is allowed on its own, for the case where "
        "an environment variable changed in the dashboard and the service needs a "
        "restart without a code change."
    )

    g.h2("Avoiding double deployment")
    g.p(
        "Render can watch the repository and deploy on every push by itself. If both "
        "that and this workflow are active, every merge deploys twice - two builds, "
        "two restarts, and a race over which one wins. `render.yaml` therefore sets "
        "`autoDeploy: false`, and GitHub Actions is the single controlled path."
    )
    g.callout(
        "important",
        "If the service was created by hand in the dashboard rather than from the "
        "blueprint, auto-deploy must be switched off there manually. This is the most "
        "common way a deployment pipeline ends up racing itself.",
    )

    g.h2("Deploying without printing the hook")
    g.p(
        "The deploy hook URL is a credential: anyone holding it can trigger a "
        "deployment. The workflow reads it from the environment, posts to it with "
        "curl, and inspects only the response body and status code. The URL is never "
        "echoed, never interpolated into a log line, and never written to the job "
        "summary."
    )
    g.code(
        """
- name: Trigger the Render deployment
  env:
    RENDER_DEPLOY_HOOK_URL: ${{ secrets.RENDER_DEPLOY_HOOK_URL }}
  run: |
    status=$(curl -sS -o /tmp/deploy.json -w '%{http_code}' \\
      -X POST "$RENDER_DEPLOY_HOOK_URL")

    echo "Render responded with HTTP ${status}"
    if [ "$status" != "200" ] && [ "$status" != "201" ]; then
      echo "::error::Render rejected the deploy hook (HTTP ${status})"
      head -c 400 /tmp/deploy.json || true
      exit 1
    fi
    echo "deployment triggered"
""",
        caption="Listing. The deployment step. The secret is read from the "
                "environment and never appears in output.",
    )

    g.h2("Verifying the deployment")
    g.p(
        "After triggering, the workflow polls `/api/v1/health` until it reports ok, "
        "with a generous allowance because Render rebuilds the image before "
        "restarting. Failing to reach healthy within that window produces a warning "
        "and a pointer to the dashboard rather than a false failure, because a slow "
        "free-tier build is not the same thing as a broken deployment."
    )


# ---------------------------------------------------------------------------
def _render(g: Guide) -> None:
    g.h1("Hosting on Render", page_break=True)

    g.h2("The shape of the deployment")
    g.table(
        ["Property", "Value", "Why"],
        [
            ["Runtime", "Docker",
             "The same image that CI built and that runs locally"],
            ["Plan", "Free", "The project is a portfolio and study system"],
            ["Health check path", "`/api/v1/health`",
             "Matches the image's own HEALTHCHECK"],
            ["Auto-deploy", "false", "GitHub Actions owns deployment"],
            ["Database block", "absent",
             "PostgreSQL is Neon, reached only through DATABASE_URL"],
            ["Port", "from `$PORT`",
             "Assigned by the platform; never hard-coded"],
            ["Workers", "`WEB_CONCURRENCY = 2`",
             "The free plan's memory allowance makes two a sensible ceiling"],
        ],
        caption="The Render service configuration, from render.yaml.",
        widths=[1.2, 1.5, 3.1],
    )

    g.h2("Why the blueprint is committed")
    g.p(
        "The service could equally be created by hand in the dashboard. render.yaml is "
        "checked in so that the deployment shape is visible and reviewable in the same "
        "place as the code. Every value in it is either public or marked `sync: false`, "
        "which means \"set this in the dashboard\" - so the file contains no secret."
    )

    g.h2("Free-tier realities, stated plainly")
    g.bullets([
        "The service sleeps when idle. The first request after a sleep pays for a "
        "cold start, and the Neon compute may be resuming at the same moment.",
        "Memory is limited, which is why the worker count is capped at two.",
        "Build minutes are finite, which is another reason a single deployment path "
        "matters.",
        "Actual cold-start and response latency for this deployment have not been "
        "measured. Not measured yet.",
    ])

    g.h2("What must be set in the dashboard")
    g.table(
        ["Variable", "Source"],
        [
            ["`DATABASE_URL`", "The Neon connection string, with SSL required"],
            ["`GROQ_API_KEY`, `GROQ_MODEL`", "The model provider"],
            ["`TAVILY_API_KEY`", "Search provider"],
            ["`AVIATIONSTACK_API_KEY`", "Aviation provider"],
            ["`OPENWEATHER_API_KEY`", "Weather provider"],
            ["`LANGSMITH_API_KEY`", "Tracing, optional"],
            ["`MCP_*_URL`", "Only if a remote MCP server is used"],
            ["`CORS_ORIGINS`", "Only if the interface is hosted separately"],
        ],
        caption="Values marked `sync: false` in render.yaml. Each is set in the "
                "dashboard and never committed.",
        widths=[2.0, 3.8],
    )

    g.h2("No cloud-specific code")
    g.p(
        "Nothing in the business logic knows it is running on Render. There is no "
        "import of a platform SDK, no branch on a platform environment variable in an "
        "agent or a service, and no assumption about the filesystem beyond a "
        "configurable static directory. The platform-specific facts - the assigned "
        "port, the health check path, the deploy hook - live in the entrypoint, the "
        "blueprint and the workflow respectively."
    )


# ---------------------------------------------------------------------------
def _secrets(g: Guide) -> None:
    g.h1("Secrets Across the Whole Pipeline", page_break=True)

    g.table(
        ["Secret", "Lives in", "Never in"],
        [
            ["`DATABASE_URL`", "Render environment; a local `.env` for development",
             "Git, the React bundle, logs, traces, the database"],
            ["`GROQ_API_KEY`", "Render environment", "Git, the bundle, logs, traces"],
            ["`TAVILY_API_KEY`", "Render environment", "Git, the bundle, logs"],
            ["`AVIATIONSTACK_API_KEY`", "Render environment", "Git, the bundle, logs"],
            ["`OPENWEATHER_API_KEY`", "Render environment", "Git, the bundle, logs"],
            ["`LANGSMITH_API_KEY`", "Render environment", "Git, the bundle, logs"],
            ["`RENDER_DEPLOY_HOOK_URL`", "A GitHub Actions secret only",
             "Git, the Render environment, any log line, the job summary"],
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
        "Why Render's auto-deploy must be off.",
        "Which secrets live where, and the five defences that keep them there.",
        "Why LangSmith can never fail a journey.",
    ])
