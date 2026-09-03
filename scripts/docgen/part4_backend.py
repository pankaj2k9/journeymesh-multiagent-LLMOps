"""The Python backend: FastAPI, Pydantic, services, repositories, i18n."""

from __future__ import annotations

from docgen.builder import Guide
from docgen.repo import FACTS


def write(g: Guide) -> None:
    _fastapi(g)
    _pydantic(g)
    _api_reference(g)
    _services(g)
    _i18n(g)
    _python_packages(g)


# ---------------------------------------------------------------------------
def _fastapi(g: Guide) -> None:
    g.h1("The FastAPI Application", page_break=True)

    g.h2("Why FastAPI")
    g.definition(
        "FastAPI",
        "An asynchronous Python web framework built on Starlette and Pydantic, in "
        "which route signatures are type annotations: the framework derives request "
        "parsing, validation, serialisation and an OpenAPI schema from the types "
        "themselves.",
        "A web framework where you describe the shape of the data once, in normal "
        "Python types, and it handles checking it, converting it and documenting it "
        "for you.",
    )
    g.bullets([
        "Asynchronous by default, which matters because most of what JourneyMesh does "
        "is waiting - on a model, on a provider, on the database.",
        "Validation is the type annotation. There is no separate schema file that can "
        "drift from the code.",
        "OpenAPI and an interactive explorer come free, so the API is documented by "
        "construction.",
        "The same Pydantic models validate an HTTP request and the arguments an agent "
        "receives, so there is one definition of what a trip constraint is.",
    ])

    g.h2("Application construction")
    g.p(
        "The application is built by a factory function rather than at import time. "
        "That is what allows the test suite to construct an application with different "
        "settings, and it is why the offline evaluation runner can import the graph "
        "without starting a web server."
    )

    g.h2("Middleware, and why the order matters")
    g.p(
        "FastAPI applies middleware in reverse order of registration, so the last one "
        "added is the outermost. The registration order in main.py therefore produces "
        "this request path:"
    )
    g.diagram(
        """
  incoming request
        |
        v
  CORSMiddleware               only relevant when the SPA is hosted separately
        |
        v
  RequestContextMiddleware     attaches a request id; every log line carries it
        |
        v
  RequestSizeLimitMiddleware   rejects bodies over MAX_REQUEST_SIZE
        |
        v
  RateLimitMiddleware          per-client window; 429 when exhausted
        |
        v
  SecurityHeadersMiddleware    CSP, frame options, referrer policy, and the
        |                      removal of the server banner
        v
  route handler
""",
        "The effective middleware order for an incoming request.",
    )
    g.p(
        "The ordering is deliberate. A request id is attached first so that a "
        "rejection by any later layer is still correlatable in the logs. The size "
        "limit runs before the rate limiter so that an oversized body is discarded "
        "without consuming a rate-limit slot. Security headers are applied closest to "
        "the handler so that every response - including error responses produced by "
        "the layers above - carries them."
    )

    g.h2("Lifespan")
    g.p(
        "The lifespan context manager runs once at start-up and once at shutdown. On "
        "start-up it configures logging, applies observability configuration, prepares "
        "the database engine and - when RUN_MIGRATIONS_ON_STARTUP is set - ensures the "
        "schema is current. On shutdown it disposes the engine so connections are "
        "returned cleanly, which matters on a serverless database where idle "
        "connections are a scarce resource."
    )

    g.h2("Serving the React application")
    g.p(
        "In production one container serves both the API and the built React bundle. "
        "app/api/static_site.py mounts the bundle with a catch-all route so that a "
        "browser requesting /trip/abc123 - a client-side route that does not exist on "
        "disk - receives index.html and lets React Router resolve it."
    )
    g.table(
        ["Concern", "How static_site.py handles it"],
        [
            ["API paths must not be swallowed",
             "RESERVED_PREFIXES excludes /api, the docs paths and the OpenAPI schema "
             "from the catch-all"],
            ["Path traversal",
             "`_safe_file()` resolves the requested path and refuses anything that "
             "escapes the distribution directory"],
            ["A missing build",
             "`mount_frontend()` returns False and the API runs alone rather than "
             "failing to start"],
            ["Deep links",
             "Any unmatched GET returns index.html with a 200, which is what a SPA "
             "router requires"],
        ],
        caption="The four problems a single-container SPA mount has to solve.",
        widths=[1.5, 4.3],
    )

    g.h2("The health endpoint")
    g.p(
        "The health check is the platform's liveness probe, so it is deliberately the "
        "cheapest endpoint in the system. It calls no model, runs no graph, invokes no "
        "MCP tool, contacts no travel provider, does not talk to LangSmith and does "
        "not open a database connection. It reports configuration, not the liveness of "
        "third parties."
    )
    g.callout(
        "important",
        "This is a deployment requirement, not a stylistic preference. A health check "
        "that calls a provider will fail when that provider has an outage, and the "
        "platform will then restart a perfectly healthy container - converting a "
        "partial degradation into a total one.",
    )
    g.code(
        """
@router.get("/health", response_model=HealthResponse, summary="Service health")
def health(
    verbose: bool = Query(default=False, description="Include provider and MCP details"),
) -> HealthResponse:
    settings = get_settings()

    response = HealthResponse(
        status="ok",
        service="JourneyMesh API",
        app=settings.app_name,
        tagline=APP_TAGLINE,
        version=VERSION,
        environment=settings.app_env,
        database=configured_backend(),
        llm="groq" if settings.llm_available else "deterministic",
        time=datetime.now(timezone.utc),
    )
    ...
""",
        caption="Listing. The health endpoint. `configured_backend()` reports which "
                "driver is configured, without connecting.",
    )
    g.p(
        "The verbose form adds the provider catalogue, the MCP transport status, "
        "runtime information, observability configuration and the in-process metrics "
        "snapshot. All of that is local state, so the verbose form is still free of "
        "network calls."
    )

    g.understand([
        "Why route annotations are the validation layer in FastAPI.",
        "The effective middleware order and the reasoning behind it.",
        "How one container serves both an API and a client-side router.",
        "Why the health endpoint must not touch any external dependency.",
    ])


