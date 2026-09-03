"""Setup walkthroughs, command reference, source-code walkthrough, troubleshooting."""

from __future__ import annotations

from docgen.builder import Guide


def write(g: Guide) -> None:
    _local_setup(g)
    _docker_setup(g)
    _cloud_setup(g)
    _commands(g)
    _code_walkthrough(g)
    _troubleshooting(g)


# ---------------------------------------------------------------------------
def _local_setup(g: Guide) -> None:
    g.h1("Running It Locally", page_break=True)

    g.h2("Prerequisites")
    g.table(
        ["Tool", "Version", "Why"],
        [
            ["Python", "3.10 or newer", "The backend; the codebase targets 3.10 "
                                        "syntax deliberately"],
            ["Node.js", "20 or newer", "The frontend build"],
            ["make", "any", "The single entry point for every task"],
            ["Docker", "optional", "Only for the container workflows"],
        ],
        caption="What must be installed first.",
        widths=[1.0, 1.3, 3.5],
    )
    g.callout(
        "note",
        "The backend targets Python 3.10 on purpose, which is why `timezone.utc` is "
        "used rather than `datetime.UTC` throughout. Ruff's UP017 rule, which rewrites "
        "one to the other, is disabled for exactly this reason - the rewrite would "
        "break the project on 3.10.",
    )

    g.h2("Two commands")
    g.code(
        """
git clone <your fork of this repository>
cd journeymesh-multiagent-LLMOps

make setup     # virtualenv, backend deps, frontend deps, both .env files
make dev       # API and interface together; Ctrl-C stops both
""",
        caption="Listing. The whole local setup.",
    )

    g.h2("What `make setup` does, step by step")
    g.numbered([
        "check-tools. Verifies Python, Node and npm are present and new enough, and "
        "stops with a clear message if not.",
        "venv. Creates the backend virtual environment.",
        "backend-install. Installs backend/requirements.txt into it.",
        "backend-env. Copies backend/.env.example to backend/.env if it does not "
        "already exist. Every secret stays blank.",
        "frontend-install. Runs npm install for the interface.",
        "frontend-env. Creates the frontend environment file the same way.",
    ])
    g.callout(
        "important",
        "The system runs immediately after setup with no API keys at all. The health "
        "endpoint reports `llm: deterministic`, agents produce structured results from "
        "reference data, and everything is labelled ESTIMATE. Adding keys upgrades the "
        "labels; it is not required to see the system work.",
    )

    g.h2("What `make dev` starts")
    g.table(
        ["Process", "Port", "Serves"],
        [
            ["Uvicorn with reload", "8000",
             "The API at /api/v1, the OpenAPI schema and the interactive explorer"],
            ["Vite dev server", "5173",
             "The interface, proxying API calls to the backend"],
        ],
        caption="The two development processes. Override with, for example, "
                "`make dev BACKEND_PORT=9000`.",
        widths=[1.5, 0.8, 3.5],
    )

    g.h2("Adding keys")
    g.p(
        "Editing backend/.env upgrades the system's behaviour without changing any "
        "code. Each key is independent: a Groq key enables model-composed prose, a "
        "weather key upgrades the forecast from ESTIMATE to LIVE, and so on."
    )
    g.code(
        """
# backend/.env  - each line is optional and independent

GROQ_API_KEY=            # model-composed itinerary prose
GROQ_MODEL=              # which Groq model to use
TAVILY_API_KEY=          # web search for hotels and activities
AVIATIONSTACK_API_KEY=   # live flight data
OPENWEATHER_API_KEY=     # live forecasts
LANGSMITH_TRACING=       # set to true to trace
LANGSMITH_API_KEY=       # required only if tracing is on
DATABASE_URL=            # leave blank for local SQLite
""",
        caption="Listing. The keys that matter locally. Values are blank in the "
                "repository and must stay that way.",
    )

    g.h2("The end-to-end smoke test")
    g.p(
        "`make smoke` plans a journey, requests a change and approves it against a "
        "running API, exercising the whole human-in-the-loop path in one command. It "
        "is the fastest way to confirm a local instance actually works."
    )


# ---------------------------------------------------------------------------
def _docker_setup(g: Guide) -> None:
    g.h1("Running It in Containers", page_break=True)

    g.h2("The production-shaped stack")
    g.code(
        """
make docker-up        # postgres, then migrations, then the application
make docker-logs      # follow; s=api to follow one service
make docker-ps        # container status
make docker-down      # stop; v=1 also drops the database volume
""",
        caption="Listing. The compose stack.",
    )
    g.p(
        "The ordering is enforced by the compose file: PostgreSQL must report healthy "
        "before migrations run, and migrations must exit successfully before the "
        "application starts. There is no sleep anywhere in the arrangement."
    )

    g.h2("The single production image")
    g.code(
        """
make image            # build the three-stage image
make image-run        # build it and run it locally

# then, in another shell:
curl -s localhost:8000/api/v1/health
open http://localhost:8000/
""",
        caption="Listing. Building and running exactly what production runs.",
    )
    g.p(
        "This is the closest local approximation to the deployed system: one container "
        "serving both the interface and the API, on the port given by PORT, with the "
        "same entrypoint and the same health check."
    )

    g.h2("The development overlay")
    g.p(
        "`make docker-dev` runs the split arrangement with hot reload on both halves - "
        "the backend under uvicorn's reloader and the interface under Vite. It is "
        "slower to start and more convenient to work in; the production image is what "
        "you check before deploying."
    )


