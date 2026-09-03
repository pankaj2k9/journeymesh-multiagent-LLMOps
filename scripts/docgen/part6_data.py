"""Persistence: the schema, JSONB, migrations, PostgreSQL and checkpoints."""

from __future__ import annotations

from docgen.builder import Guide


def write(g: Guide) -> None:
    _why_a_database(g)
    _schema(g)
    _jsonb(g)
    _alembic(g)
    _postgres_everywhere(g)
    _checkpoints(g)


# ---------------------------------------------------------------------------
def _why_a_database(g: Guide) -> None:
    g.h1("Persistence", page_break=True)

    g.h2("Why a relational database")
    g.p(
        "The obvious alternative for an LLM application is a document store, or no "
        "store at all. JourneyMesh needs a relational database for a specific reason: "
        "the human-in-the-loop pause. Between the draft and the decision the process "
        "may end. A journey that exists only in memory does not survive that, and on a "
        "free hosting tier the container is genuinely expected to sleep between the "
        "two halves of a conversation."
    )
    g.bullets([
        "The draft must outlive the request that produced it.",
        "Revisions must be countable and bounded, which requires a durable counter.",
        "The audit trail must be append-only and durable, or it is not an audit "
        "trail.",
        "A traveller returning tomorrow must find their journey, and browser storage "
        "is not a place to keep it.",
        "The relationships between a trip, its result, its reviews, its messages and "
        "its audit events are genuinely relational, and cascade deletes are worth "
        "having the database enforce.",
    ])

    g.h2("Two backends, one codebase")
    g.table(
        ["Environment", "Backend", "Reason"],
        [
            ["Tests", "SQLite, in memory",
             "No external service; a clean schema per test run"],
            ["Local development", "SQLite file, or PostgreSQL in Docker",
             "Zero setup by default; PostgreSQL when compose is used"],
            ["Production", "PostgreSQL on the VPS via `DATABASE_URL`",
             "The same engine, in its own container with its own volume, reached "
             "only over the private Compose network"],
        ],
        caption="Database backends by environment.",
        widths=[1.2, 2.1, 2.5],
    )
    g.p(
        "The difference is confined to app/db/database.py, which normalises the URL, "
        "applies an SSL mode where one is required, chooses pool options appropriate to "
        "the driver, and reports which backend is configured. No model, repository or "
        "service contains a branch on the database vendor."
    )