# ---------------------------------------------------------------------------
def _pydantic(g: Guide) -> None:
    g.h1("Pydantic and Configuration", page_break=True)

    g.h2("Pydantic v2")
    g.definition(
        "Pydantic",
        "A data-validation library that builds a validator from a type annotation and "
        "produces a typed, immutable-by-convention model instance or a structured "
        "error. Version 2 implements the validation core in Rust.",
        "You describe what good data looks like using ordinary Python types, and it "
        "either hands you clean data or tells you exactly which field was wrong.",
    )
    g.p(
        "In JourneyMesh, Pydantic sits at three boundaries: the HTTP request boundary, "
        "the tool-argument boundary and the response boundary. A value that has passed "
        "all three has been checked three times against three different definitions of "
        "correct, and no agent contains a line of defensive parsing."
    )

    g.table(
        ["Module", "Defines"],
        [
            ["`app/schemas/common.py`",
             "The shared base model and `ProviderStatus`, which carries the "
             "provenance label"],
            ["`app/schemas/travel.py`",
             "`TripPlanRequest`, `TripConstraints`, `HealthResponse` and the trip "
             "response envelope"],
            ["`app/schemas/flight.py`", "Flight options and their pricing"],
            ["`app/schemas/hotel.py`", "Hotel options and their nightly rates"],
            ["`app/schemas/weather.py`", "Forecast days and current conditions"],
            ["`app/schemas/budget.py`", "The breakdown, totals and budget status"],
            ["`app/schemas/itinerary.py`", "Days, slots and activities"],
            ["`app/schemas/review.py`", "Approve and request-changes payloads"],
            ["`app/schemas/evaluation.py`",
             "`EvaluationCheck`, `EvaluationResult` and the check outcome literals"],
        ],
        caption="The schema modules and what each one owns.",
        widths=[1.7, 4.1],
    )

    g.h2("pydantic-settings and the Settings object")
    g.p(
        "All configuration is read once into a single Settings object built with "
        "pydantic-settings, cached with an LRU cache so the environment is parsed once "
        "per process. Nothing in the codebase reads os.environ directly; every value "
        "arrives as a typed attribute."
    )
    g.bullets([
        "Blank-to-default validators. An environment variable that is present but "
        "empty falls back to its default rather than becoming an empty string. This "
        "matters because a platform dashboard will happily set a variable to \"\" and "
        "a shipped .env.example has every secret blank on purpose.",
        "Derived properties rather than duplicated variables. `sqlalchemy_url` and "
        "`psycopg_url` are computed from DATABASE_URL; `langsmith_enabled` is computed "
        "from the tracing flag and the presence of a key; `frontend_dist_path` is "
        "computed from the distribution directory setting.",
        "One place to change a default. Adding a setting means adding a field, and "
        "the type annotation is the validation.",
    ])
    g.callout(
        "warning",
        "The repository's `.env` and `.env.example` ship with every secret blank by "
        "design. They are configuration templates, not configuration. A blank "
        "GROQ_API_KEY is a supported state - the system runs in its deterministic "
        "mode - so an empty template never produces a crash at import time.",
    )

    g.h2("Environment variables")
    g.p(
        f"There are {len(FACTS.backend_env)} variables in backend/.env.example. They "
        "fall into nine groups."
    )
    g.table(
        ["Group", "Variables"],
        [
            ["Application", "`APP_NAME`, `APP_ENV`, `DEBUG`"],
            ["Database",
             "`DATABASE_URL`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT_"
             "SECONDS`, `DB_POOL_RECYCLE_SECONDS`, `DB_CONNECT_TIMEOUT_SECONDS`, "
             "`DB_STATEMENT_TIMEOUT_MS`, `DB_REQUIRE_SSL`, "
             "`RUN_MIGRATIONS_ON_STARTUP`"],
            ["Model", "`GROQ_API_KEY`, `GROQ_MODEL`"],
            ["Providers",
             "`TAVILY_API_KEY`, `AVIATIONSTACK_API_KEY`, `OPENWEATHER_API_KEY`"],
            ["MCP",
             "`MCP_SEARCH_TRANSPORT`, `MCP_SEARCH_URL`, `MCP_AVIATION_TRANSPORT`, "
             "`MCP_AVIATION_URL`, `MCP_WEATHER_TRANSPORT`, `MCP_WEATHER_URL`"],
            ["HTTP and limits",
             "`CORS_ORIGINS`, `RATE_LIMIT_ENABLED`, `RATE_LIMIT_REQUESTS`, "
             "`RATE_LIMIT_WINDOW_SECONDS`, `MAX_REQUEST_SIZE`"],
            ["Guardrails",
             "`GUARDRAILS_ENABLED`, `PROMPT_INJECTION_CHECK_ENABLED`, "
             "`PII_GUARD_ENABLED`, `TOOL_GUARD_ENABLED`"],
            ["Observability and evaluation",
             "`LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, "
             "`LANGSMITH_ENDPOINT`, `EVALUATION_ENABLED`, `EVALUATION_MODE`, "
             "`EVALUATOR_MODEL`"],
            ["Runtime and hosting",
             "`PORT`, `SERVE_FRONTEND`, `FRONTEND_DIST_DIR`, `MAX_REVISION_COUNT`, "
             "`FRONTEND_URL`, `BACKEND_URL`, `ENABLE_MOCK_DATA`"],
        ],
        caption="Every environment variable, grouped. Secret values ship blank.",
        widths=[1.2, 4.6],
    )

    g.understand([
        "The three boundaries where Pydantic validates in this system.",
        "Why a blank environment variable must fall back to a default.",
        "Why derived properties are preferable to duplicated environment variables.",
        "Which environment variables are secrets and which are safe to commit.",
    ])


