# JourneyMesh

**Every journey, intelligently connected.**

JourneyMesh turns a sentence like *"plan a relaxing 5-day family trip from Dhaka to
Singapore with a budget of $2,000"* into a reviewable travel plan: routes, a shortlist of
stays, a forecast, a cost breakdown that separates confirmed prices from estimates, and a
day-by-day itinerary you can send back for changes without regenerating the parts you
already liked.

It is built as a production-shaped agentic system rather than a chatbot: a supervisor
decides which specialists a request actually needs, every external call is authorised
before it leaves the process, every draft is measured, and nothing is final until a human
approves it.

---

## Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Dynamic supervisor](#dynamic-supervisor)
- [Specialist agents](#specialist-agents)
- [Budget agent](#budget-agent)
- [Shared TravelState](#shared-travelstate)
- [MCP architecture](#mcp-architecture)
- [MCP tool guard](#mcp-tool-guard)
- [Human-in-the-loop](#human-in-the-loop)
- [Request-changes workflow](#request-changes-workflow)
- [Selective agent re-execution](#selective-agent-re-execution)
- [LangGraph checkpointing](#langgraph-checkpointing)
- [Guardrails](#guardrails)
- [Evaluation](#evaluation)
- [Security](#security)
- [Observability](#observability)
- [Internationalisation](#internationalisation)
- [Project structure](#project-structure)
- [Environment variables](#environment-variables)
- [Local setup](#local-setup)
- [PostgreSQL setup](#postgresql-setup)
- [API reference](#api-reference)
- [Testing](#testing)
- [Offline evaluation](#offline-evaluation)
- [Docker](#docker)
- [Vercel deployment](#vercel-deployment)
- [Render PostgreSQL setup](#render-postgresql-setup)
- [Troubleshooting](#troubleshooting)
- [Author](#author)
- [License](#license)

---

## Overview

| Layer | Technology |
| --- | --- |
| Interface | React 18, TypeScript, Vite, React Router, TanStack Query, Tailwind CSS, i18next |
| API | FastAPI, Pydantic v2 |
| Orchestration | LangGraph, LangChain |
| Tools | Model Context Protocol (MCP) client, aviation / search / custom weather servers |
| Storage | PostgreSQL, SQLAlchemy 2.0, Alembic, LangGraph PostgreSQL checkpoints |
| Quality | Deterministic evaluation rules plus optional LLM-as-judge |
| Tests | pytest (154 tests), Vitest + React Testing Library (21 tests), an offline eval suite |
| Packaging | Multi-stage Docker images for both halves, Docker Compose, Vercel configs |

JourneyMesh runs end to end with **no third-party credentials at all**. Without an API key
each provider falls back to a deterministic adapter whose output is labelled `ESTIMATE`,
so the whole workflow - routing, guardrails, review, evaluation - can be exercised
offline. Nothing is ever presented as a live price unless a provider confirmed it.

---

## Features

- A supervisor that picks agents per request instead of running all of them
- Five specialists (flight, hotel, weather, budget, itinerary) plus a final response agent
- Every external call routed through an MCP client and an authorisation guard
- Input guardrails: relevance, semantics, payload size, unsafe markup, prompt injection, PII
- Output guardrails: schema, completeness, credential leakage, unsafe URLs, consistency
- A ten-dimension evaluation module, deterministic first, model-judged only where necessary
- Human-in-the-loop review with an approve / request-changes loop and a revision limit
- Dependency-aware selective re-execution: change the hotel, keep the flights
- PostgreSQL persistence for trips, results, reviews, conversations and audit events
- LangGraph checkpointing so the workflow pauses at review and resumes later
- English, Bengali and Hindi across both the interface and the generated journey
- Structured JSON logging with PII redaction, in-process tracing and metrics
- Rate limiting, security headers, request-size limits and safe error envelopes

---

## Architecture

```text
USER
  |
  v
React frontend  (planner, trip view, review controls, history)
  |
  v
FastAPI  /api/v1
  |
  v
Security middleware  (request id, size limit, rate limit, headers)
  |
  v
INPUT GUARDRAILS ---- blocked ----> safe rejection payload
  |
  | passed
  v
SUPERVISOR AGENT  (decides which specialists this request needs)
  |
  +-------------+-------------+-------------+--------------+
  v             v             v             v              v
Flight        Hotel        Weather        Budget        Itinerary
  |             |             |             |              |
  +-------------+------+------+-------------+--------------+
                       v
                 MCP TOOL GUARD   (allowlist, agent, args, risk, budget)
                       v
                 MCP CLIENT  ->  aviation / search / weather servers
                       v
                 SHARED TravelState
                       v
                  OUTPUT GUARD
                       v
                  EVALUATION
                       v
                HUMAN-IN-THE-LOOP
                  |            |
              APPROVE     REQUEST CHANGES
                  |            |
                  |            v
                  |       Supervisor  -> affected agents only
                  |            |
                  |            v
                  |       re-run, update state, guard, evaluate
                  |            |
                  +<-----------+
                  v
          FINAL RESPONSE AGENT  (renders in en / bn / hi)
                  v
             PostgreSQL
```

### Design principle

Responsibilities are kept apart, and the module boundaries follow them:

| Concern | Owner |
| --- | --- |
| What should happen for one part of the journey | the specialist agents |
| Which agents should run at all | the supervisor |
| How an external service is reached | the MCP client and server configs |
| Whether a tool call is permitted | the tool guard |
| What may enter and leave a model | the guardrails |
| How good the result is | the evaluation module |
| Whether the result is accepted | the human reviewer |
| What is recorded, and what must never be | observability and the audit trail |
| What survives a restart | PostgreSQL and the LangGraph checkpointer |

---

## Dynamic supervisor

The supervisor reads the request and returns a routing decision. It never plans the trip
itself.

```json
{
  "selected_agents": ["hotel_agent", "budget_agent", "itinerary_agent"],
  "trip_constraints": { "max_hotel_price_per_night": 120 },
  "execution_reason": "Re-running because the change concerns accommodation; the cost picture changes.",
  "change_scope": ["hotel_agent"]
}
```

| Request | Agents that run |
| --- | --- |
| "What will the weather be like in Dubai next week?" | `weather_agent` |
| "Plan a 5-day family trip to Dubai under $3,000." | all five specialists |
| "Find a cheaper hotel but keep my flights." | `hotel_agent`, `budget_agent`, `itinerary_agent` |
| "Change my departure flight." | `flight_agent`, `budget_agent`, `itinerary_agent` |

Routing is rule-based and deterministic by default. When a model is configured it may
widen or narrow the selection, but it can only choose from the known agent set, and the
rule-based result stands if the model returns anything unusable. Only a short, safe
execution summary is stored - never model reasoning.

---

## Specialist agents

**Flight agent** resolves both cities to airports, asks the aviation tool for routes, and
normalises whatever comes back. It never invents a flight number, schedule, availability
or fare. Every price carries one of four labels: `LIVE`, `SEARCH_DERIVED`, `ESTIMATE`,
`UNAVAILABLE`. AviationStack schedules arrive without fares, so those options are marked
`UNAVAILABLE` rather than being filled in.

**Hotel agent** derives a nightly ceiling from the budget, the trip length and the travel
style (or takes an explicit ceiling from a change request), asks the search tool for
candidates, and ranks them on price fit, rating, party size, distance and interests.

**Weather agent** calls the custom weather MCP for current conditions and a forecast that
covers the travel window, then turns that into packing advice and activity guidance the
itinerary agent can act on.

**Itinerary agent** builds the day structure deterministically - arrival and departure
days, pacing per travel style, travel time, rest, indoor swaps when rain is likely or the
afternoon is too hot - and uses a model, when one is configured, only to make activity
titles specific to the city.

**Final response agent** runs after approval, assembles the approved slices into one
validated `FinalJourney`, and renders every generated sentence in `en`, `bn` or `hi`.

---

## Budget agent

`backend/app/agents/budget_agent.py` produces a structured cost picture and keeps
provider-confirmed prices and JourneyMesh estimates in separate buckets:

```json
{
  "currency": "USD",
  "total_budget": 3000,
  "estimated_total": 2650,
  "breakdown": {
    "flights": 900,
    "hotels": 850,
    "food": 400,
    "transport": 200,
    "activities": 200,
    "miscellaneous": 100
  },
  "line_provenance": {
    "flights": { "amount": 900, "source": "ESTIMATE", "basis": "long-haul fare band x 3 travellers" },
    "hotels":  { "amount": 850, "source": "SEARCH_DERIVED", "basis": "170/night x 5 nights" }
  },
  "remaining_budget": 350,
  "budget_status": "within_budget",
  "confirmed_cost_total": 850,
  "estimated_cost_total": 1800,
  "recommendations": ["About 350 USD is unspent - it covers a guided day trip."]
}
```

Statuses are `within_budget`, `near_limit`, `over_budget` and `insufficient_data`. The
agent is independently callable, so a change that only affects cost re-runs the budget
without touching anything else.

---

## Shared TravelState

`backend/app/graph/state.py` defines the single structure every node reads and writes:
`user_query`, `trip_constraints`, `selected_agents`, `flight_results`, `hotel_results`,
`weather_info`, `budget_analysis`, `itinerary_plan`, `messages`, `provider_status`,
`evaluation_results`, `guardrail_results`, `human_review_status`, `requested_changes`,
`change_scope`, `llm_calls`, `tool_calls`, `trip_id`, `session_id`, `created_at`,
`updated_at`.

Each specialist owns exactly one slice (`AGENT_STATE_KEYS`). Agents never call each other,
which is precisely what makes selective re-execution safe: an agent that does not run
keeps its slice byte-for-byte.

---

## MCP architecture

```text
JourneyMesh
    |
    v
MCP client  (transport, dispatch, normalisation, provider status)
    |
    +-- aviation server   search_flights, lookup_airport
    +-- search server     search_hotels, web_search
    +-- weather server    get_current_weather, get_weather_forecast   (custom, this repo)
```

Transport configuration, tool discovery, invocation, authorisation, provider normalisation
and agent logic all live in separate modules. Both `stdio` and streamable HTTP are
supported; when a server is not reachable, or the MCP SDK is not installed, the client
falls back to the in-process adapter for that tool and says so in the provider status.

The weather server is a real MCP server and can be run on its own:

```bash
cd backend
python -m app.mcp.weather_server        # speaks MCP over stdio
```

Point the backend at it with `MCP_WEATHER_TRANSPORT=stdio`.

---

## MCP tool guard

```text
Agent -> Tool Guard -> MCP client -> MCP server
```

The guard denies by default. For every call it checks that the tool is allowlisted and
enabled, that the requesting agent is authorised for it, that the arguments match the
declared schema, that no credential or travel-document field is being forwarded, that the
per-run call budget is not exhausted, and that the operation class is one JourneyMesh may
perform without asking.

```python
TOOL_POLICIES = {
    "search_flights": {
        "allowed_agents": ["flight_agent"],
        "operation": "search",
        "risk": "low",
        "requires_confirmation": False,
        "max_calls_per_run": 4,
    },
    ...
}
```

Operations are classified `READ`, `SEARCH`, `WRITE` and `DESTRUCTIVE`. JourneyMesh
performs only `READ` and `SEARCH` autonomously. Booking, payment, cancellation and
outbound messaging are declared in the policy table, disabled, and marked
`requires_confirmation: true` so the boundary is explicit rather than implicit.

---

## Human-in-the-loop

Review is not optional. After the specialists finish, the output guard and the evaluator
run and the workflow **ends** at the review node with its state checkpointed. The trip
page shows `DRAFT`, `AWAITING REVIEW`, `REVISION IN PROGRESS` or `APPROVED`, with two
controls: **Approve** and **Request changes**.

Approving resumes the workflow on the finalise branch, the final response agent assembles
the journey in the chosen language, and the result is persisted.

---

## Request-changes workflow

```text
User requests changes
      -> input guardrails on the change text
      -> supervisor analyses which agents it affects
      -> only those agents, plus their dependents, re-run
      -> the state is updated in place
      -> output guard
      -> evaluation
      -> back to human review
```

```http
POST /api/v1/trips/{trip_id}/request-changes
{
  "requested_changes": "Find a cheaper hotel under $120 per night.",
  "response_language": "en"
}
```

```json
{
  "trip_id": "…",
  "revision": 2,
  "selected_agents": ["hotel_agent", "budget_agent", "itinerary_agent"],
  "change_scope": ["hotel_agent"],
  "status": "awaiting_review"
}
```

---

## Selective agent re-execution

Dependencies are declared once, in `AGENT_DEPENDENTS`, and the supervisor expands the
change scope through them:

| You say | Re-runs | Preserved |
| --- | --- | --- |
| "Find a cheaper hotel." | hotel, budget, itinerary | flights, weather |
| "Change my departure flight." | flight, budget, itinerary | hotels, weather |
| "The weather looks bad, change activities." | itinerary (weather only if it must be refreshed) | flights, hotels |
| "Reduce the entire trip below $2,000." | budget, hotel, flight, itinerary | weather |

The supervisor also understands preservation phrasing: *"find a cheaper hotel, **keep my
flights**"* removes the flight agent from the scope even though the sentence contains the
word *flights*. `backend/tests/test_graph_workflow.py` asserts the preserved slices are
identical objects after a revision, not merely similar.

### Revision limit

`revision_count` and `review_iteration` are tracked on the state and persisted.
`MAX_REVISION_COUNT` (default 3) caps the loop: past it the review node returns
`revision_limit_reached`, the API answers `409`, and the interface offers approve or start
again. The graph has no unbounded cycle.

---

## LangGraph checkpointing

When `DATABASE_URL` is set, LangGraph checkpoints to PostgreSQL
(`langgraph-checkpoint-postgres`), keyed by `thread_id = trip_id`; otherwise it uses an
in-memory saver. Because the graph ends at the review node, the checkpoint *is* the pause:
approving or requesting a change hours later re-enters the graph with the previous state
intact. Nothing is replanned that the traveller did not ask to change, and no workflow has
to be restarted from the beginning.

---

## Guardrails

**Input** (`app/guardrails/input_guard.py`) - Pydantic handles structure; this layer adds
payload size, unsafe markup, prompt-injection screening, travel relevance, semantic checks
(`departure_date <= return_date`, `budget >= 0`, `travelers > 0`, trip length, dates not in
the past), supported response language, and PII redaction. A blocked request returns a
safe `status: "blocked"` payload with guidance instead of an error.

**Prompt injection** (`prompt_injection.py`) - a weighted rule set covering instruction
override, system-prompt disclosure, secret extraction, local file access, shell execution,
permission escalation, hidden tool invocation, guardrail disabling, role confusion and
exfiltration. It is enforced in the application layer, not by asking a model nicely.

**PII** (`pii_guard.py`) - passports, national IDs, card numbers (Luhn-checked), IBANs,
emails, phone numbers and credential-shaped strings are redacted before anything reaches a
model, an MCP server, a log line or the audit trail. ISO dates are explicitly not mistaken
for phone numbers.

**Output** (`output_guard.py`) - JSON parse, Pydantic validation, then required sections
for the agents that ran, credential and connection-string detection, unsafe markup and URL
schemes, budget arithmetic, itinerary length against the trip length, duplicate activities,
and a final PII pass.

---

## Evaluation

`backend/app/evaluation/` measures ten dimensions: relevance, completeness, groundedness,
consistency, tool correctness, schema validity, safety, language correctness, itinerary
feasibility and budget consistency.

Anything decidable is decided by a rule - date arithmetic, budget arithmetic, schema
validity, provenance labels, required sections, provider success, duplicate activities,
output language script. `EVALUATION_MODE` selects `deterministic` (default), `hybrid` or
`llm_judge`; the model is used only for recommendation relevance, clarity and preference
alignment, and reports `skipped` rather than guessing when no model is configured. Private
reasoning is never surfaced.

---

## Security

- CORS restricted to `CORS_ORIGINS`
- Fixed-window rate limiting per client with `X-RateLimit-*` headers
- Request-size limits before parsing (`MAX_REQUEST_SIZE`)
- Security headers: CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Permissions-Policy`, COOP/CORP, HSTS in production, and no `Server` header
- Safe error envelopes - internals never reach the client, docs disabled in production
- Secrets read through one module, reported as present/absent and never echoed
- Tool authorisation on every external call; provider timeouts on every request
- An audit trail of `PROMPT_INJECTION_BLOCKED`, `TOOL_CALL_BLOCKED`, `INVALID_REQUEST`,
  `RATE_LIMIT_EXCEEDED`, `OUTPUT_VALIDATION_FAILED`, `PROVIDER_FAILURE`, `PII_REDACTED`,
  `HUMAN_REVIEW_APPROVED`, `HUMAN_REVIEW_CHANGES_REQUESTED`, `REVISION_LIMIT_REACHED`

No secret is ever exposed through `VITE_*` variables, API responses, logs, localStorage or
git. `.env` is git-ignored; `.env.example` ships with empty values.

---

## Observability

Structured JSON logs carry `request_id`, `trip_id`, `session_id`, `agent_name`,
`tool_name`, `provider`, `latency_ms`, success/failure, evaluation score, guardrail
decision, `revision_count`, `human_review_status` and token usage when the provider
reports it. Every record passes through the PII redactor before it is written. Spans are
collected in-process per request; counters and latency percentiles are exposed on the
health endpoint.

---

## Internationalisation

English (`en`, default), Bengali (`bn`) and Hindi (`hi`), on both sides:

- **Interface** - `i18next` + `react-i18next`, catalogues at
  `frontend/src/locales/{en,bn,hi}/common.json` (264 keys, kept in step by a test). No
  user-facing string is hard-coded: `<h1>{t('planner.planJourney')}</h1>`, never
  `<h1>Plan your journey</h1>`. The choice is stored in `localStorage`, defaults to English
  when nothing is stored, and updates the `<html lang>` attribute.
- **Generated journey** - agents emit *phrase codes*; the final response agent renders them
  from `backend/app/core/i18n.py`. The output language therefore does not depend on a
  translation model being configured, and it cannot drift between revisions.

`response_language` is sent with every plan, approve and change request.

---

## Project structure

```text
journeymesh-multiagent-LLMOps/
├── backend/
│   ├── app/
│   │   ├── main.py                    FastAPI application factory
│   │   ├── api/          router.py, deps.py, routes/{health,travel,history,review}.py
│   │   ├── agents/       supervisor, flight, hotel, weather, budget, itinerary, final_response
│   │   ├── graph/        state.py, routing.py, travel_graph.py
│   │   ├── mcp/          client.py, config.py, registry.py, aviation.py, search.py, weather_server.py
│   │   ├── guardrails/   input_guard, output_guard, prompt_injection, pii_guard, tool_guard, policies
│   │   ├── evaluation/   evaluator, schemas, metrics, rules, quality_checks, runner
│   │   ├── security/     rate_limit, headers, request_security, secret_manager, audit
│   │   ├── observability/ tracing, logging, metrics
│   │   ├── services/     travel, review, conversation, provider, llm
│   │   ├── db/           database.py, models.py, repositories/
│   │   ├── schemas/      travel, flight, hotel, weather, budget, itinerary, review, evaluation
│   │   └── core/         config.py, constants.py, exceptions.py, i18n.py
│   ├── alembic/          migration environment and versions
│   ├── tests/            154 tests
│   ├── evals/            cases.json, run_offline_eval.py
│   ├── api/index.py      Vercel ASGI entry point
│   ├── Dockerfile, docker-entrypoint.sh, .dockerignore
│   ├── requirements.txt, vercel.json, .env.example
│
├── frontend/
│   └── src/
│       ├── components/   common/, layout/, planner/, trip/, review/, language/
│       ├── pages/        HomePage, TripPage, HistoryPage, AboutPage, SettingsPage, NotFoundPage
│       ├── api/          client.ts, trips.ts, reviews.ts
│       ├── hooks/        useTrips.ts, useLanguage.ts
│       ├── types/        the API contract in TypeScript
│       ├── utils/        format.ts, constants.ts, session.ts
│       ├── i18n/config.ts
│       ├── locales/      en/, bn/, hi/
│       ├── test/         Vitest suites
│       ├── App.tsx, main.tsx, index.css
│       └── ...
│   ├── Dockerfile, nginx.conf, .dockerignore
│   └── vite.config.ts, tailwind.config.js, vercel.json, .env.example
│
├── docker-compose.yml     db + API + interface
├── docker-compose.dev.yml Hot-reload overlay
├── .env.example           Compose-stack settings
├── scripts/smoke.py       End-to-end check against a running instance
├── docs/ARCHITECTURE.md
├── Makefile, LICENSE, README.md
```

---

## Environment variables

`backend/.env` (copy from `backend/.env.example`; every value may be left empty):

| Variable | Purpose |
| --- | --- |
| `APP_NAME`, `APP_ENV`, `DEBUG` | Application identity and mode |
| `DATABASE_URL` | PostgreSQL connection string. Empty falls back to an ephemeral database |
| `GROQ_API_KEY`, `GROQ_MODEL` | Chat model. Empty means every agent uses its deterministic path |
| `TAVILY_API_KEY` | Hotel and destination research |
| `AVIATIONSTACK_API_KEY` | Live flight schedules |
| `OPENWEATHER_API_KEY` | Live weather |
| `MCP_SEARCH_TRANSPORT`, `MCP_SEARCH_URL` | Search MCP transport: `stdio`, `streamable_http`, `disabled` |
| `MCP_AVIATION_TRANSPORT`, `MCP_AVIATION_URL` | Aviation MCP transport |
| `MCP_WEATHER_TRANSPORT`, `MCP_WEATHER_URL` | Weather MCP transport |
| `CORS_ORIGINS` | Comma-separated allowed origins |
| `RATE_LIMIT_ENABLED`, `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW_SECONDS` | Rate limiting |
| `MAX_REQUEST_SIZE` | Maximum request body in bytes |
| `GUARDRAILS_ENABLED`, `PROMPT_INJECTION_CHECK_ENABLED`, `PII_GUARD_ENABLED`, `TOOL_GUARD_ENABLED` | Guardrail switches |
| `EVALUATION_ENABLED`, `EVALUATION_MODE`, `EVALUATOR_MODEL` | Evaluation |
| `MAX_REVISION_COUNT` | Human-in-the-loop revision limit |
| `FRONTEND_URL`, `BACKEND_URL` | Deployment URLs |
| `ENABLE_MOCK_DATA` | Deterministic provider fallbacks in development |

`frontend/.env`:

| Variable | Purpose |
| --- | --- |
| `VITE_API_BASE_URL` | Base URL of the API. Empty in development uses the Vite proxy |

Only `VITE_*` variables reach the browser, and none of them is a secret.

---

## Local setup

Two commands, from the repository root:

```bash
make setup     # venv, backend deps, frontend deps, both .env files
make dev       # API on :8000 and the interface on :5173, together
```

`make dev` runs both processes in one terminal with `[api]` and `[web]` prefixes;
Ctrl-C stops both. Then open:

- <http://localhost:5173> - the interface
- <http://127.0.0.1:8000/docs> - the API documentation
- <http://127.0.0.1:8000/api/v1/health> - status, providers, MCP catalogue

Nothing needs to be filled in first. Every credential in `backend/.env` may stay empty:
JourneyMesh runs offline and labels every unconfirmed price as an `ESTIMATE`.

Prefer containers? `make docker-up` brings up PostgreSQL, the API and the interface
together - see [Docker](#docker).

### The rest of the Makefile

| Command | What it does |
| --- | --- |
| `make help` | The full list (also the default target) |
| `make setup` | venv, backend deps, frontend deps, `.env` files |
| `make dev` | Run the API and the interface together |
| `make backend-run` / `make frontend-dev` | Run one half only |
| `make stop` | Free ports 8000 and 5173 |
| `make test` | pytest and vitest |
| `make lint` / `make typecheck` | ruff and TypeScript |
| `make eval` | The offline evaluation suite |
| `make build` | Production frontend build |
| `make verify` | Tests, evaluation and build in one go |
| `make migrate` / `make migration m="..."` | Alembic |
| `make health` / `make smoke` | Check a running instance |
| `make info` | Resolved paths, ports and setup state |
| `make clean` / `make reset` | Remove caches / caches plus venv and node_modules |

Ports can be overridden per invocation: `make dev BACKEND_PORT=9000 FRONTEND_PORT=3000`.

`make smoke` (`scripts/smoke.py`) drives a running API end to end - it plans a journey,
asks for a cheaper hotel while keeping the flights, checks that the untouched results were
preserved, and approves the result in Bengali:

```text
  health     ok  |  db ephemeral_sqlite  |  llm deterministic
  planned    awaiting_review  |  agents: flight_agent, hotel_agent, weather_agent, budget_agent, itinerary_agent
             quality 1.00  |  5 days  |  estimated 2609 USD (within_budget)
  revision 2  re-ran: hotel_agent, budget_agent, itinerary_agent
             flights and weather preserved: True
             new nightly rate: 83.33
  approved   Singapore-এ 5 দিনের ভ্রমণ
```

### Without make

<details>
<summary>Manual setup, if you would rather not use the Makefile</summary>

**Backend**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # every value may stay empty
uvicorn app.main:app --reload --port 8000 --no-server-header
```

**Frontend**

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

The dev server proxies `/api` to port 8000, so `VITE_API_BASE_URL` can stay empty.

</details>

## PostgreSQL setup

```bash
createdb journeymesh
# backend/.env
DATABASE_URL=postgresql://<user>:<password>@localhost:5432/journeymesh

cd backend
alembic upgrade head
```

The schema is owned by Alembic. Trips, travel results, human reviews, conversation
messages and audit events use `JSONB` where the payload is document-shaped. API keys are
never stored in the database.

Without `DATABASE_URL` the API still runs on an ephemeral in-memory database - useful for a
demo, and reported honestly by `/api/v1/health` as `ephemeral_sqlite`. Journeys do not
survive a restart in that mode.

---

## API reference

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/health` | Status, provider configuration, MCP catalogue, metrics |
| `POST` | `/api/v1/trips/plan` | Plan a journey; returns a draft awaiting review |
| `GET` | `/api/v1/trips` | List journeys for the calling session |
| `GET` | `/api/v1/trips/{trip_id}` | One journey with its review history |
| `DELETE` | `/api/v1/trips/{trip_id}` | Delete a journey and everything attached to it |
| `POST` | `/api/v1/trips/{trip_id}/approve` | Approve and produce the final journey |
| `POST` | `/api/v1/trips/{trip_id}/request-changes` | Ask for changes; re-runs only what is affected |
| `POST` | `/api/v1/trips/{trip_id}/regenerate` | Re-plan the whole journey (counts as a revision) |

```bash
curl -X POST http://127.0.0.1:8000/api/v1/trips/plan \
  -H 'Content-Type: application/json' \
  -d '{
        "query": "Plan a relaxing 5-day family trip from Dhaka to Singapore with a budget of $2000. We like nature, local food and child-friendly activities.",
        "origin": "Dhaka",
        "destination": "Singapore",
        "departure_date": "2027-01-10",
        "return_date": "2027-01-14",
        "travelers": 3,
        "budget": 2000,
        "currency": "USD",
        "travel_style": "family",
        "interests": ["food", "nature", "family_activities"],
        "response_language": "en"
      }'
```

---

## Testing

```bash
make verify                       # everything below, in one command

make backend-test                 # pytest, 154 tests
make frontend-test                # vitest, 21 tests
make eval                         # the offline evaluation suite
make build                        # production frontend build
```

The backend suite covers the health endpoint, trip planning, dynamic routing, each
specialist agent, the shared state, MCP calls and the tool guard, input and output
guardrails, prompt injection, PII redaction, evaluation, persistence, LangGraph
checkpointing, and the human-in-the-loop pause/resume cycle - including the critical
regression:

> Start with `flight_results = A`, `hotel_results = B`, `weather_results = C`.
> Ask for "cheaper hotels". Hotel, budget and itinerary must re-run; flight and weather
> must not; `flight_results` must still be `A` and `weather_results` still `C`.

The frontend suite covers translation-key parity across all three languages, planner
validation and payload construction, the review controls including the revision limit, the
provenance labelling in the budget panel, and the formatting helpers.

---

## Offline evaluation

```bash
cd backend
python -m evals.run_offline_eval               # every case
python -m evals.run_offline_eval --case weather_only
```

The suite drives the real graph with providers in their offline mode - no credentials, no
network - and checks routing, blocking, output language, selective re-execution and the
evaluation score for each case. A JSON report is written to `backend/evals/reports/`.

---

## Docker

The whole stack - PostgreSQL, the API and the interface - runs with one command.

```bash
cp .env.example .env        # optional; every value may stay empty
docker compose up --build   # or: make docker-up
```

- <http://localhost:5173> - the interface
- <http://localhost:8000/docs> - the API
- PostgreSQL on `localhost:5432`

`.env` at the repository root configures the compose stack only; running the backend
directly (`make dev`) still uses `backend/.env`.

### What the stack contains

| Service | Image | Role |
| --- | --- | --- |
| `db` | `postgres:16-alpine` | Trips, results, reviews, audit events and LangGraph checkpoints, on a named volume |
| `migrate` | built from `backend/` | Runs `alembic upgrade head` once, then exits |
| `api` | built from `backend/` | FastAPI + LangGraph under uvicorn, as a non-root user |
| `web` | built from `frontend/` | The production bundle served by nginx, which also proxies `/api` to `api` |

Ordering is enforced rather than hoped for: `api` waits for `db` to pass its
`pg_isready` health check *and* for `migrate` to exit successfully; `web` waits for `api`
to report healthy on `/api/v1/health`. Every service has a health check and rotating logs.

Because nginx proxies `/api` to the API container, the browser only ever talks to one
origin - so `VITE_API_BASE_URL` stays empty and the stack needs no CORS configuration.

### Images

**Backend** (`backend/Dockerfile`) is a two-stage build: dependencies are compiled into a
virtualenv in a builder stage, and the runtime stage carries only `libpq5` and `curl`. It
runs as uid 10001, deletes any stray `.env` from the build context, and has a health
check. `backend/docker-entrypoint.sh` accepts:

| Command | Behaviour |
| --- | --- |
| `serve` (default) | Wait for the database, apply migrations if `RUN_MIGRATIONS=true`, start uvicorn |
| `migrate` | Apply Alembic migrations and exit |
| anything else | Executed verbatim - `docker compose run --rm api pytest -q` works |

`RELOAD=true` swaps uvicorn's worker pool for `--reload`, which is what the development
overlay uses.

**Frontend** (`frontend/Dockerfile`) has four stages: `deps`, `dev` (the Vite dev server),
`builder` (type-check plus bundle) and `runtime` (nginx serving the static output).
`frontend/nginx.conf` adds the SPA fallback so `/trip/:id` and `/history` survive a
refresh, security headers, gzip, immutable caching for hashed assets, a `/healthz`
endpoint, and the `/api` proxy. The upstream is resolved through Docker's DNS at request
time, so the API container can restart without taking nginx down with it.

### Development with hot reload

```bash
make docker-dev
# or: docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

The overlay mounts both source trees, runs uvicorn with `--reload` and Vite's dev server,
switches the API to human-readable logs, and points the interface at
`http://localhost:8000` with CORS configured for it.

### Make targets

| Command | What it does |
| --- | --- |
| `make docker-up` | Build and start the stack in the background |
| `make docker-dev` | The same stack with hot reload, in the foreground |
| `make docker-down` | Stop it (`v=1` also drops the database volume) |
| `make docker-logs` | Follow the logs (`s=api` for one service) |
| `make docker-ps` | Container status |
| `make docker-migrate` | Run Alembic inside the stack |
| `make docker-test` | Run the backend suite inside the API image |
| `make docker-shell` | Shell into the API container (`s=web` for the interface) |
| `make docker-db` | `psql` into the database |
| `make docker-clean` | Remove containers, volumes and locally built images |

### Building the images on their own

```bash
docker build -t journeymesh-api ./backend
docker build -t journeymesh-web ./frontend                                  # nginx, /api proxied
docker build -t journeymesh-web ./frontend \
  --build-arg VITE_API_BASE_URL=https://api.example.com                     # calling a remote API
```

Ports are configurable through the root `.env` (`WEB_PORT`, `API_PORT`, `POSTGRES_PORT`).

---

## Vercel deployment

Deploy the two halves as two Vercel projects.

**Frontend** - root directory `frontend`, framework Vite, build `npm run build`, output
`dist`. `frontend/vercel.json` rewrites every non-API path to `index.html`, so
`/trip/:id`, `/history` and `/about` survive a refresh. Set `VITE_API_BASE_URL` to the
deployed API origin.

**Backend** - root directory `backend`. `backend/api/index.py` exposes the ASGI `app`
object and `backend/vercel.json` routes every request to it. Do not assume
`uvicorn app.main:app --reload` in production: on Vercel there is no long-running server,
so start-up work happens in the FastAPI lifespan on each cold start. Set `DATABASE_URL`,
`CORS_ORIGINS` (your frontend origin) and any provider keys as project environment
variables.

For any container host, use the images described under [Docker](#docker) instead.

---

## Render PostgreSQL setup

1. In the Render dashboard choose **New → PostgreSQL**, pick a name and region, and create
   the instance.
2. Open the database and copy the **External Database URL** (or the internal URL when the
   API runs on Render too).
3. Put it in `backend/.env` locally, or in the deployment's environment:
   `DATABASE_URL=<the URL you copied>`. Leave the value empty in the repository.
4. Run `alembic upgrade head` once against it.

Nothing else in the codebase mentions Render. The provider is defined entirely by
`DATABASE_URL`, so moving to Neon, Supabase, RDS or a local instance is a one-line change.
Treat a free-tier database as demo infrastructure, not production storage.

---

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Health reports `"database": "ephemeral_sqlite"` | `DATABASE_URL` is empty. Set it and run `alembic upgrade head`. |
| Health reports `"llm": "deterministic"` | No `GROQ_API_KEY`. Everything still works; agents use their deterministic paths. |
| Every price is labelled `ESTIMATE` | No provider keys are configured. This is expected, and honest. |
| `alembic upgrade head` raises "DATABASE_URL is not set" | Migrations need a real PostgreSQL URL; the fallback database has no migration history. |
| Log line: "MCP SDK is not installed" | `pip install mcp`, or leave the transports `disabled` to use the in-process adapters. |
| `429` from the API | The rate limiter. Raise `RATE_LIMIT_REQUESTS` or widen the window in development. |
| A request comes back with `"status": "blocked"` | A guardrail rejected it. `reason_code` says which; the message and guidance are safe to show. |
| `409 revision_limit_reached` | `MAX_REVISION_COUNT` reached. Approve the plan or start a new journey. |
| CORS errors in the browser | Add the frontend origin to `CORS_ORIGINS` and restart the API. |
| A refresh on `/trip/:id` returns 404 in production | The SPA rewrite is missing; check `frontend/vercel.json`. |
| Frontend cannot reach the API in development | Start the backend on port 8000, or set `VITE_API_BASE_URL`. |
| `docker compose up` fails with "port is already allocated" | Change `WEB_PORT`, `API_PORT` or `POSTGRES_PORT` in the root `.env`. |
| The interface returns 502 from `/api` | The API container is not healthy yet. `make docker-logs s=api`. |
| Old journeys are still there after a rebuild | The database volume survives `docker compose down`. Use `make docker-down v=1`. |
| `make docker-up` reports the migrate service failed | The database was not reachable. Check `make docker-logs s=db` and the `POSTGRES_*` values. |

---

## Author

**Pankaj Kumar Pramanik**
[pkp2.me2k9@gmail.com](mailto:pkp2.me2k9@gmail.com) · [pankajpramanik.com](https://pankajpramanik.com)

---

## License

Released under the MIT License. See [LICENSE](LICENSE).