# ---------------------------------------------------------------------------
def _schema(g: Guide) -> None:
    g.h1("The Schema", page_break=True)

    g.diagram(
        """
              +--------------------------------------------+
              |  trips                                     |
              |--------------------------------------------|
              |  id                    PK   String(36)     |
              |  session_id            IX   String(64)     |
              |  user_query                 Text           |
              |  origin, destination        String(120)    |
              |  departure_date, return_date Date          |
              |  travelers                  Integer        |
              |  budget, currency           Float, Str(3)  |
              |  travel_style, hotel_pref   String(32)     |
              |  interests                  JSON           |
              |  special_requirements       Text           |
              |  additional_instructions    Text           |
              |  preferred_language         String(2)      |
              |  status                IX   String(32)     |
              |  review_status              String(32)     |
              |  revision_count             Integer        |
              |  constraints                JSON           |
              |  selected_agents            JSON           |
              |  created_at, updated_at     DateTime(tz)   |
              +----+------------+-----------+--------------+
                   | 1:1        | 1:N       | 1:N        | 1:N
                   v            v           v            v
    +----------------------+ +---------------+ +------------------------+
    | travel_results       | | human_reviews | | conversation_messages  |
    |----------------------| |---------------| |------------------------|
    | id            PK     | | id       PK   | | id              PK     |
    | trip_id       FK  UQ | | trip_id  FK   | | trip_id         FK     |
    | flight_results  JSON | | revision_number| | session_id     IX     |
    | hotel_results   JSON | | review_status | | role, agent            |
    | weather_results JSON | | requested_    | | content         Text   |
    | budget_analysis JSON | |   changes     | | revision_number        |
    | itinerary       JSON | | selected_     | | created_at             |
    | final_summary   JSON | |   agents JSON | +------------------------+
    | provider_metadata    | | change_scope  |
    |                 JSON | |          JSON | +------------------------+
    | evaluation_summary   | | reviewer_note | | audit_events           |
    |                 JSON | | reviewed_at   | |------------------------|
    | guardrail_summary    | +---------------+ | id              PK     |
    |                 JSON |                   | trip_id      FK (null) |
    | created_at/updated_at|                   | request_id      IX     |
    +----------------------+                   | event_type      IX     |
                                               | severity, actor        |
                                               | detail          JSON   |
                                               | created_at             |
                                               +------------------------+
""",
        "The JourneyMesh entity-relationship diagram. Every child row cascades from "
        "its trip.",
    )

    g.h2("The five tables")
    g.table(
        ["Table", "Holds", "Cardinality", "Why it is separate"],
        [
            ["`trips`",
             "The request and its lifecycle status",
             "The root",
             "The one row that exists before any work is done"],
            ["`travel_results`",
             "Every agent's output, plus provider, evaluation and guardrail summaries",
             "One per trip",
             "Result payloads are large and are read as a unit; keeping them out of "
             "`trips` keeps list queries cheap"],
            ["`human_reviews`",
             "One row per review decision",
             "Many per trip",
             "The revision history is the audit of who asked for what and which "
             "agents that selected"],
            ["`conversation_messages`",
             "Execution notes in order",
             "Many per trip",
             "A timeline that can be paged and trimmed independently of the result"],
            ["`audit_events`",
             "Security and lifecycle events",
             "Many per trip, and some with no trip at all",
             "Append-only, queryable by event type and request id, and must survive "
             "even when no trip exists"],
        ],
        caption="The five tables and the reason each one exists.",
        widths=[1.2, 1.7, 1.2, 2.3],
    )

    g.h2("Identifiers and timestamps")
    g.bullets([
        "Primary keys are UUID strings in a String(36) column rather than integers. "
        "They are generated by the application, are safe to expose in a URL, and do "
        "not leak how many journeys exist.",
        "Every timestamp is DateTime(timezone=True) and is written in UTC. Local time "
        "is a presentation concern and is applied in the browser.",
        "session_id, status, event_type and request_id are indexed, because those are "
        "the columns the application actually filters on.",
    ])

    g.h2("Audit events")
    g.p(
        "audit_events is the only table whose trip_id is nullable, because some events "
        "have no trip: a rate-limit rejection, a request that failed input "
        "guardrails, a tool call blocked before a journey existed. The detail column "
        "is JSON and holds the structured context of the event - rule names, agent "
        "names, tool names - and never a secret or a raw argument value."
    )
    g.table(
        ["Event", "Recorded when"],
        [
            ["`TOOL_CALL_BLOCKED`", "The Tool Guard refused an invocation"],
            ["`OUTPUT_VALIDATION_FAILED`", "The output guard rejected an assembled "
                                           "journey"],
            ["`PROVIDER_FAILURE`", "An external call failed or timed out"],
            ["`REVISION_LIMIT_REACHED`", "A traveller hit MAX_REVISION_COUNT"],
        ],
        caption="Representative audit events, from app/core/constants.py.",
        widths=[1.8, 4.0],
    )