# ---------------------------------------------------------------------------
def _cloud_setup(g: Guide) -> None:
    g.h1("Deploying It", page_break=True)

    g.h2("The order of operations")
    g.numbered([
        "Create the Neon project and copy the connection string. It must require SSL.",
        "Push the repository to GitHub and let CI run. Do not proceed until it is "
        "green - the deploy workflow will refuse anyway.",
        "Create the Render web service from the Dockerfile, or from render.yaml. "
        "Confirm that auto-deploy is off.",
        "Set every `sync: false` variable in the Render dashboard: DATABASE_URL, the "
        "provider keys, and the LangSmith key if tracing is wanted.",
        "Copy the deploy hook from the Render dashboard and add it to GitHub as the "
        "repository secret RENDER_DEPLOY_HOOK_URL. Add nothing else anywhere.",
        "Optionally set the repository variable RENDER_SERVICE_URL so the deploy "
        "workflow can poll the health endpoint after deploying.",
        "Merge to main. CI runs, and on success the deploy workflow posts the hook.",
        "Verify with `make verify-deployment url=https://your-service`.",
    ])

    g.h2("The verification script")
    g.p(
        "scripts/verify_deployment.py checks a deployed instance: that the health "
        "endpoint responds and reports ok, that the security headers are present, that "
        "the interface is served and its deep links resolve, that the API is reachable "
        "under its prefix, and - with `plan=1` - that a full journey can be planned, "
        "revised and approved."
    )
    g.callout(
        "note",
        "Run against a local server during development, the script reports one "
        "expected failure: the DATABASE_URL check, which is not configured locally. "
        "Every other check passes. That is the documented local result, not a claim "
        "about the deployed instance.",
    )

    g.h2("Deployment status, stated precisely")
    g.table(
        ["Claim", "Status"],
        [
            ["The pipeline is configured", "Yes - workflows, blueprint and entrypoint "
                                           "are in the repository"],
            ["The image builds", "Proven by the CI docker job, not locally"],
            ["The application runs from the image", "Not verified locally - Docker was "
                                                    "unavailable in the development "
                                                    "environment"],
            ["A production instance is live", "Not asserted by this document"],
            ["Production latency", "Not measured yet"],
        ],
        caption="What this guide claims about deployment, and what it does not.",
        widths=[2.4, 3.4],
    )


# ---------------------------------------------------------------------------
def _commands(g: Guide) -> None:
    g.h1("Command Cheat Sheet", page_break=True)

    g.h2("Getting started")
    g.table(
        ["Command", "Does"],
        [
            ["`make help`", "The full target list with descriptions"],
            ["`make setup`", "Everything: venv, dependencies, environment files"],
            ["`make dev`", "API and interface together"],
            ["`make verify`", "Every test suite plus a production build"],
            ["`make info`", "Resolved paths, ports and setup state"],
        ],
        caption="Getting started.",
        widths=[1.7, 4.1],
    )

    g.h2("Running individually")
    g.table(
        ["Command", "Does"],
        [
            ["`make backend-run`", "The API alone"],
            ["`make frontend-dev`", "The interface alone"],
            ["`make stop`", "Stop anything left listening on those ports"],
        ],
        caption="Individual processes.",
        widths=[1.7, 4.1],
    )

    g.h2("Quality")
    g.table(
        ["Command", "Does"],
        [
            ["`make test`", "Both suites"],
            ["`make backend-test`", "pytest"],
            ["`make frontend-test`", "vitest"],
            ["`make typecheck`", "`tsc --noEmit`"],
            ["`make lint`", "ruff"],
            ["`make eval`", "The offline evaluation suite"],
            ["`make build`", "The production frontend build"],
        ],
        caption="Quality gates.",
        widths=[1.7, 4.1],
    )

    g.h2("Database")
    g.table(
        ["Command", "Does"],
        [
            ["`make migrate`", "Apply migrations"],
            ["`make migration m=\"add x\"`", "Autogenerate a revision"],
        ],
        caption="Database.",
        widths=[1.7, 4.1],
    )

    g.h2("Docker")
    g.table(
        ["Command", "Does"],
        [
            ["`make docker-up`", "Build and start the stack"],
            ["`make docker-dev`", "Split stack with hot reload"],
            ["`make docker-down`", "Stop; `v=1` drops the volume"],
            ["`make docker-logs`", "Follow logs; `s=api` for one service"],
            ["`make docker-ps`", "Container status"],
            ["`make docker-migrate`", "Migrations inside the stack"],
            ["`make docker-test`", "The backend suite inside the image"],
            ["`make docker-shell`", "A shell in the container; `s=db` for PostgreSQL"],
            ["`make docker-db`", "psql into the database"],
            ["`make docker-clean`", "Remove containers and volumes"],
        ],
        caption="Docker.",
        widths=[1.7, 4.1],
    )

    g.h2("Deployment and housekeeping")
    g.table(
        ["Command", "Does"],
        [
            ["`make image`", "Build the production image"],
            ["`make image-run`", "Build and run it locally"],
            ["`make verify-deployment url=...`",
             "Check a deployed instance; `plan=1` runs a full journey"],
            ["`make health`", "Read a running API's health endpoint"],
            ["`make smoke`", "Plan, revise and approve one journey end to end"],
            ["`make clean`", "Remove caches and build output"],
            ["`make reset`", "clean, plus the venv and node_modules"],
        ],
        caption="Deployment and housekeeping.",
        widths=[1.9, 3.9],
    )