# ---------------------------------------------------------------------------
def _api_reference(g: Guide) -> None:
    g.h1("API Reference", page_break=True)

    g.p(
        "Every route is prefixed with /api/v1. The prefix is a version, not decoration: "
        "the SPA mount reserves it so that a client-side route can never shadow the "
        "API."
    )

    g.table(
        ["Method", "Path", "Purpose"],
        [
            ["GET", "`/api/v1/health`",
             "Configuration and readiness. Cheap by contract."],
            ["POST", "`/api/v1/trips/plan`",
             "Plan a new journey. Runs the draft pass and returns a reviewable "
             "journey."],
            ["GET", "`/api/v1/trips`",
             "List journeys for the current browser session."],
            ["GET", "`/api/v1/trips/{trip_id}`",
             "Fetch one journey with its results, provider labels and scores."],
            ["DELETE", "`/api/v1/trips/{trip_id}`",
             "Remove a journey and its dependent rows."],
            ["POST", "`/api/v1/trips/{trip_id}/approve`",
             "Approve the draft. Runs the finalise branch and renders the response in "
             "the chosen language."],
            ["POST", "`/api/v1/trips/{trip_id}/request-changes`",
             "Ask for a change. Runs selective re-execution."],
            ["POST", "`/api/v1/trips/{trip_id}/regenerate`",
             "Re-run the draft pass from the original request."],
        ],
        caption="Every HTTP route in JourneyMesh.",
        widths=[0.7, 2.3, 3.4],
    )

    g.h2("Request and response shape")
    g.code(
        """
POST /api/v1/trips/plan
Content-Type: application/json

{
  "user_query": "Plan a relaxing 5-day family trip from Dhaka to Singapore under $2000",
  "constraints": {
    "origin": "Dhaka",
    "destination": "Singapore",
    "departure_date": "2026-11-10",
    "return_date": "2026-11-15",
    "travelers": 4,
    "budget": 2000,
    "currency": "USD",
    "travel_style": "family",
    "interests": ["food", "nature"],
    "preferred_language": "en"
  },
  "session_id": "<opaque browser session id>"
}
""",
        caption="Listing. A planning request. Values are illustrative.",
    )
    g.code(
        """
200 OK

{
  "trip_id": "...",
  "status": "awaiting_review",
  "review_status": "awaiting_review",
  "revision_count": 1,
  "selected_agents": ["flight_agent", "hotel_agent", "weather_agent",
                      "budget_agent", "itinerary_agent"],
  "execution_reason": "...",
  "results": {
    "flights": { "options": [ ... ] },
    "hotels":  { "options": [ ... ] },
    "weather": { "forecast": [ ... ] },
    "budget":  { "breakdown": { ... }, "status": "within_budget" },
    "itinerary": { "days": [ ... ] }
  },
  "provider_status": [ { "provider": "...", "source": "ESTIMATE", ... } ],
  "evaluation": { "overall_score": 0.0, "passed": true, "dimensions": { ... } },
  "guardrails": [ ... ]
}
""",
        caption="Listing. The response envelope. The score shown is a placeholder - "
                "actual values depend on the request.",
    )

    g.h2("Status codes")
    g.table(
        ["Code", "When"],
        [
            ["200", "The request succeeded"],
            ["400", "The request was structurally valid but rejected by a guardrail "
                    "or a domain rule"],
            ["404", "No journey with that identifier belongs to this session"],
            ["409", "The journey is not in a state where this action is allowed - for "
                    "example approving something already approved"],
            ["413", "The body exceeded MAX_REQUEST_SIZE"],
            ["422", "Pydantic rejected the payload; the response names the field"],
            ["429", "The rate-limit window is exhausted"],
            ["500", "An unhandled error. The response carries the request id and no "
                    "internal detail"],
        ],
        caption="Status codes and their meanings.",
        widths=[0.6, 5.2],
    )