# ---------------------------------------------------------------------------
def _jsonb(g: Guide) -> None:
    g.h1("JSONB and the Structured/Unstructured Boundary", page_break=True)

    g.definition(
        "JSONB",
        "PostgreSQL's binary JSON column type. Values are stored in a decomposed "
        "binary form rather than as text, which makes them queryable and indexable "
        "with operators and GIN indexes, at the cost of slightly slower writes.",
        "A column that holds a whole JSON object, and that the database can actually "
        "look inside - not just a string that happens to contain braces.",
    )

    g.h2("What is a column and what is JSON")
    g.p(
        "The rule applied throughout the schema is simple: if the application filters, "
        "sorts or joins on it, it is a column; if the application reads it as a whole "
        "and hands it to the interface, it is JSON."
    )
    g.table(
        ["Data", "Storage", "Why"],
        [
            ["Trip status", "Column, indexed",
             "Filtered on every list query"],
            ["Session id", "Column, indexed", "Scopes every read"],
            ["Departure date", "Column",
             "A real date, compared and sorted as one"],
            ["Interests", "JSON",
             "A short list read as a unit; never filtered on"],
            ["Flight results", "JSON",
             "A nested payload whose shape changes as agents improve; read whole"],
            ["Budget analysis", "JSON",
             "A breakdown rendered as a unit; only its status matters to the "
             "application, and that lives in the payload"],
            ["Evaluation summary", "JSON",
             "Ten dimensions plus checks; read whole, never joined"],
            ["Audit detail", "JSON",
             "Different shape per event type - the classic case for a document "
             "column"],
        ],
        caption="The structured/unstructured boundary, table by table.",
        widths=[1.4, 1.3, 3.1],
    )

    g.h2("The portability layer")
    g.p(
        "SQLite has no JSONB. The models therefore use a JSONType that resolves to "
        "PostgreSQL's JSONB when the dialect supports it and to a JSON-encoded text "
        "column otherwise. The application code is identical either way, which is what "
        "lets the entire test suite run against SQLite while production runs on "
        "PostgreSQL."
    )
    g.callout(
        "warning",
        "The portability has a limit worth stating plainly: JSONB containment "
        "operators and GIN indexes do not exist on SQLite. No query in the codebase "
        "uses them today, and any future query that does will be PostgreSQL-only.",
    )

    g.h2("What this costs")
    g.p(
        "JSON columns trade queryability for flexibility. It is not currently possible "
        "to ask the database \"which journeys had a flight over $800\" without reading "
        "the payloads. That is an accepted trade: the application has no such query, "
        "and promoting a field to a column later is a migration rather than a "
        "redesign."
    )


# ---------------------------------------------------------------------------
def _alembic(g: Guide) -> None:
    g.h1("Migrations with Alembic", page_break=True)

    g.definition(
        "Migration",
        "A versioned, ordered script that transforms a database schema from one "
        "revision to the next, with a recorded identifier so that any database can "
        "report which revision it is at.",
        "A numbered list of changes to the database's shape, so every copy of it - "
        "yours, a colleague's, production - can be brought to the same state in the "
        "same order.",
    )

    g.h2("Why not create_all")
    g.p(
        "SQLAlchemy can create every table from the models in one call. That is "
        "adequate exactly once. It cannot add a column to a table that already holds "
        "rows, cannot rename anything, cannot backfill, and gives no way to know "
        "whether a running database matches the code. Alembic exists so that the "
        "schema has a history."
    )
    g.callout(
        "note",
        "create_all is still used in one place: the ephemeral SQLite backend used by "
        "tests, where the database is created and discarded within a single process "
        "and there is no history to preserve.",
    )

    g.h2("The commands")
    g.table(
        ["Command", "Does"],
        [
            ["`make migrate`", "Upgrade the configured database to the latest "
                               "revision"],
            ["`make migration`", "Autogenerate a revision from a model change, for "
                                 "review before committing"],
            ["`alembic upgrade head`", "The underlying upgrade command"],
            ["`alembic downgrade -1`", "Step back one revision"],
            ["`alembic current`", "Report the revision a database is at"],
            ["`alembic upgrade head --sql`", "Render the SQL without executing it - "
                                             "this is what CI validates"],
        ],
        caption="The migration commands.",
        widths=[1.9, 3.9],
    )

    g.h2("Migrations in CI and at deploy time")
    g.p(
        "CI runs the offline render - `--sql` - which proves that the migration "
        "configuration is valid and every revision is reachable without needing a "
        "database. At deploy time the container entrypoint runs the upgrade before the "
        "server starts, so a failed migration fails the deployment rather than "
        "producing a server that runs against a schema it does not expect."
    )
    g.code(
        """
# The deployment ordering, from backend/docker-entrypoint.sh

  RUN_MIGRATIONS=true  ->  alembic upgrade head   (must succeed)
                       ->  exec uvicorn ... --host 0.0.0.0 --port "$PORT"
""",
        caption="Listing. Migrations run to completion before the server binds a port.",
    )