# ---------------------------------------------------------------------------
def _code_walkthrough(g: Guide) -> None:
    g.h1("Reading the Source", page_break=True)

    g.h2("A reading order that makes sense")
    g.p(
        "Reading a codebase alphabetically teaches you very little. This order follows "
        "one request through the system, so each file explains the next."
    )
    g.numbered([
        "`backend/app/core/constants.py`. Every name the rest of the code uses: "
        "agents, execution order, dependents, provenance labels, statuses. Twenty "
        "minutes here saves hours later.",
        "`backend/app/graph/state.py`. What the agents share, who owns which key, and "
        "the result markers that make preservation correct.",
        "`backend/app/graph/travel_graph.py`. The seven nodes and the edges between "
        "them. Read the module docstring first - it is the graph in ASCII.",
        "`backend/app/graph/routing.py`. The entry router and the agent ordering.",
        "`backend/app/agents/supervisor.py`. The intent vocabulary, dependency "
        "expansion and preservation.",
        "`backend/app/agents/base.py`, then one specialist - `budget_agent.py` is the "
        "shortest and has no tool calls to distract from the shape.",
        "`backend/app/guardrails/policies.py`, then `tool_guard.py`. The policy table "
        "first, then the code that enforces it.",
        "`backend/app/mcp/client.py`. How a tool call actually travels.",
        "`backend/app/evaluation/schemas.py`, then `rules.py`, then `metrics.py`. "
        "Dimensions, then checks, then aggregation.",
        "`backend/app/api/routes/travel.py` and `backend/app/services/travel_service."
        "py`. How HTTP meets the graph.",
        "`backend/app/db/models.py`. The schema, once you know what is being stored.",
        "`frontend/src/hooks/useTrips.ts` and `frontend/src/pages/TripPage.tsx`. How "
        "the response becomes an interface.",
        "`frontend/src/theme/theme.ts` and `frontend/src/index.css`. The token system "
        "and both palettes.",
    ])

    g.h2("Where to make common changes")
    g.table(
        ["To do this", "Change these files"],
        [
            ["Add a specialist agent",
             "`core/constants.py` (name, order, dependents), `graph/state.py` (key "
             "and result marker), `agents/<new>_agent.py`, `agents/__init__.py` "
             "(registry), `guardrails/policies.py` (its tools), plus tests"],
            ["Add a tool",
             "The MCP server module, `guardrails/policies.py`, and a Tool Guard test"],
            ["Add an evaluation dimension",
             "`evaluation/schemas.py` (DIMENSIONS and DIMENSION_WEIGHTS), "
             "`evaluation/rules.py` (the check), plus a test"],
            ["Add a language",
             "`core/constants.py`, `core/i18n.py`, `frontend/src/locales/<code>/`, "
             "and the i18n parity test picks up the rest"],
            ["Change the theme palette",
             "`frontend/src/index.css` only - components name tokens, never colours"],
            ["Change the theme init script",
             "`frontend/src/theme/theme.ts`, then regenerate the SHA-256 hash in "
             "`backend/app/security/headers.py` and `frontend/nginx.conf`"],
            ["Add an environment variable",
             "`core/config.py` (a typed field), `backend/.env.example` (blank), and "
             "`render.yaml` if it is needed in production"],
            ["Add a database column",
             "`db/models.py`, then `make migration`, then review the generated "
             "revision before committing it"],
            ["Add an API route",
             "`api/routes/<area>.py`, a schema in `schemas/`, a service method, and a "
             "TestClient test"],
        ],
        caption="A change-impact map for the most common tasks.",
        widths=[1.5, 4.3],
    )

    g.callout(
        "tip",
        "The theme-script hash is the one change with a non-obvious second location. "
        "Changing the script without regenerating the hash produces a content security "
        "policy violation that silently blocks the script, and the symptom is a "
        "flash of the wrong theme rather than an error.",
    )