# ---------------------------------------------------------------------------
def _services(g: Guide) -> None:
    g.h1("Services and Repositories", page_break=True)

    g.h2("Why there is a service layer at all")
    g.p(
        "A route handler that ran the graph, wrote to the database and formatted a "
        "response would be untestable without an HTTP client and impossible to reuse "
        "from the evaluation runner. The service layer exists so that the sequence "
        "'validate, persist intent, run the workflow, persist the result, shape the "
        "response' lives in one place that can be called from anywhere."
    )

    g.table(
        ["Service", "Responsibility"],
        [
            ["`travel_service.py`",
             "Owns the planning path: creates the trip, invokes the workflow, "
             "persists results, assembles the response envelope"],
            ["`review_service.py`",
             "Owns the human-in-the-loop path: approve, request changes, enforce "
             "MAX_REVISION_COUNT, resume the graph on the right branch"],
            ["`conversation_service.py`",
             "Turns the state's message list into persisted conversation rows"],
            ["`provider_service.py`",
             "Reports which providers and MCP transports are configured, without "
             "contacting any of them"],
            ["`llm_service.py`",
             "Wraps the model client, counts usage, and degrades to a deterministic "
             "mode when no key is configured"],
        ],
        caption="The five services.",
        widths=[1.5, 4.3],
    )

    g.h2("Repositories")
    g.p(
        "Repositories are the only code that writes SQL-shaped operations. Services "
        "call repositories; agents never do. This keeps ORM concerns out of the domain "
        "layer and means a query change has exactly one place to happen."
    )
    g.table(
        ["Repository", "Table", "Typical operations"],
        [
            ["`trip_repository.py`", "`trips`",
             "Create a draft, load with results, list by session, update status, "
             "delete with cascade"],
            ["`review_repository.py`", "`human_reviews`",
             "Record a review, read the latest revision, count revisions"],
            ["`conversation_repository.py`", "`conversation_messages`",
             "Append execution notes, read a trip's history"],
        ],
        caption="The three repositories.",
        widths=[1.5, 1.3, 3.0],
    )

    g.h2("The degraded LLM mode")
    g.p(
        "llm_service reports llm_available as false when no model key is configured, "
        "and the system continues in a deterministic mode: agents produce structured "
        "results from their tools and reference data, and the parts that would have "
        "been model-composed are assembled by rule. This is what makes the repository "
        "runnable immediately after cloning with a blank .env, and it is why the "
        "health endpoint reports `llm: deterministic` rather than an error."
    )
    g.callout(
        "tip",
        "This mode is also the reason the offline evaluation suite can run in CI, "
        "where no provider keys exist. Determinism there is a feature: the same input "
        "produces the same score every time, so a regression is unambiguous.",
    )