# ---------------------------------------------------------------------------
def _postgres_everywhere(g: Guide) -> None:
    g.h1("One PostgreSQL, Two Places", page_break=True)

    g.h2("The same engine on a laptop and in production")
    g.p(
        "JourneyMesh runs PostgreSQL in both environments, and the application "
        "cannot tell them apart. Locally it is a `postgres:16-alpine` container in "
        "the compose stack; in production it is the same `postgres:16-alpine` "
        "container on the VPS. There is no managed-provider SDK, no vendor client "
        "library, and no `if vps:` or `if docker:` anywhere in the codebase. The "
        "difference between the two is one environment variable."
    )
    g.table(
        ["", "Local", "Production"],
        [
            ["Runs as", "A container in `docker-compose.yml`",
             "A container in `deploy/docker-compose.prod.yml`"],
            ["Reached at", "`db:5432` on the compose network",
             "`db:5432` on the compose network - the same address"],
            ["Configured by", "`DATABASE_URL` in `.env`",
             "Assembled from `POSTGRES_*` in `/opt/journeymesh/.env` on the VPS"],
            ["Data lives in", "`./db/postgres-data`, bind-mounted",
             "The `postgres-data` named volume, plus a nightly `pg_dump`"],
            ["Reachable from", "The host, on `localhost:5432`",
             "Nothing outside its own container network; `compose exec db psql` "
             "for administration"],
            ["Survives", "`docker compose down`",
             "Every application deployment"],
        ],
        caption="The same database, configured twice.",
        widths=[1.2, 2.3, 2.3],
    )

    g.callout(
        "important",
        "Testing against the same engine you deploy is the point. SQLite is used "
        "for the unit tests because they must be fast and hermetic, but the "
        "development stack runs real PostgreSQL, so a JSONB behaviour or a "
        "constraint that only PostgreSQL enforces is discovered on a laptop rather "
        "than in production.",
    )

    g.h2("Why a container rather than an installed PostgreSQL")
    g.bullets([
        "Nobody has to install or upgrade anything. `docker compose up --build` is "
        "the whole setup, and a new contributor gets the exact version production "
        "runs rather than whichever one their package manager offers.",
        "The version is pinned in a file that is reviewed like any other code, so "
        "two developers cannot silently be on different major versions.",
        "It is disposable. Deleting the data directory and starting again takes a "
        "few seconds and touches nothing else on the machine.",
        "It matches the deployment shape: services talking over a private "
        "container network is exactly what the VPS runs.",
    ])

    g.h2("Reaching it: service names, not localhost")
    g.p(
        "Inside a container, `localhost` means that container - not your machine, "
        "and not the database. The backend therefore reaches PostgreSQL by its "
        "compose service name, which Docker's embedded DNS resolves on the shared "
        "network:"
    )
    g.code(
        """
# Correct - inside the compose network
DATABASE_URL=postgresql+psycopg://journeymesh:journeymesh@db:5432/journeymesh

# Wrong - "localhost" inside the backend container is the backend container
DATABASE_URL=postgresql+psycopg://journeymesh:journeymesh@localhost:5432/journeymesh
""",
        caption="Listing. The single most common Docker networking mistake, and the "
                "reason a test asserts `@db:5432` appears in the compose file and "
                "`@localhost:5432` does not.",
    )
    g.p(
        "Running the backend directly on your machine - `make dev` - inverts this: "
        "there, `localhost:5432` is right, because the process and the port really "
        "are on the same host. The address is configuration, which is why it is "
        "configuration and not code."
    )

    g.h2("Local persistence")
    g.p(
        "The local database is a bind mount rather than a named Docker volume:"
    )
    g.code(
        """
volumes:
  - ./db/postgres-data:/var/lib/postgresql/data
""",
        caption="Listing. From the `db` service in docker-compose.yml.",
    )
    g.bullets([
        "`docker compose down` removes the containers and leaves the data. A named "
        "volume would too, but a bind mount makes that visible: the data is in the "
        "repository, in a directory you can look at.",
        "Rebuilding the images or recreating the containers does not touch it.",
        "The directory's contents are git-ignored. PostgreSQL data files must never "
        "be committed, and a test asserts the ignore rule exists.",
        "Starting fresh is deliberate and explicit: `make docker-down v=1`, which "
        "deletes the data directory and says so.",
    ])

    g.h2("Reference variables in production")
    g.definition(
        "Reference variable",
        "A variable whose value is resolved by the platform at deploy time from "
        "another service in the same project, rather than being a copied literal.",
        "You point at the database instead of writing its password down. The "
        "platform fills in the real value when it deploys.",
    )
    g.p(
        "The backend's production `DATABASE_URL` is assembled by "
        "`deploy/docker-compose.prod.yml` from the `POSTGRES_*` values in "
        "`/opt/journeymesh/.env` - the same values the database container itself is "
        "started with. Nothing is typed twice and nothing is committed: rotating the "
        "password is one edit in one file, and there is no stale copy anywhere to go "
        "wrong."
    )
    g.callout(
        "warning",
        "The alternative - writing a full connection string into a second "
        "variable - looks identical and is worse in three ways: the password is "
        "now in two places, rotating one silently breaks the application, and the "
        "value tends to end up pasted into a chat message or a screenshot.",
    )

    g.h2("Private networking")
    g.p(
        "On the VPS every JourneyMesh container joins one Compose bridge network "
        "that never leaves the host, and only nginx additionally joins the shared "
        "`proxy` network so the VPS-level Caddy can reach it. PostgreSQL publishes "
        "no port at all - not on the internet, and not on loopback either; "
        "administrative access goes through the container with `compose exec`. "
        "The frontend never connects to PostgreSQL: it calls the backend's API, "
        "which is the only thing holding a database credential."
    )
    g.diagram(
        """
                        Internet
                            |
                            | 443 only
                            v
                   +------------------+
                   | shared-caddy     |   /opt/proxy, its own project
                   +--------+---------+  the only published ports
                            |
                            v
                   +------------------+
                   | frontend         |   nginx + React
                   +--------+---------+
                            |  /api
                            v
                   +------------------+
                   | backend          |   FastAPI
                   +--------+---------+
                            |
                   the Compose network
                            |
                            v
                   +------------------+
                   | PostgreSQL       |
                   | 127.0.0.1 only   |
                   +------------------+

   Correct:    shared-caddy -> frontend -> backend -> PostgreSQL
   Never:      frontend -> PostgreSQL
""",
        "Production networking. Exactly one container is reachable from the "
        "internet.",
    )

    g.h2("Connecting to a managed database correctly")
    g.p(
        "One engine configuration serves both environments, and it is built for the "
        "harder case - a database reached over a network. The settings are harmless "
        "against a container on the same machine, which is why there is no branch."
    )
    g.table(
        ["Setting", "Variable", "Why it matters"],
        [
            ["SSL mode", "`DB_REQUIRE_SSL`",
             "A managed database requires TLS; a container on a private network "
             "neither needs nor offers it. `apply_ssl_mode()` adds it when the host "
             "is not local, and always respects an `sslmode` already in the URL"],
            ["Pre-ping", "always on",
             "A pooled connection can be dead after an idle period. Pre-ping "
             "discovers that before a query rather than during one"],
            ["Pool size", "`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`",
             "A managed plan has a connection limit; an oversized pool wastes it"],
            ["Recycle", "`DB_POOL_RECYCLE_SECONDS`",
             "Connections are retired before an idle timeout can close them "
             "underneath the application"],
            ["Connect timeout", "`DB_CONNECT_TIMEOUT_SECONDS`",
             "Bounds how long a request waits for a connection that may never come"],
            ["Statement timeout", "`DB_STATEMENT_TIMEOUT_MS`",
             "A runaway query is bounded server-side rather than holding a "
             "connection indefinitely"],
        ],
        caption="Connection settings, all of them configuration rather than code.",
        widths=[1.1, 1.6, 3.1],
    )

    g.h2("Waiting for the database")
    g.p(
        "Start-up order is not the same thing as readiness. Compose's "
        "`condition: service_healthy` waits for `pg_isready`, which is necessary but "
        "not sufficient - a database can accept a health probe a moment before it "
        "accepts a connection, and in production there is no Compose at all. The "
        "container entrypoint therefore retries the connection itself for up to "
        "sixty seconds before giving up, so the application is resilient to a slow "
        "database rather than dependent on something else having sequenced it."
    )
    g.code(
        """
# backend/docker-entrypoint.sh

wait_for_database() {
  ...
  log "waiting for the database (up to ${DB_WAIT_SECONDS}s)..."
  until python -c '<connect with a 3s timeout>' ; do
    waited=$((waited + 2))
    [ "$waited" -ge "$DB_WAIT_SECONDS" ] && return 1
    sleep 2
  done
  log "database is reachable"
}
""",
        caption="Listing. Two independent protections: the orchestrator sequences, "
                "and the application retries.",
    )

    g.understand([
        "Why the same PostgreSQL configuration serves a container and a managed "
        "service.",
        "Why `localhost` is wrong inside a container and right outside one.",
        "What a bind mount gives you that a named volume does not.",
        "What a reference variable is, and the three ways a copied connection "
        "string is worse.",
        "Why the entrypoint retries even though Compose already waited.",
    ])