# ---------------------------------------------------------------------------
def _troubleshooting(g: Guide) -> None:
    g.h1("Troubleshooting", page_break=True)

    g.h2("Frontend")
    g.table(
        ["Symptom", "Cause", "Fix"],
        [
            ["`[postcss] The 'bg-canvas' class does not exist`",
             "A dev server started before the Tailwind configuration changed is "
             "serving a stale config from its cache",
             "Stop the dev server, `rm -rf frontend/node_modules/.vite`, start it "
             "again"],
            ["`Cannot find module @rollup/rollup-<platform>`",
             "node_modules contains binaries built for a different operating system - "
             "typically because an install was run from a different machine into a "
             "shared folder",
             "`rm -rf frontend/node_modules && npm install --prefix frontend`. Do NOT "
             "delete package-lock.json: it holds the record of every platform "
             "variant"],
            ["A flash of the wrong theme on load",
             "The pre-paint script did not run - usually a stale CSP hash after the "
             "script changed",
             "Regenerate the SHA-256 hash and update both "
             "`backend/app/security/headers.py` and `frontend/nginx.conf`"],
            ["A deep link returns 404 in production",
             "The SPA fallback is not mounted, or the build is missing from the image",
             "Confirm SERVE_FRONTEND is true and that the image contains ./static"],
            ["Type errors that the editor does not show",
             "The editor is using a different TypeScript version",
             "`make typecheck` is the authority; CI runs the same command"],
        ],
        caption="Frontend problems.",
        widths=[1.6, 2.0, 2.2],
    )

    g.h2("Backend")
    g.table(
        ["Symptom", "Cause", "Fix"],
        [
            ["`no such table: trips` in a test",
             "A TestClient constructed without the lifespan handler never created the "
             "schema",
             "The engine creates tables for the ephemeral SQLite backend; confirm the "
             "test uses that backend"],
            ["A date is redacted as a phone number",
             "An over-broad phone pattern",
             "`_looks_like_phone` rejects ISO dates and short digit runs; this is "
             "fixed, and a regression test covers it"],
            ["A response is rejected with a provider-status error",
             "An internal fallback returned a source label outside the four canonical "
             "values",
             "The MCP client coerces unknown labels to UNAVAILABLE; add the label to "
             "DATA_SOURCES only if it is genuinely a new provenance class"],
            ["ruff rewrites `timezone.utc` to `datetime.UTC`",
             "The UP017 rule assumes Python 3.11",
             "UP017 is disabled and target-version is py310; do not re-enable it "
             "unless the project drops 3.10"],
            ["A circular import at start-up",
             "A package `__init__` importing a module that imports the package",
             "`app/services/__init__.py` and `app/graph/__init__.py` use a "
             "module-level `__getattr__` for lazy loading; follow that pattern"],
            ["The supervisor re-runs an agent the traveller asked to keep",
             "The preservation phrase did not match",
             "Check the phrasing against `_PRESERVE`; the pattern allows up to forty "
             "characters between the verb and the noun"],
        ],
        caption="Backend problems.",
        widths=[1.6, 2.0, 2.2],
    )

    g.h2("CI and deployment")
    g.table(
        ["Symptom", "Cause", "Fix"],
        [
            ["The secret scan fails on a test fixture",
             "A credential-shaped literal in the repository",
             "Build fixtures by concatenation so no literal exists; the scan excludes "
             "the workflow, compose and test paths"],
            ["Every merge deploys twice",
             "Render auto-deploy is on as well as the workflow",
             "Set `autoDeploy: false`, or switch it off in the dashboard"],
            ["`RENDER_DEPLOY_HOOK_URL is not set`",
             "The secret is missing",
             "Add it under Settings, Secrets and variables, Actions. Nowhere else"],
            ["The health poll times out after a deploy",
             "A free-tier build can take longer than the polling window",
             "This is a warning, not a failure; check the Render dashboard"],
            ["The service starts but the interface is missing",
             "The frontend build did not reach the image",
             "Confirm the frontend-builder stage succeeded and that the COPY into "
             "./static is present"],
            ["A migration fails on deploy",
             "The revision does not apply to the current database",
             "The entrypoint stops before the server starts, which is intended; fix "
             "the revision and redeploy"],
        ],
        caption="Pipeline and hosting problems.",
        widths=[1.6, 2.0, 2.2],
    )