# ---------------------------------------------------------------------------
def _i18n(g: Guide) -> None:
    g.h1("Multilingual Support on the Server", page_break=True)

    g.p(
        "JourneyMesh supports English, Bengali and Hindi, with English as the default. "
        "Language is a property of the request, not of the browser: a traveller can "
        "plan in English and read the approved journey in Bengali."
    )

    g.h2("Codes, not prose")
    g.p(
        "Specialist agents never emit translated sentences. They emit message codes "
        "and structured values. The final response agent renders those codes through "
        "the server-side catalogue in app/core/i18n.py, using translate() for one "
        "phrase and translate_all() for a list."
    )
    g.table(
        ["Approach", "Consequence"],
        [
            ["Each agent writes prose in the target language",
             "Five agents must each know three languages; adding a fourth language "
             "means editing five prompts; a model may translate inconsistently"],
            ["Agents emit codes, one renderer translates",
             "Translation lives in one file; adding a language is a catalogue entry; "
             "the same journey renders identically in every language"],
        ],
        caption="Why the second approach was chosen.",
        widths=[2.2, 3.6],
    )

    g.table(
        ["Code", "Language", "Notes"],
        [
            ["`en`", "English", "Default. Every key is defined here first."],
            ["`bn`", "Bengali", "Full catalogue coverage."],
            ["`hi`", "Hindi", "Full catalogue coverage."],
        ],
        caption="Supported languages, from SUPPORTED_LANGUAGES in "
                "app/core/constants.py.",
        widths=[0.7, 1.3, 3.8],
    )

    g.callout(
        "note",
        "Language and theme are independent and are stored under separate keys - "
        "`journeymesh_language` and `journeymesh_theme`. Changing one never changes "
        "the other.",
    )


# ---------------------------------------------------------------------------
def _python_packages(g: Guide) -> None:
    g.h1("Python Dependency Reference", page_break=True)
    g.p(
        f"The backend declares {len(FACTS.python_packages)} direct dependencies in "
        "backend/requirements.txt. Each is listed below with the reason it is present "
        "- a dependency without a justification is a dependency that should be removed."
    )

    reasons = {
        "fastapi": "The web framework. Routing, validation, OpenAPI.",
        "uvicorn[standard]": "The ASGI server that runs the application, with the "
                             "standard extras for HTTP tooling and reload support.",
        "pydantic": "Data validation at every boundary.",
        "pydantic-settings": "Typed configuration loaded once from the environment.",
        "python-dotenv": "Reads a local .env file during development.",
        "httpx": "The async HTTP client used to reach providers and MCP servers.",
        "SQLAlchemy": "ORM and engine. Version 2 typed mappings are used throughout.",
        "alembic": "Schema migrations, so the database shape is versioned with the "
                   "code.",
        "langchain": "Shared abstractions used by the model and agent tooling.",
        "langchain-core": "The message and runnable primitives the graph builds on.",
        "langchain-groq": "The Groq chat model client.",
        "langgraph": "The state machine that is the orchestration layer.",
        "langgraph-checkpoint": "The checkpointing interface, and the in-memory saver "
                                "used locally and in tests.",
        "langgraph-checkpoint-postgres": "The PostgreSQL checkpoint saver used when a "
                                         "PostgreSQL URL is configured.",
        "langsmith": "Optional tracing. Never a hard runtime dependency.",
        "mcp": "The Model Context Protocol SDK. Its absence is detected and the "
               "in-process adapters are used instead.",
        "langchain-mcp-adapters": "Bridges MCP tool definitions into the LangChain "
                                  "tool interface.",
    }
    rows = [
        [f"`{name}`", version or "unpinned", reasons.get(name, "See requirements.txt")]
        for name, version in FACTS.python_packages
    ]
    g.table(
        ["Package", "Constraint", "Why it is here"],
        rows,
        caption="Backend dependencies, read from backend/requirements.txt at "
                "generation time.",
        widths=[1.6, 1.0, 3.2],
        size=8.5,
    )

    g.h2("Dependencies that are deliberately absent")
    g.bullets([
        "No Redis. Rate limiting is in-process, which is honest about the single-"
        "container deployment; a multi-instance deployment would need a shared store, "
        "and that is recorded as a scaling step rather than pretended away.",
        "No Celery or task queue. The draft run completes within one request; the "
        "human pause is handled by checkpointing rather than by a background worker.",
        "No authentication library. There are no user accounts; journeys are scoped "
        "by an opaque browser session id. Adding accounts is a documented extension, "
        "not a hidden feature.",
        "No pypdf or document toolkit in the runtime. Document generation is a "
        "developer script, not a server capability.",
    ])