def _checkpoints(g: Guide) -> None:
    g.h1("Checkpointing the Workflow", page_break=True)

    g.p(
        "Checkpointing is separate from the application's own tables. The application "
        "persists what a traveller should see - the trip, its result, its reviews. The "
        "checkpointer persists what the graph needs to resume - the full TravelState at "
        "each node boundary, keyed by thread."
    )

    g.table(
        ["Concern", "Application tables", "Checkpoint store"],
        [
            ["Owned by", "Repositories and services", "LangGraph"],
            ["Shape", "Five typed tables", "Opaque serialised state"],
            ["Read by", "The API and the interface", "The graph, on resume"],
            ["Keyed by", "Trip id", "Thread id - which is the trip id"],
            ["Lifetime", "As long as the journey exists",
             "As long as a run may be resumed"],
        ],
        caption="Two persistence layers with two different jobs.",
        widths=[1.1, 2.3, 2.4],
    )

    g.h2("Choosing the saver")
    g.p(
        "The workflow builds a checkpointer at construction: the in-memory saver when "
        "there is no PostgreSQL to talk to, and the PostgreSQL saver when there is. "
        "The graph code is identical in both cases. In tests and in the offline "
        "evaluation runner the in-memory saver is the correct choice - a run completes "
        "within a process and there is nothing to resume across."
    )

    g.h2("Thread identity")
    g.p(
        "The checkpoint thread id is the trip id. That is what makes resuming "
        "possible: a request to approve trip abc123 resumes thread abc123, and the "
        "state that comes back is exactly what the draft run left behind - including "
        "the flight results that a later revision must preserve."
    )

    g.callout(
        "tip",
        "In an interview, this is the crispest way to describe the whole "
        "human-in-the-loop design: the graph does not wait, it stops; the checkpoint "
        "is the memory; the trip id is the address; and the entry router decides which "
        "branch a resumed run takes.",
    )

    g.understand([
        "Why the human-in-the-loop pause forces a durable store.",
        "Which fields are columns, which are JSON, and the rule that decides.",
        "Why Alembic exists when create_all would produce the same tables.",
        "Which connection settings a serverless database needs and why.",
        "The difference between the application's tables and the checkpoint store.",
    ])
