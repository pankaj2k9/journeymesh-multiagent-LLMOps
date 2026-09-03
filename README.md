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
- [Theming](#theming)
- [Documentation](#documentation)
- [Project structure](#project-structure)
- [Environment variables](#environment-variables)
- [Local setup](#local-setup)
- [PostgreSQL setup](#postgresql-setup)
- [API reference](#api-reference)
- [Testing](#testing)
- [Offline evaluation](#offline-evaluation)
- [Observability and LangSmith](#observability-and-langsmith)
- [Docker](#docker)
- [Production deployment](#production-deployment)
- [CI/CD](#cicd)
- [Environment variables in Render](#environment-variables-in-render)
- [Alternative: Vercel](#alternative-vercel)
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
| Observability | Structured logs, in-process tracing, optional LangSmith |
| Quality | Deterministic evaluation rules plus optional LLM-as-judge |
| Tests | pytest (218 tests), Vitest + React Testing Library (21 tests), an offline eval suite |
| Packaging | One multi-stage production image (React + FastAPI), Docker Compose |
| Deployment | GitHub Actions → Render (Docker) → Neon PostgreSQL |

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
- Optional LangSmith tracing of the graph, agents and MCP calls - never load-bearing
- One production image serving the React build and the API from a single origin
- GitHub Actions quality gate that must pass before Render is allowed to deploy
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
| "Plan a 5-day Dubai trip including flights and hotels." | `flight_agent`, `hotel_agent`, `itinerary_agent` |
| "Plan a Japan trip under 2 lakhs." | `flight_agent`, `hotel_agent`, `budget_agent`, `itinerary_agent` |
| "Plan a 5-day Singapore trip with flights, hotels and the weather." | `flight_agent`, `hotel_agent`, `weather_agent`, `itinerary_agent` |
| "Find a cheaper hotel but keep my flights." | `hotel_agent`, `budget_agent`, `itinerary_agent` |
| "Change my departure flight." | `flight_agent`, `budget_agent`, `itinerary_agent` |

Two rules widen a selection beyond what was named, and both exist because the result
would otherwise be misleading rather than merely incomplete: a stated **budget** pulls in
flights and hotels, because they are the two largest cost lines; a multi-night
**itinerary** pulls in hotels, because a day-by-day plan with nowhere to sleep is not a
plan. **Weather is opt-in** - a forecast is retrieved when the traveller asks about
conditions, packing or the season, and not otherwise, so a request for flights and hotels
does not spend a provider call on a section nobody wanted.

Intent matching is by **word**, not by substring: `"hotels"` contains `"hot"`, and an
earlier substring match meant every hotel request also looked like a weather question.

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

**Unlawful intent** (`unlawful_intent.py`) - a request can be perfectly on topic, free of
injection markers and still be something to refuse: *"plan a Dubai trip by hacking the
airport server"* is a travel request wrapped around a crime. Six rules cover unauthorised
access, forged travel documents, border evasion, smuggling, contraband transport and
payment fraud. Each names its subject, so the refusal reads *"Request involves hacking,
which is illegal and harmful."* rather than a generic wall. Every rule needs both an
action and an object and ambiguous verbs are absent, so *"avoid the customs queue"*,
*"life hack"* and *"hackathon"* are all left alone. It runs inside the input guard, before
the supervisor, so a refused request selects no agent, authorises no tool, contacts no
provider and creates no trip row.

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

## Observability and LangSmith

Two layers, deliberately separate.

**Local, always on.** Structured JSON logs carry `request_id`, `trip_id`,
`session_id`, `agent_name`, `tool_name`, `provider`, `latency_ms`,
success/failure, evaluation score, guardrail decision, `revision_count`,
`human_review_status` and token usage when the provider reports it. Every record
passes through the PII redactor before it is written. Spans are collected
in-process per request; counters and latency percentiles are on
`/api/v1/health?verbose=true`.

**LangSmith, when configured.** The AI-specific layer: the LangGraph run, each
agent, each model call and each MCP tool call arrive as one nested trace.

```text
JourneyMesh Trip Request
├── Input Guard
├── agent:supervisor
├── agent:flight_agent
│   └── tool:search_flights          (aviation MCP)
├── agent:hotel_agent
│   └── tool:search_hotels           (search MCP)
├── agent:weather_agent
│   └── tool:get_weather_forecast    (weather MCP)
├── agent:budget_agent
├── agent:itinerary_agent
├── Output Guard
├── Evaluation
└── Human Review
```

### One integration point

`app/observability/tracing.py` already opens a span around every agent, tool
call, model call and graph node. LangSmith is attached *there* - so no agent,
no tool and no guard contains tracing code of its own, and adding an agent
gets tracing for free.

```text
app/observability/
├── langsmith.py    configuration, metadata sanitisation, span mirroring
├── tracing.py      in-process spans -> LangSmith child runs
├── logging.py      structured JSON logs with PII redaction
└── metrics.py      counters and latency percentiles
```

### Revisions are legible

Each graph run is named after its phase and revision, so selective
re-execution can be read straight off the trace list:

| Run | Agents in the trace |
| --- | --- |
| `JourneyMesh Trip Request` | supervisor, flight, hotel, weather, budget, itinerary |
| `JourneyMesh Trip Planning - Revision 2` | supervisor, **hotel, budget, itinerary only** |
| `JourneyMesh Final Response` | final response agent |

Runs are tagged `journeymesh`, the phase, and `revision:N`, and every run
carries `trip_id`, so one journey's whole history - including which agents did
*not* re-run - can be filtered in one view.

### What is attached, and what never is

Metadata passes an allowlist before it leaves the process: `trip_id`,
`session_id`, `agent`, `selected_agents`, `change_scope`, `revision_number`,
`provider`, `tool`, `transport`, `response_language`, `human_review_status`,
`evaluation_score`, `budget_status`, `destination`, `origin`, `travelers`,
`source`, `latency_ms`, `success`.

Everything else is dropped - including the traveller's own words. API keys,
the database URL, passports, card numbers, emails, phone numbers, the raw
query and free-text change requests can never reach a trace, and allowlisted
values are still run through the PII redactor and truncated.

### It is never load-bearing

```text
JourneyMesh workflow
   ├── LangSmith available    -> trace
   └── LangSmith missing, misconfigured, timed out or disabled
                              -> carry on planning
```

Tracing starts only when `LANGSMITH_TRACING=true` *and* an API key is present.
Every call into the SDK is wrapped; a failure is counted, logged once and
swallowed. `tests/test_observability.py` asserts this directly: with the tracer
raising on every span, a journey still plans, evaluates and reaches review.

### It does not replace the evaluation module

`backend/app/evaluation/` keeps its job - deterministic checks, budget
arithmetic, schema validation, date consistency, tool correctness, itinerary
feasibility, groundedness and the quality score. LangSmith adds trace
inspection, datasets, experiment comparison and model-graded evaluation on top
of it. The two are complementary, and the deterministic layer is the one that
gates a journey.

### Configuration

| Variable | Meaning |
| --- | --- |
| `LANGSMITH_TRACING` | `true` turns tracing on. Off by default. |
| `LANGSMITH_API_KEY` | Required for tracing. Never appears in a log or a response. |
| `LANGSMITH_PROJECT` | Project name; `JourneyMesh` by default. |
| `LANGSMITH_ENDPOINT` | Override for self-hosted LangSmith. |

CI never talks to the real LangSmith: the suite runs with tracing off and
tests the disabled, misconfigured and failing paths explicitly.

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

## Theming

Two themes, light and dark, with **light as the default**. The dark palette is designed
rather than inverted: surfaces, text tones and every status colour have their own dark
values, and both palettes carry their measured contrast ratios as comments beside the
tokens.

- **Semantic tokens** - components say `bg-surface`, `text-muted`, `text-positive-fg`,
  never a literal colour. Each token resolves to a CSS custom property defined twice in
  `frontend/src/index.css`, once on `:root` and once under `.dark`, so a component is
  written once and themed centrally. Tailwind runs with `darkMode: 'class'`.
- **No flash** - a small script inlined into `index.html` runs before the first paint,
  reads the stored preference, toggles the `dark` class, sets `color-scheme` and updates
  the theme-colour meta tag. It is allowed by the content security policy through its
  exact SHA-256 hash, not `unsafe-inline` - the hash lives in both
  `backend/app/security/headers.py` and `frontend/nginx.conf`, so changing the script
  means regenerating it in both places.
- **Independent of language** - the theme is stored under `journeymesh_theme` and the
  language under `journeymesh_language`. Changing one never affects the other.
- **Where to change it** - the palettes live in `frontend/src/index.css` and the token
  names in `frontend/tailwind.config.js`. `ThemeToggle` is the navbar switch;
  `ThemeSelector` is the two-option radio group on the settings page.

---

## Documentation

A complete architecture guide is generated from this repository into
`docs/JourneyMesh_Architecture_Explanation_Guide.docx` - roughly 170 pages covering the
architecture, every agent, LangGraph, MCP and the tool guard, the guardrails, the
evaluation module, persistence, deployment, thirteen architecture decision records,
setup walkthroughs, sixty-four interview questions, an academic term-project chapter, a
glossary and a troubleshooting reference.

```bash
make docs          # regenerate it from the current source
```

It is generated by `scripts/generate_architecture_doc.py`, which reads dependency lists,
database tables, graph nodes, agent names, tool policies, API routes, environment
variables, translation keys and test counts out of the source at generation time - so the
document and the code cannot silently drift apart. Where something has not been measured,
the guide says "Not measured yet" rather than inventing a figure.

---

## Project structure

```text
journeymesh-multiagent-LLMOps/
├── backend/
│   ├── app/
│   │   ├── main.py                    FastAPI application factory
│   │   ├── api/          router.py, deps.py, static_site.py, routes/{health,travel,history,review}.py
│   │   ├── agents/       supervisor, flight, hotel, weather, budget, itinerary, final_response
│   │   ├── graph/        state.py, routing.py, travel_graph.py
│   │   ├── mcp/          client.py, config.py, registry.py, aviation.py, search.py, weather_server.py
│   │   ├── guardrails/   input_guard, output_guard, prompt_injection, pii_guard, tool_guard, policies
│   │   ├── evaluation/   evaluator, schemas, metrics, rules, quality_checks, runner
│   │   ├── security/     rate_limit, headers, request_security, secret_manager, audit
│   │   ├── observability/ langsmith, tracing, logging, metrics
│   │   ├── services/     travel, review, conversation, provider, llm
│   │   ├── db/           database.py, models.py, repositories/
│   │   ├── schemas/      travel, flight, hotel, weather, budget, itinerary, review, evaluation
│   │   └── core/         config.py, constants.py, exceptions.py, i18n.py
│   ├── alembic/          migration environment and versions
│   ├── tests/            218 tests
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
├── Dockerfile             The production image: React build + FastAPI
├── docker-compose.yml     db + the single application container
├── docker-compose.dev.yml Split hot-reload overlay
├── render.yaml            Render blueprint (autoDeploy off, no secrets)
├── .github/workflows/     ci.yml (quality gate) and deploy.yml (Render hook)
├── .env.example           Compose-stack settings
├── scripts/smoke.py       End-to-end check against a local instance
├── scripts/verify_deployment.py  Post-deploy verification
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

make backend-test                 # pytest, 218 tests
make frontend-test                # vitest, 21 tests
make eval                         # the offline evaluation suite
make build                        # production frontend build
```

The backend suite covers the health endpoint, trip planning, dynamic routing, each
specialist agent, the shared state, MCP calls and the tool guard, input and output
guardrails, prompt injection, PII redaction, evaluation, persistence, LangGraph
checkpointing, the human-in-the-loop pause/resume cycle, the LangSmith
integration (disabled, misconfigured and failing), the static SPA fallback and
the deployment configuration itself - including the critical regression:

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

The stack runs with one command, in the same shape as production: one container
serving React and the API, plus PostgreSQL.

```bash
cp .env.example .env        # optional; every value may stay empty
docker compose up --build   # or: make docker-up
```

- <http://localhost:8000> - the interface
- <http://localhost:8000/docs> - the API
- PostgreSQL on `localhost:5432`

`.env` at the repository root configures the compose stack only; running the
backend directly (`make dev`) still uses `backend/.env`.

### What the stack contains

| Service | Role |
| --- | --- |
| `db` | `postgres:16-alpine` - the local stand-in for Neon, on a named volume |
| `migrate` | Runs `alembic upgrade head` once, then exits |
| `app` | The production image: React build + FastAPI on one port |

Ordering is enforced rather than hoped for: `app` waits for `db` to pass its
`pg_isready` health check *and* for `migrate` to exit successfully. A failed
migration means the application never starts against a mismatched schema. Every
service has a health check and rotating logs, and the database lives on a named
volume rather than inside a container filesystem.

Switching to Neon locally is one line - point `DATABASE_URL` at the Neon
connection string in `.env` and the `db` service simply goes unused.

### The production image

`Dockerfile` at the repository root has three stages:

| Stage | Does |
| --- | --- |
| `frontend-builder` (node:22-alpine) | `npm ci`, then `npm run build` - which type-checks first, so a type error fails the image |
| `backend-builder` (python:3.11-slim) | Compiles the Python dependencies into `/opt/venv` |
| `application` (python:3.11-slim) | Copies the venv, the backend, and **only** `frontend/dist` |

The final image carries no `node_modules`, no frontend source, no build cache,
no test caches, no `.git` and no `.env` - the build context excludes them and
the last layer removes anything that slipped through. It runs as uid 10001,
carries only `libpq5` and `curl` beyond Python, and declares a health check on
`/api/v1/health`.

```bash
make image        # build journeymesh:local
make image-run    # build it and run it on :8000
```

### The entrypoint

`backend/docker-entrypoint.sh` is shared by both images:

| Command | Behaviour |
| --- | --- |
| `serve` (default) | Wait for the database, apply migrations when `RUN_MIGRATIONS=true`, then bind `0.0.0.0:$PORT` |
| `migrate` | Apply Alembic migrations and exit - non-zero if the database is unreachable |
| anything else | Executed verbatim, so `docker compose run --rm app pytest -q` works |

`PORT` comes from the environment with 8000 as the local fallback, which is what
lets Render assign the port without a code change. `RELOAD=true` swaps the
worker pool for `--reload`.

### Development with hot reload

```bash
make docker-dev
# docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

The overlay splits the halves apart again - uvicorn with `--reload` on
:8000, the Vite dev server on :5173, both with the source mounted - and parks
the single-container service behind a profile. `docker compose --profile single
up app` brings the production image back when you want to check it locally.

### Make targets

| Command | What it does |
| --- | --- |
| `make docker-up` | Build and start the production-shaped stack |
| `make docker-dev` | Split stack with hot reload |
| `make docker-down` | Stop it (`v=1` also drops the database volume) |
| `make docker-logs` | Follow the logs (`s=app` for one service) |
| `make docker-ps` | Container status |
| `make docker-migrate` | Run Alembic inside the stack |
| `make docker-test` | Run the backend suite inside the image |
| `make docker-shell` | Shell into the app container (`s=db` for PostgreSQL) |
| `make docker-db` | `psql` into the database |
| `make docker-clean` | Remove containers, volumes and locally built images |

`frontend/Dockerfile` (nginx) and `backend/Dockerfile` (API only) are still
there and are what the development overlay builds; the root `Dockerfile` is
what production runs.

---

## Production deployment

The demo deployment is one Docker container on Render, talking to Neon
PostgreSQL, traced by LangSmith, and deployed only by GitHub Actions after CI
has passed.

```text
GitHub repository
      │ push / pull request
      ▼
GitHub Actions ── CI ── lint · frontend tests · frontend build · backend tests
      │                 guardrail & security checks · evaluation · Docker build
      │
      │ main branch only, and only when every required job passed
      ▼
Render deploy hook
      ▼
Render free web service (Docker)
      │
      ├── React production build  ── served by FastAPI
      └── FastAPI  ── LangGraph · MCP · Guardrails · Evaluation · HITL
                │
                ▼
          Neon PostgreSQL
          trips · TravelState · checkpoints · review history
                │
                ▼
             LangSmith
          tracing · debugging · evaluation datasets
```

One image, one origin:

| Path | Served by |
| --- | --- |
| `/` | React |
| `/trip/:tripId`, `/history`, `/about`, `/settings` | React (SPA fallback, so a refresh works) |
| `/assets/*` | The hashed bundle, cached immutably |
| `/api/v1/*` | FastAPI |
| `/api/v1/health` | The platform health check |

### Step by step

**1. Create the Neon project.** In the Neon console create a project and a
database. Nothing about JourneyMesh is Neon-specific - Supabase, RDS or Cloud
SQL work identically.

**2. Copy the connection string.** Use the pooled connection string. It looks
like `postgresql://user:password@ep-something.region.aws.neon.tech/dbname?sslmode=require`.
JourneyMesh adds `sslmode=require` itself if it is missing, and normalises the
scheme for SQLAlchemy and for the LangGraph checkpointer.

**3. Create the Render web service.** New → Web Service → connect the
repository → **Docker** runtime → **Free** plan. Root directory is the
repository root; the `Dockerfile` there builds React and FastAPI into one
image.

**4. Set the health check path** to `/api/v1/health`. It is deliberately cheap:
no model call, no graph run, no MCP tool, no external travel API, no LangSmith
call and no database round trip.

**5. Configure the environment variables** in the Render dashboard - see
[the table below](#environment-variables-in-render). `DATABASE_URL` is the one
that matters; everything else has a working default.

**6. Turn Render's auto-deploy off.** Settings → Build & Deploy → Auto-Deploy →
**No**. GitHub Actions owns deployment; two systems deploying the same pushes
is the failure mode this avoids.

**7. Create the deploy hook.** Settings → Deploy Hook → copy the URL. Treat it
as a credential: anyone holding it can trigger a deployment.

**8. Add it to GitHub** under Settings → Secrets and variables → Actions → New
repository secret, named `RENDER_DEPLOY_HOOK_URL`. Optionally add a repository
*variable* `RENDER_SERVICE_URL` (e.g. `https://journeymesh.onrender.com`) so
the deploy workflow polls the service afterwards. The hook never appears in the
repository, and the workflow never echoes it.

**9. Push to main.** GitHub Actions runs CI. If every required job passes, the
deploy workflow fires the hook; if anything fails, nothing is deployed.

**10. Render builds and starts the container.** The entrypoint waits for the
database, runs `alembic upgrade head`, and only then starts uvicorn on
`0.0.0.0:$PORT`. A failed migration stops the deployment rather than serving
against an incompatible schema.

**11. Verify.**

```bash
make verify-deployment url=https://journeymesh.onrender.com
# add plan=1 to also plan, revise and approve a real journey
```

The script checks the health endpoint, that `database` reports `postgresql`
rather than the ephemeral fallback, that `/` and the nested routes return the
React shell, that `/api/v1/*` still reaches FastAPI, that an unknown API path is
a 404, that the guardrails are live, and that no credential leaks through the
health payload. With `plan=1` it also confirms selective re-execution end to
end against the deployed instance.

**12. Check LangSmith.** Open the `JourneyMesh` project. A planned journey
appears as `JourneyMesh Trip Request` with the supervisor, the specialist
agents and their MCP calls nested underneath.

### Notes on the free tier

A free Render service sleeps when idle, so the first request after a pause is
slow - the health check will wake it. Neon's free tier also suspends idle
compute; the pooled connection with `pool_pre_ping` handles the reconnect. Both
are fine for a portfolio deployment and neither is production capacity.

The container filesystem is ephemeral: **all** durable state lives in Neon, so a
restart or a redeploy loses nothing. The one thing to know is that a journey
planned while `DATABASE_URL` is unset lives in the in-memory fallback and does
not survive a restart - which is exactly what the health endpoint reports, and
what `verify-deployment` fails on.

### Migrations

Migrations are applied by the container entrypoint before the server starts:

```bash
alembic upgrade head        # what the entrypoint runs
```

If it fails, the container exits and the deployment stops. To run them by hand
against Neon:

```bash
cd backend
DATABASE_URL="postgresql://...neon.tech/db?sslmode=require" alembic upgrade head
```

Only one Render instance runs on the free plan, so migrations cannot race. If
you scale out later, set `RUN_MIGRATIONS=false` on the web service and run the
migration as a separate one-off job before the rollout.

---

## CI/CD

Two workflows, with one controlled path to production.

```text
Pull request                          Merge to main
     │                                     │
     ▼                                     ▼
  CI only                              CI (quality gate)
     │                          ┌──────────┴──────────┐
     ▼                       Frontend               Backend
 no deployment            test · build         test · security · eval
                                 └──────────┬──────────┘
                                            ▼
                                      Docker build
                                     (runs the image,
                                      checks / and /api)
                                            ▼
                                          PASS
                                            ▼
                                   Render deploy hook
                                            ▼
                                     Render Docker
```

### `.github/workflows/ci.yml`

| Job | What it does | Required |
| --- | --- | --- |
| `frontend` | Install, TypeScript check, Vitest, production build, artifact upload | yes |
| `backend` | Install, ruff, import check, pytest, guardrail/security suites, evaluation suites, observability suite, offline eval, Alembic render | yes |
| `security` | No `.env` tracked, no deploy hook or key-shaped credential committed, no connection string with a password, `pip-audit` on backend dependencies | yes |
| `security` (informational) | `npm audit`, hadolint - reported, never blocking | no |
| `docker` | Builds the production image, runs it, and asserts health, `/`, nested routes, `/api`, and that no build leftovers are in the image | yes |
| `quality-gate` | Fails unless all four succeeded | yes |

The backend job runs with **no credentials at all** - that is the point: every
provider has an offline path, and LangSmith is off.

### `.github/workflows/deploy.yml`

Triggered by CI *completing on main*, and gated twice: the run must be on
`main` and CI must have concluded `success`. A pull request cannot reach it. It
checks the secret is present, POSTs the hook without ever echoing the URL,
optionally polls `/api/v1/health` until the service is healthy, and writes a
deployment summary.

### Secrets

| Secret | Where | Why |
| --- | --- | --- |
| `RENDER_DEPLOY_HOOK_URL` | GitHub Actions secret | The only secret CI needs |
| `RENDER_SERVICE_URL` | GitHub Actions *variable* (optional) | Post-deploy health polling |

Runtime secrets - `DATABASE_URL`, `GROQ_API_KEY`, `TAVILY_API_KEY`,
`AVIATIONSTACK_API_KEY`, `OPENWEATHER_API_KEY`, `LANGSMITH_API_KEY` - live in
**Render**, not in GitHub. CI does not need them, so it does not have them.

`render.yaml` is checked in as a reviewable description of the service. It sets
`autoDeploy: false` and marks every credential `sync: false`, meaning "set this
in the dashboard" - no secret is stored in the repository.

---

## Environment variables in Render

Set these on the web service. Only `DATABASE_URL` really matters; everything
else has a working default, and any credential left empty simply puts that
provider into its offline mode.

| Variable | Suggested value | Notes |
| --- | --- | --- |
| `DATABASE_URL` | *(Neon connection string)* | The only database configuration there is |
| `DB_REQUIRE_SSL` | `true` | TLS is added automatically for a remote host |
| `APP_ENV` | `production` | Disables `/docs` and enables HSTS |
| `PORT` | *(set by Render)* | Do not set it yourself |
| `WEB_CONCURRENCY` | `2` | Uvicorn workers; the free plan is small |
| `GROQ_API_KEY` | *(optional)* | Empty means deterministic agents |
| `GROQ_MODEL` | *(optional)* | Defaults to a Llama 3.3 70B model |
| `TAVILY_API_KEY` | *(optional)* | Hotel and destination research |
| `AVIATIONSTACK_API_KEY` | *(optional)* | Live flight schedules |
| `OPENWEATHER_API_KEY` | *(optional)* | Live weather |
| `MCP_SEARCH_TRANSPORT` / `_URL` | `disabled` | `stdio`, `streamable_http` or `disabled` |
| `MCP_AVIATION_TRANSPORT` / `_URL` | `disabled` | |
| `MCP_WEATHER_TRANSPORT` / `_URL` | `disabled` | |
| `LANGSMITH_TRACING` | `true` | Needs a key to actually trace |
| `LANGSMITH_API_KEY` | *(optional)* | Never logged or returned |
| `LANGSMITH_PROJECT` | `JourneyMesh` | |
| `LANGSMITH_ENDPOINT` | *(optional)* | For self-hosted LangSmith |
| `GUARDRAILS_ENABLED` | `true` | |
| `PROMPT_INJECTION_CHECK_ENABLED` | `true` | |
| `PII_GUARD_ENABLED` | `true` | |
| `TOOL_GUARD_ENABLED` | `true` | |
| `EVALUATION_ENABLED` | `true` | |
| `EVALUATION_MODE` | `deterministic` | `hybrid` and `llm_judge` need a model |
| `MAX_REVISION_COUNT` | `3` | The human-in-the-loop revision limit |
| `CORS_ORIGINS` | *(unset)* | Only needed if the interface is hosted separately |
| `RATE_LIMIT_ENABLED` | `true` | |
| `RATE_LIMIT_REQUESTS` | `60` | Per window, per client |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | |
| `MAX_REQUEST_SIZE` | `65536` | Bytes |
| `ENABLE_MOCK_DATA` | `true` | Offline provider fallbacks |
| `SERVE_FRONTEND` | `true` | Set by the image already |

`DATABASE_URL` is a backend variable and never reaches the browser: the React
bundle only ever sees `VITE_*` values, and the only one that exists is the API
base URL, which is empty because the API is same-origin.

---

## Alternative: Vercel

The single Render image is the supported deployment. The repository also keeps
the split Vercel configuration, if you would rather host the two halves apart.

**Frontend** - root directory `frontend`, framework Vite, build `npm run build`,
output `dist`. `frontend/vercel.json` rewrites non-API paths to `index.html`.
Set `VITE_API_BASE_URL` to the API origin.

**Backend** - root directory `backend`. `backend/api/index.py` exposes the ASGI
`app` and `backend/vercel.json` routes everything to it. There is no
long-running server there, so start-up work happens in the FastAPI lifespan on
each cold start. Set `DATABASE_URL` and `CORS_ORIGINS` (the frontend origin).

Split hosting means two origins, so `CORS_ORIGINS` matters - unlike the single
container, where it does not.

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
| The deployed health endpoint reports `ephemeral_sqlite` | `DATABASE_URL` is not set on the Render service. Journeys will not survive a restart until it is. |
| A deployed nested route 404s on refresh | The image was built without the React build. Check the `frontend-builder` stage succeeded. |
| Render deploys on every push as well as through Actions | Render's auto-deploy is still on. Settings → Build & Deploy → Auto-Deploy → No. |
| The deploy workflow fails immediately | `RENDER_DEPLOY_HOOK_URL` is missing from the repository secrets. |
| No traces appear in LangSmith | Tracing needs `LANGSMITH_TRACING=true` *and* a key. `/api/v1/health?verbose=true` reports which one is missing. |
| The first request after a while is very slow | The free Render service and Neon compute both sleep when idle. |

---

## Author

**Pankaj Kumar Pramanik**
[pkp2.me2k9@gmail.com](mailto:pkp2.me2k9@gmail.com) · [pankajpramanik.com](https://pankajpramanik.com)

---

## License

Released under the MIT License. See [LICENSE](LICENSE).
