"""Front matter, executive summary, problem, requirements and architecture."""

from __future__ import annotations

from docgen.builder import Guide
from docgen.repo import FACTS


def write(g: Guide) -> None:
    _how_to_use(g)
    _executive_summary(g)
    _problem(g)
    _objectives(g)
    _functional(g)
    _non_functional(g)
    _architecture(g)
    _request_lifecycle(g)
    _revision_lifecycle(g)


# ---------------------------------------------------------------------------
def _how_to_use(g: Guide) -> None:
    g.h1("How to Use This Guide")
    g.p(
        "This document explains the JourneyMesh system in enough depth to work on it, "
        "deploy it, debug it, defend it in a technical interview and submit it as an "
        "academic project. It is written for a developer who is comfortable with Python, "
        "JavaScript, React, HTTP APIs and relational databases, but who has not "
        "necessarily worked with agentic AI, LangGraph, the Model Context Protocol, "
        "LLM evaluation or AI guardrails. Those topics are introduced from first "
        "principles before the JourneyMesh implementation of them is described."
    )
    g.p(
        "Every claim here was taken from the repository itself. Dependency lists, "
        "database tables, graph nodes, tool policies, API routes, environment variables "
        "and test counts are read out of the source at generation time rather than "
        "written from memory, so the document and the code cannot silently drift apart."
    )

    g.h2("Reading paths")
    g.table(
        ["If you are", "Read", "Skip"],
        [
            ["New to the codebase",
             "Chapters 1-6, then the source-code walkthrough",
             "The interview and academic chapters"],
            ["Preparing for an interview",
             "The executive summary, the architecture chapter, then the interview "
             "preparation and quick revision chapters",
             "The setup walkthroughs"],
            ["Deploying it",
             "Docker, Compose, Railway, CI/CD and the troubleshooting chapter",
             "The agent internals"],
            ["Writing the term report",
             "The academic chapter, plus the architecture and evaluation chapters",
             "The command cheat sheet"],
            ["Extending an agent",
             "TravelState, the supervisor, the specialist agents and the evaluation "
             "chapters",
             "Deployment"],
        ],
        caption="Suggested reading paths through this guide.",
        widths=[1.2, 2.6, 1.6],
    )

    g.h2("Conventions")
    g.bullets([
        "Hard ideas are given twice: a technical definition, then the same idea in plain "
        "words. Both matter - the first is what you write in a design document, the "
        "second is what you say out loud in an interview.",
        "Every major chapter ends with a 'What you should understand' checkpoint.",
        "Code samples are taken from the repository. Where a sample is shortened, the "
        "omission is marked and the file path is given so the original can be read.",
        "Diagrams are drawn in text so they survive copying into any editor.",
        "Where something has not been measured, this guide says so rather than "
        "inventing a number.",
    ])

    g.callout(
        "important",
        "This guide describes the state of the repository at generation time. Deployment "
        "status in particular is stated precisely: 'configured', 'tested locally', "
        "'verified in CI' and 'deployed' mean different things and are not used "
        "interchangeably.",
    )


# ---------------------------------------------------------------------------
def _executive_summary(g: Guide) -> None:
    g.h1("Executive Summary", page_break=True)

    g.h2("What JourneyMesh is")
    g.p(
        "JourneyMesh is a multilingual, agentic travel-planning system. A traveller "
        "describes a trip in ordinary language - \"plan a relaxing 5-day family trip "
        "from Dhaka to Singapore under $2,000\" - and JourneyMesh returns a reviewable "
        "plan: candidate routes, a shortlist of places to stay, a forecast for the "
        "travel window, a cost breakdown that separates confirmed prices from "
        "estimates, and a day-by-day itinerary. Nothing is final until a human approves "
        "it, and asking for one change does not regenerate the parts that were already "
        "acceptable."
    )
    g.p(
        "It is deliberately not a chatbot with a travel prompt. It is a coordinated "
        "system in which a supervisor decides which specialists a request actually "
        "needs, each specialist works on its own slice of a shared state, every "
        "external call is authorised before it leaves the process, every draft is "
        "measured before a person sees it, and the whole run is persisted so it can be "
        "paused and resumed."
    )

    g.h2("The problem it solves")
    g.p(
        "Planning a trip means reconciling several independent information domains - "
        "flights, accommodation, weather, money, activities and time - each with its "
        "own source of truth, and each constrained by the others. A cheaper hotel "
        "changes the budget, which changes what activities fit, which changes the "
        "shape of each day. Doing this by hand means many browser tabs and a "
        "spreadsheet. Doing it with a single language model means fluent answers that "
        "may be confidently wrong about prices, schedules and availability."
    )

    g.h2("How it works, in one paragraph")
    g.p(
        "A React interface sends a structured request to a FastAPI service. The request "
        "passes security middleware and input guardrails. A supervisor agent reads it "
        "and decides which of the five specialist agents are required - a weather "
        "question runs one, a full journey runs all five. The selected agents run in "
        "dependency order, writing into a shared TravelState. Any external call they "
        "need goes through an MCP client, and before that through a tool guard that "
        "denies by default. The assembled result is checked by output guardrails, "
        "scored by a ten-dimension evaluation module, and then the workflow stops and "
        "waits for a human. Approving it runs a final response agent that renders the "
        "journey in English, Bengali or Hindi. Asking for a change sends the traveller's "
        "words back to the supervisor, which re-runs only the affected agents. "
        "Everything is persisted in PostgreSQL, and the whole execution can be traced "
        "in LangSmith."
    )

    g.diagram(
        """
        Traveller
            |
            v
      React interface  (planner, trip view, review controls, history)
            |
            v
      FastAPI  /api/v1        <-- security middleware, input guardrails
            |
            v
      Supervisor agent        <-- decides WHICH specialists are needed
            |
    +-------+-------+---------+---------+----------+
    v       v       v         v         v
  Flight  Hotel  Weather   Budget   Itinerary      (specialist agents)
    |       |       |         |         |
    +-------+---+---+---------+---------+
                v
          MCP tool guard      <-- may this agent call this tool?
                v
          MCP client -> aviation / search / weather servers
                v
          Shared TravelState
                v
          Output guard -> Evaluation -> HUMAN REVIEW
                                          |        |
                                     approve    request changes
                                          |        |
                                          |        v
                                          |   supervisor re-plans
                                          |   only affected agents
                                          v
                                Final response agent
                                          v
                        PostgreSQL (container / Railway service)
        """,
        "JourneyMesh at a glance: dynamic routing, guarded tools, human review.",
    )

    g.h2("Why each major decision was made")
    g.table(
        ["Decision", "Why"],
        [
            ["Agentic AI rather than one prompt",
             "The task decomposes naturally into domains with different data sources, "
             "different failure modes and different trust levels. A single prompt cannot "
             "call an airline API, and a single model cannot be held to account for which "
             "part of its answer was fabricated."],
            ["Multiple specialist agents",
             "Each agent has a small, testable responsibility and its own slice of state. "
             "A bug in hotel ranking cannot corrupt the forecast. Each can be evaluated "
             "and re-run independently."],
            ["A supervisor agent",
             "Running every agent for every request wastes latency, provider quota and "
             "model spend. The supervisor makes the set of agents a function of the "
             "request - and, on a revision, a function of what the traveller asked to "
             "change."],
            ["LangGraph",
             "The workflow is a stateful graph with a conditional entry point and a "
             "durable pause in the middle. LangGraph provides typed state, conditional "
             "edges and checkpointing, which is exactly the shape of the problem."],
            ["Model Context Protocol",
             "It standardises how the system reaches external tools, so providers can be "
             "swapped or moved out of process without touching agent logic."],
            ["Human-in-the-loop",
             "Travel decisions involve money and time. The system proposes; the person "
             "decides. This also makes the product honest about model uncertainty."],
            ["Evaluation as its own module",
             "LLM output is probabilistic, so unit tests are not enough. Dates, "
             "arithmetic, schemas and provenance are checked deterministically before a "
             "person is shown anything."],
            ["Guardrails as their own module",
             "Prompt injection, PII and tool authorisation are security concerns, not "
             "prompt-engineering concerns. They are enforced in application code that a "
             "model cannot talk its way past."],
            ["PostgreSQL",
             "Trips are relational; agent output is document-shaped. PostgreSQL with "
             "JSONB handles both, transactionally, and is also where LangGraph's "
             "checkpoints live."],
            ["Docker",
             "Reproducible images, so the thing that runs in production is the thing "
             "that was built and probed in CI - and so nobody has to install a "
             "database, a Python version or a Node version to work on the project."],
            ["Docker Compose",
             "The local orchestrator. One command starts the interface, the API and "
             "PostgreSQL together, in the same three-service shape production runs, "
             "with the database persisted in the repository."],
            ["Railway",
             "The production platform. Each component becomes its own service with "
             "its own build, rollout and variables; PostgreSQL is a managed service "
             "reached over private networking through a reference variable, so no "
             "credential is ever written down."],
            ["GitHub Actions",
             "The quality gate. Nothing reaches production without passing tests, "
             "guardrail checks, evaluation and a Docker build that is actually started "
             "and probed."],
            ["LangSmith",
             "Agentic systems are hard to debug from logs alone. LangSmith shows the "
             "nested run - which agents fired, which tools they called, how long each "
             "took - and makes selective re-execution visible per revision."],
        ],
        caption="The reasoning behind each principal technology choice.",
        widths=[1.2, 3.4],
    )

    g.h2("Scale of the implementation")
    g.table(
        ["Area", "Measure"],
        [
            ["Backend Python modules (app/)", str(FACTS.backend_files)],
            ["Frontend TypeScript modules (src/)", str(FACTS.frontend_files)],
            ["Backend tests", f"{FACTS.backend_test_count} across {len(FACTS.backend_test_files)} files"],
            ["Frontend test files", str(len(FACTS.frontend_test_files))],
            ["Offline evaluation cases", str(len(FACTS.eval_cases))],
            ["Database tables", ", ".join(FACTS.tables)],
            ["Specialist and supervisory agents", str(len(FACTS.agents))],
            ["LangGraph nodes", str(len(FACTS.graph_nodes))],
            ["Tool policies", str(len(FACTS.tools))],
            ["Interface translation keys per language", str(FACTS.locale_keys)],
            ["Public API endpoints", str(len(FACTS.api_routes))],
        ],
        caption="Repository inventory, read from the source at generation time.",
        widths=[2.2, 2.4],
    )

    g.understand([
        "What JourneyMesh does and what it deliberately is not.",
        "Why the travel-planning problem suits a multi-agent design.",
        "The role of the supervisor, the specialists, the guards and the human.",
        "Why each principal technology was chosen.",
    ])


# ---------------------------------------------------------------------------
def _problem(g: Guide) -> None:
    g.h1("Problem Statement", page_break=True)

    g.h2("Travel planning is a multi-domain constraint problem")
    g.p(
        "A single trip request touches at least eight domains at once, and they are not "
        "independent."
    )
    g.table(
        ["Domain", "Question it answers", "Depends on"],
        [
            ["Flights", "How do I get there and what does it cost?", "Origin, destination, dates, party size"],
            ["Accommodation", "Where do I stay?", "Destination, nights, budget, party size, style"],
            ["Weather", "What will it be like?", "Destination, travel window"],
            ["Budget", "Does this fit the money?", "Flights, hotels, activities, party size, duration"],
            ["Activities", "What is worth doing?", "Interests, weather, budget, opening times"],
            ["Scheduling", "What happens on which day?", "Everything above, plus travel time and rest"],
            ["Preferences", "What does this traveller like?", "Stated interests and travel style"],
            ["Constraints", "What must be respected?", "Dates, accessibility, children, dietary needs"],
        ],
        caption="The domains a travel plan has to reconcile, and their dependencies.",
        widths=[1.0, 2.2, 1.8],
    )

    g.h2("Why a fixed pipeline struggles")
    g.p(
        "The obvious design is a fixed sequence: search flights, then hotels, then "
        "weather, then compute a budget, then write an itinerary. It works until the "
        "requests stop being uniform."
    )
    g.bullets([
        "\"What will the weather be like in Dubai next week?\" runs four unnecessary "
        "agents, each with its own latency and provider quota.",
        "\"Find a cheaper hotel but keep my flights\" re-runs the entire pipeline, "
        "discarding results the traveller explicitly said were fine - and may return "
        "different flights than the ones they approved.",
        "A provider outage in step one blocks the steps that did not need it.",
        "Every new capability makes the single sequence longer and more brittle.",
    ])

    g.h2("Why a language model alone is not enough")
    g.table(
        ["Limitation", "Consequence for travel planning", "What JourneyMesh does"],
        [
            ["No current data",
             "Training data cannot know today's fares, availability or forecast.",
             "External providers reached through MCP; every value carries a provenance label."],
            ["Hallucination",
             "A model will happily produce a plausible flight number and a confident price.",
             "Agents never invent a fare or a schedule; anything unconfirmed is marked ESTIMATE, "
             "and the evaluation module fails a journey whose priced items are unlabelled."],
            ["No inherent access to services",
             "A model cannot call an airline API by itself.",
             "An MCP client with an authorisation guard performs the calls."],
            ["Inconsistent structure",
             "Free text is hard to render, diff or re-run selectively.",
             "Every agent returns a Pydantic-validated structure; the interface renders sections, not prose."],
            ["No memory of a decision",
             "A follow-up request restarts from nothing.",
             "TravelState plus LangGraph checkpoints persist the run across requests and days."],
            ["No accountability",
             "There is no way to ask which part came from where.",
             "Provider status, provenance labels, audit events and traces answer that."],
        ],
        caption="Why the system is more than a prompt around a model.",
        widths=[1.1, 1.9, 2.2],
    )

    g.h2("The JourneyMesh answer")
    g.diagram(
        """
        LLM reasoning        (what to do, how to phrase it)
              +
        Supervisor           (which specialists are needed)
              +
        Specialist agents    (one domain each, own slice of state)
              +
        MCP                  (standardised access to external tools)
              +
        Tool guard           (may this call happen at all?)
              +
        Shared TravelState   (how agents cooperate without coupling)
              +
        Guardrails           (what may enter and leave a model)
              +
        Evaluation           (is this good enough to show a person?)
              +
        Human review         (the person decides, not the model)
              +
        Persistence          (nothing is lost between decisions)
        """,
        "The composition that replaces a single prompt.",
    )

    g.understand([
        "Why travel planning is a multi-domain constraint problem.",
        "Three concrete ways a fixed pipeline fails on real requests.",
        "The six limitations of a bare language model, and JourneyMesh's answer to each.",
    ])


# ---------------------------------------------------------------------------
def _objectives(g: Guide) -> None:
    g.h1("Objectives and Scope", page_break=True)

    g.h2("Primary objective")
    g.callout(
        "note",
        "Build a multilingual agentic travel-planning system that dynamically "
        "coordinates specialist agents and external tools while maintaining security, "
        "observability, evaluation, persistence and human control.",
    )

    g.h2("Secondary objectives")
    g.table(
        ["Objective", "Where it is realised"],
        [
            ["Dynamic agent selection", "`app/agents/supervisor.py`"],
            ["Flight research", "`app/agents/flight_agent.py`, `app/mcp/aviation.py`"],
            ["Accommodation research", "`app/agents/hotel_agent.py`, `app/mcp/search.py`"],
            ["Weather integration", "`app/agents/weather_agent.py`, `app/mcp/weather_server.py`"],
            ["Budget analysis", "`app/agents/budget_agent.py`"],
            ["Itinerary generation", "`app/agents/itinerary_agent.py`"],
            ["MCP integration", "`app/mcp/` (client, config, registry, three servers)"],
            ["Human-in-the-loop", "`app/graph/travel_graph.py`, `app/services/review_service.py`"],
            ["Request-changes loop", "`SupervisorAgent.analyse_change`, `POST /trips/{id}/request-changes`"],
            ["Persistent state", "`app/db/`, LangGraph PostgreSQL checkpoints"],
            ["Multilingual interface and output", "`frontend/src/locales/`, `app/core/i18n.py`"],
            ["Light and dark themes", "`frontend/src/theme/`"],
            ["Evaluation", "`app/evaluation/` and `backend/evals/`"],
            ["Security", "`app/security/`, `app/guardrails/`"],
            ["Observability", "`app/observability/` including LangSmith"],
            ["CI/CD", "`.github/workflows/ci.yml`, `.github/workflows/deploy.yml`"],
            ["Deployment", "`docker-compose.yml` locally; `railway.json` per service "
             "in production; PostgreSQL via `DATABASE_URL` in both"],
        ],
        caption="Secondary objectives mapped to the code that implements them.",
        widths=[1.6, 3.0],
    )

    g.h2("Out of scope")
    g.p(
        "Stating what a system does not do is as useful as stating what it does. "
        "JourneyMesh does not book anything, take payment, hold user accounts or claim "
        "real-time availability. The tool policy table declares booking, payment and "
        "cancellation operations so the boundary is explicit in code, but they are "
        "disabled and require confirmation. See the future-work chapter."
    )


# ---------------------------------------------------------------------------
def _functional(g: Guide) -> None:
    g.h1("Functional Requirements", page_break=True)
    g.p(
        "Each requirement below is implemented and covered by at least one automated "
        "test. The verification column names the mechanism rather than claiming success "
        "in the abstract."
    )

    g.table(
        ["#", "Requirement", "Implementation", "Verified by"],
        [
            ["F1", "Plan a journey from a natural-language request",
             "`POST /api/v1/trips/plan`", "`test_api_trips.py`"],
            ["F2", "Accept origin, destination, dates, travellers, budget, currency",
             "`TripPlanRequest`", "`test_guardrails_input.py`"],
            ["F3", "Accept travel style, hotel preference and interests",
             "`TripPlanRequest` enums", "`test_guardrails_input.py`"],
            ["F4", "Research flights and resolve airports",
             "Flight agent + aviation MCP", "`test_agents.py`"],
            ["F5", "Research accommodation against budget and party size",
             "Hotel agent + search MCP", "`test_agents.py`"],
            ["F6", "Retrieve current conditions and a forecast",
             "Weather agent + weather MCP", "`test_agents.py`"],
            ["F7", "Produce a cost breakdown with provenance",
             "Budget agent", "`test_agents.py`, `test_evaluation.py`"],
            ["F8", "Generate a realistic day-by-day itinerary",
             "Itinerary agent", "`test_agents.py`"],
            ["F9", "Produce travel tips in the chosen language",
             "Final response agent + `app/core/i18n.py`", "`test_agents.py`, `test_i18n.py`"],
            ["F10", "Persist a journey and its results",
             "`TravelService`, `app/db/`", "`test_persistence.py`"],
            ["F11", "List and open previous journeys",
             "`GET /trips`, `GET /trips/{id}`", "`test_api_trips.py`"],
            ["F12", "Delete a journey and everything attached to it",
             "`DELETE /trips/{id}`", "`test_persistence.py`"],
            ["F13", "Pause for human review before anything is final",
             "`human_review` graph node", "`test_graph_workflow.py`"],
            ["F14", "Approve a draft and produce the final journey",
             "`POST /trips/{id}/approve`", "`test_api_trips.py`"],
            ["F15", "Request changes in free text",
             "`POST /trips/{id}/request-changes`", "`test_api_trips.py`"],
            ["F16", "Re-run only the agents a change affects",
             "`SupervisorAgent.analyse_change`", "`test_graph_workflow.py`, `test_supervisor.py`"],
            ["F17", "Preserve untouched results across a revision",
             "Per-agent state slices", "`test_graph_workflow.py`"],
            ["F18", "Track revisions and enforce a limit",
             "`revision_count`, `MAX_REVISION_COUNT`", "`test_graph_workflow.py`"],
            ["F19", "Support English, Bengali and Hindi in the interface",
             "i18next catalogues", "`i18n.test.ts`"],
            ["F20", "Produce the journey itself in the chosen language",
             "Phrase codes rendered by the final agent", "`test_agents.py`, `test_i18n.py`"],
            ["F21", "Support light and dark themes",
             "`frontend/src/theme/`", "`theme.test.tsx`, `theme-coverage.test.ts`"],
            ["F22", "Report provider failures honestly instead of failing the request",
             "`ProviderStatus`, per-agent fallbacks", "`test_agents.py`, `test_mcp.py`"],
            ["F23", "Reject unsafe or irrelevant requests with a usable message",
             "Input guardrails", "`test_guardrails_input.py`, `test_prompt_injection.py`"],
        ],
        caption="Functional requirements, their implementation and their tests.",
        widths=[0.3, 2.0, 1.6, 1.4],
        size=8.5,
    )


# ---------------------------------------------------------------------------
def _non_functional(g: Guide) -> None:
    g.h1("Non-Functional Requirements", page_break=True)

    g.table(
        ["Quality", "How JourneyMesh addresses it"],
        [
            ["Security",
             "Input and output guardrails, prompt-injection screening, PII redaction, "
             "deny-by-default tool authorisation, rate limiting, request-size limits, "
             "security headers, safe error envelopes, secrets read through one module, "
             "and a CI job that fails if a credential or an environment file is committed."],
            ["Reliability",
             "A provider failure is data, not an exception: the tool call returns a "
             "status, the agent records it and the journey continues with a partial "
             "result. An agent that raises is caught, recorded on the state and skipped."],
            ["Maintainability",
             "Responsibilities are separated by module boundary - agents decide, the "
             "supervisor routes, MCP transports, the guard authorises, evaluation "
             "measures. Agents communicate only through TravelState, so none of them "
             "imports another."],
            ["Extensibility",
             "Adding an agent means adding one module, one state key, one entry in the "
             "execution order and its dependents, and a tool policy if it needs a tool. "
             "Nothing else changes."],
            ["Observability",
             "Structured JSON logs with request, trip and session identifiers; "
             "in-process spans; counters and latency percentiles on the health endpoint; "
             "an audit trail; and optional LangSmith tracing of the whole nested run."],
            ["Performance",
             "Dynamic routing avoids unnecessary agents; selective re-execution avoids "
             "unnecessary re-work; the database uses a bounded pre-pinged pool; provider "
             "calls have timeouts; the frontend caches server state with TanStack Query. "
             "No latency target has been measured - see the results chapter."],
            ["Testability",
             f"{FACTS.backend_test_count} backend tests and {len(FACTS.frontend_test_files)} "
             "frontend test files run with no credentials at all, because every provider "
             "has a deterministic offline path."],
            ["Scalability",
             "Stateless application containers with all durable state in PostgreSQL, so "
             "horizontal scaling is a deployment change rather than a rewrite. The "
             "current rate limiter is per-process and would need a shared store first."],
            ["Availability",
             "Health checks on the container and the platform; the API answers even when "
             "the database is unconfigured, reporting the degraded mode honestly."],
            ["Privacy",
             "PII is redacted before anything reaches a model, an MCP server, a log line, "
             "an audit record or a trace. The system never asks for passport or payment "
             "details and says so when a traveller volunteers them."],
            ["Accessibility",
             "Semantic landmarks, labelled form fields, visible focus rings, a skip link, "
             "accessible names on icon buttons, status conveyed by text and icon as well "
             "as colour, and contrast chosen to clear WCAG AA in both themes."],
            ["Internationalisation",
             f"{FACTS.locale_keys} interface keys per language in English, Bengali and "
             "Hindi, with a parity test; and server-side phrase codes so the generated "
             "journey is translated without depending on a model."],
            ["Fault tolerance",
             "Degrade, do not fail: missing credentials fall back to labelled offline "
             "data, an unreachable MCP server falls back to the in-process adapter, and "
             "an unavailable tracer is logged once and ignored."],
            ["Cost awareness",
             "Fewer agents per request, fewer agents per revision, deterministic "
             "evaluation instead of model-graded evaluation by default, and per-tool call "
             "budgets enforced by the guard."],
        ],
        caption="Non-functional requirements and the mechanisms that satisfy them.",
        widths=[0.9, 3.7],
    )

    g.understand([
        "The fourteen quality attributes JourneyMesh is designed against.",
        "Which mechanism in the code delivers each one.",
        "Which qualities are designed for but not yet measured.",
    ])


# ---------------------------------------------------------------------------
def _architecture(g: Guide) -> None:
    g.h1("System Architecture", page_break=True)

    g.h2("The five layers")
    g.p(
        "JourneyMesh is arranged in five layers. Each one is allowed to depend on the "
        "layer below it and never on the layer above. That single rule is what keeps "
        "the system testable: the agent layer can be exercised without an HTTP server, "
        "the orchestration layer without a database, and the tool layer without a "
        "network."
    )

    g.table(
        ["Layer", "What lives there", "Directory", "Depends on"],
        [
            ["Presentation",
             "React interface, routing, translation, theming, data fetching",
             "`frontend/src`",
             "The HTTP API only"],
            ["Interface",
             "FastAPI routes, request and response schemas, security middleware, "
             "static-site mounting",
             "`backend/app/api`, `backend/app/schemas`, `backend/app/security`",
             "Services"],
            ["Orchestration",
             "The LangGraph workflow, shared state, entry routing, the supervisor",
             "`backend/app/graph`, `backend/app/agents/supervisor.py`",
             "Agents, evaluation, guardrails"],
            ["Domain",
             "Specialist agents, evaluation, guardrails, services, repositories",
             "`backend/app/agents`, `backend/app/evaluation`, "
             "`backend/app/guardrails`, `backend/app/services`",
             "Tools and persistence"],
            ["Integration",
             "MCP client and servers, the LLM service, the database engine, "
             "observability",
             "`backend/app/mcp`, `backend/app/db`, `backend/app/observability`",
             "External providers"],
        ],
        caption="The five layers and the direction of dependency.",
        widths=[1.0, 2.4, 1.9, 1.1],
    )

    g.diagram(
        """
+---------------------------------------------------------------------------+
|  PRESENTATION            React 18 + TypeScript + Vite                      |
|  Pages, components, TanStack Query hooks, i18next, ThemeProvider           |
+-------------------------------------|-------------------------------------+
                                      |  fetch  /api/v1/...
+-------------------------------------v-------------------------------------+
|  INTERFACE               FastAPI application                               |
|  request-id -> size limit -> rate limit -> security headers -> route       |
|  routes: health, travel, review, history      SPA fallback: static_site.py |
+-------------------------------------|-------------------------------------+
                                      |
+-------------------------------------v-------------------------------------+
|  ORCHESTRATION           LangGraph StateGraph over TravelState             |
|                                                                            |
|   START --(entry_router)--+--> supervisor ------+                          |
|                           +--> supervisor_rev --+--> specialists           |
|                           +--> final_response --------------> END          |
|                                                       |                    |
|                              output_guard <-----------+                    |
|                                   |                                        |
|                              evaluation --> human_review --> END (pause)   |
+-------------------------------------|-------------------------------------+
                                      |
+-------------------------------------v-------------------------------------+
|  DOMAIN                                                                    |
|  flight | hotel | weather | budget | itinerary | final_response            |
|  input_guard  prompt_injection  pii_guard  output_guard  tool_guard        |
|  evaluator (10 dimensions)      services      repositories                 |
+-------------------------------------|-------------------------------------+
                                      |
+-------------------------------------v-------------------------------------+
|  INTEGRATION                                                               |
|  MCP client --> aviation | search | weather servers (stdio / HTTP / in-proc)|
|  LLM service (Groq via langchain-groq)                                     |
|  SQLAlchemy engine --> PostgreSQL (container or Railway) / SQLite (tests)  |
|  LangSmith tracing (optional, never load-bearing)                          |
+---------------------------------------------------------------------------+
""",
        "The five layers of JourneyMesh and the traffic between them.",
    )

    g.h2("Why the layers are separated this way")
    g.bullets([
        "The orchestration layer knows about agents but not about HTTP. The workflow "
        "can therefore be driven from a test, from the offline evaluation runner or "
        "from a future queue worker without any of them impersonating a web request.",
        "The domain layer knows about tools but not about transports. Whether a tool "
        "runs over MCP stdio, MCP streamable HTTP or an in-process adapter is decided "
        "in the integration layer, so agent code never changes when a provider does.",
        "The interface layer owns validation and security. By the time a request "
        "reaches an agent it has already been parsed into typed Pydantic models, "
        "size-limited, rate-limited and screened by the input guardrails.",
        "The presentation layer holds no secrets and no business rules. It renders "
        "what the API returns; every VITE_ variable it can see is safe to publish.",
    ])

    g.h2("Component inventory")
    g.table(
        ["Component", "File", "One-line responsibility"],
        [
            ["FastAPI application", "`backend/app/main.py`",
             "Builds the app, installs middleware, mounts routes and the SPA"],
            ["Workflow", "`backend/app/graph/travel_graph.py`",
             "Compiles and runs the LangGraph state machine"],
            ["Entry routing", "`backend/app/graph/routing.py`",
             "Chooses plan / revise / finalise and orders the agents to run"],
            ["Shared state", "`backend/app/graph/state.py`",
             "Defines TravelState and the rules for preserving results"],
            ["Supervisor", "`backend/app/agents/supervisor.py`",
             "Decides which specialists a request needs"],
            ["Agent base", "`backend/app/agents/base.py`",
             "Common tracing, tool access and error handling for every agent"],
            ["MCP client", "`backend/app/mcp/client.py`",
             "Authorises, dispatches and normalises every external tool call"],
            ["Tool Guard", "`backend/app/guardrails/tool_guard.py`",
             "Deny-by-default authorization for tool invocations"],
            ["Evaluator", "`backend/app/evaluation/evaluator.py`",
             "Scores a draft journey across ten dimensions"],
            ["Travel service", "`backend/app/services/travel_service.py`",
             "Bridges HTTP requests, the workflow and persistence"],
            ["Review service", "`backend/app/services/review_service.py`",
             "Applies approve and request-changes decisions"],
            ["Database engine", "`backend/app/db/database.py`",
             "Builds the engine, applies SSL mode and pool options"],
            ["Static site", "`backend/app/api/static_site.py`",
             "Serves the built React application with a router-safe fallback"],
        ],
        caption="The components a reader meets most often, and where to find them.",
        widths=[1.3, 2.1, 3.0],
    )

    g.understand([
        "Which five layers JourneyMesh is built from and which way dependencies point.",
        "Why the orchestration layer must not know about HTTP.",
        "Where to look first for routing, state, tools and persistence.",
        "Why nothing in the React application is allowed to hold a secret.",
    ])


# ---------------------------------------------------------------------------
def _request_lifecycle(g: Guide) -> None:
    g.h1("The Life of a Request", page_break=True)
    g.p(
        "This chapter follows a single first-time planning request from the browser to "
        "the rendered journey. Every step names the file that performs it, so the "
        "chapter doubles as a map of the codebase."
    )

    g.diagram(
        """
 1  Browser        PlannerForm submits a typed TripPlanRequest
 2  HTTP           POST /api/v1/trips/plan
 3  Middleware     request id -> body size -> rate limit -> security headers
 4  Route          api/routes/travel.py validates with Pydantic v2
 5  Service        travel_service.py creates the Trip row (status = draft)
 6  Input guard    relevance, size, markup, prompt injection, PII
 7  Graph START    entry_router -> "plan"
 8  supervisor     selects agents, writes selected_agents + execution_reason
 9  specialists    each selected agent runs in AGENT_EXECUTION_ORDER
       flight  --> tool_guard -> MCP client -> aviation server
       hotel   --> tool_guard -> MCP client -> search server
       weather --> tool_guard -> MCP client -> weather server
       budget  --> pure computation over flight + hotel results
       itinerary --> composes days from everything above
10  output_guard   secrets, markup, URL policy, internal consistency, schema
11  evaluation     ten dimensions, deterministic rules first
12  human_review   status = awaiting_review; graph reaches END
13  Persistence    TravelResult, HumanReview, ConversationMessage, AuditEvent
14  HTTP 200       the draft journey, its provider labels and its scores
15  Browser        TanStack Query caches it; ReviewPanel offers approve / change
""",
        "The fifteen steps of a first-time planning request.",
    )

    g.h2("Step by step")
    g.numbered([
        "Submission. PlannerForm collects origin, destination, dates, travellers, "
        "budget, travel style, interests and free-text instructions, and posts them "
        "as one structured object rather than as a chat message.",
        "Transport. The request goes to POST /api/v1/trips/plan. In production the "
        "React bundle and the API share an origin, so there is no cross-origin "
        "preflight and CORS is only relevant when the interface is hosted separately.",
        "Middleware. A request id is attached for correlation, the body is rejected "
        "if it exceeds MAX_REQUEST_SIZE, the client is checked against the rate "
        "limiter, and the security headers - including the content security policy - "
        "are prepared for the response.",
        "Validation. Pydantic v2 parses the payload into TripPlanRequest and "
        "TripConstraints. Dates, traveller counts, currency codes and language codes "
        "are validated here, so no agent ever has to defend against a malformed date.",
        "Persistence of intent. Before any model is called, the trip is written to "
        "the database with status 'draft'. If the process dies mid-run there is still "
        "a record of what was asked.",
        "Input guardrails. The free text is screened for relevance to travel, for "
        "size and markup abuse, for prompt-injection patterns and for personal data "
        "that should not be forwarded to a provider.",
        "Entry routing. entry_router inspects the state. With no prior result and no "
        "requested change it returns 'plan', so the graph starts at the supervisor.",
        "Supervision. The supervisor reads the request and writes selected_agents "
        "and a human-readable execution_reason into the state. It plans nothing "
        "itself.",
        "Specialist execution. The specialists node runs the selected agents in "
        "AGENT_EXECUTION_ORDER, so budget always sees flight and hotel results, and "
        "the itinerary always sees everything before it.",
        "Output guardrails. The assembled payload is checked for leaked secrets, "
        "injected markup, disallowed URLs, internal inconsistency and schema "
        "conformance.",
        "Evaluation. The evaluator scores the draft across ten dimensions. "
        "Deterministic rules run first; the optional LLM judge only ever adds "
        "opinions on top of facts that were already established.",
        "The pause. The human_review node sets the status to awaiting_review and the "
        "graph reaches END. This is the durable pause: the checkpoint holds the whole "
        "state until a person decides what happens next.",
        "Persistence of result. The travel result, the review record, the "
        "conversation messages and the audit events are written in one unit of work.",
        "Response. The API returns the journey together with its provider labels and "
        "its evaluation summary, so the interface can show not just an answer but how "
        "much of it is live data.",
        "Rendering. TanStack Query caches the response under the trip id; the trip "
        "page renders each section and the review panel offers approve or request "
        "changes.",
    ])

    g.callout(
        "note",
        "Nothing between step 6 and step 12 talks to the browser. The whole draft is "
        "produced, checked and scored before a person sees it, which is what makes the "
        "human review a decision rather than a correction.",
    )


# ---------------------------------------------------------------------------
def _revision_lifecycle(g: Guide) -> None:
    g.h1("The Life of a Revision", page_break=True)
    g.p(
        "Selective re-execution is the feature that most clearly separates JourneyMesh "
        "from a chat interface. When a traveller says \"find cheaper hotels under $100 "
        "a night, but keep my flights\", the system must change the hotels, recompute "
        "the money and the days that depend on them, and leave the flights byte for "
        "byte as they were."
    )

    g.h2("What happens")
    g.diagram(
        """
Traveller: "cheaper hotels under $100 a night, keep my flights"
       |
       v
POST /api/v1/trips/{id}/request-changes
       |
       v
review_service: revision_count += 1, review_status = changes_requested
       |
       v
graph resumes -> entry_router -> "revise" -> supervisor_revision
       |
       +-- analyse_change("cheaper hotels ... keep my flights")
       |        mentions hotels  -> {hotel_agent}
       |        mentions price   -> {hotel_agent, budget_agent}
       |        preservation     -> "keep my flights" -> protect flight_agent
       |
       +-- expand_dependents({hotel_agent, budget_agent})
       |        hotel  -> budget, itinerary
       |        budget -> itinerary
       |        result -> {hotel_agent, budget_agent, itinerary_agent}
       |
       +-- remove protected agents -> flight_agent never re-runs
       |
       v
specialists node runs, in order: hotel_agent, budget_agent, itinerary_agent
       |
       v
state["flight_results"] is untouched and carried forward unchanged
       |
       v
output_guard -> evaluation -> human_review (revision 2)
""",
        "How one sentence becomes a three-agent re-run with the flights preserved.",
    )

    g.h2("The three rules that make it correct")
    g.numbered([
        "Intent detection decides the seed set. The supervisor matches the requested "
        "change against its intent vocabulary - flight, hotel, weather, budget and "
        "itinerary term lists - and starts with the agents that were named.",
        "Dependency expansion decides the rest. AGENT_DEPENDENTS declares that a "
        "hotel change invalidates the budget and the itinerary, that a budget change "
        "invalidates the itinerary, and that an itinerary change invalidates nothing. "
        "expand_dependents closes the seed set over that relation.",
        "Preservation requests subtract from the result. The phrase \"keep my "
        "flights\" is matched by an explicit preservation pattern, and the named "
        "agent is removed from the re-run set even if intent detection put it there.",
    ])

    g.table(
        ["Agent", "Depends on", "Re-runs when these change"],
        [
            ["`flight_agent`", "Nothing", "Only an explicit flight request"],
            ["`hotel_agent`", "Nothing", "Only an explicit accommodation request"],
            ["`weather_agent`", "Nothing", "Only an explicit weather or date request"],
            ["`budget_agent`", "Flights, hotels", "Flights, hotels, or money"],
            ["`itinerary_agent`", "Everything above",
             "Flights, hotels, weather, budget, or activities"],
        ],
        caption="The dependency relation encoded in AGENT_DEPENDENTS.",
        widths=[1.2, 1.5, 2.6],
    )

    g.h2("How preservation is verified")
    g.p(
        "Preservation is not a claim in the documentation, it is an assertion in the "
        "test suite and an offline evaluation case. The case "
        "'cheaper_hotel_revision' declares the agents it expects to re-run, and the "
        "regression test compares the flight payload before and after the revision "
        "and requires them to be equal."
    )
    g.code(
        """
# backend/app/graph/state.py

AGENT_RESULT_MARKERS: dict[str, str] = {
    "flight_results": "options",
    "hotel_results": "options",
    "weather_info": "forecast",
    "budget_analysis": "breakdown",
    "itinerary_plan": "days",
}


def has_result(state: TravelState, agent: str) -> bool:
    \"\"\"True when the agent already has usable output in the state.\"\"\"
    key = AGENT_STATE_KEYS.get(agent)
    if key is None:
        return False
    payload = state.get(key)
    if not payload:
        return False
    if isinstance(payload, dict):
        marker = AGENT_RESULT_MARKERS.get(key)
        if marker and marker in payload:
            return bool(payload[marker])
        return any(bool(value) for value in payload.values())
    return True
""",
        caption="Listing. A result marker distinguishes 'ran and found nothing' from "
                "'never ran', so an empty option list is not preserved as if it were "
                "an answer.",
    )

    g.h2("The revision ceiling")
    g.p(
        "Revisions are bounded by MAX_REVISION_COUNT, which defaults to 3. When the "
        "ceiling is reached the workflow records a revision-limit audit event, sets "
        "the review status to revision_limit_reached, and stops offering further "
        "changes. This is a cost and safety control: an unbounded revision loop is an "
        "unbounded spend of model tokens and provider quota."
    )

    g.understand([
        "Why a revision re-runs three agents rather than one or five.",
        "How AGENT_DEPENDENTS turns one changed agent into a correct re-run set.",
        "What 'keep my flights' does to the set the supervisor produced.",
        "Why an empty option list must not be preserved as though it were a result.",
        "What MAX_REVISION_COUNT protects against.",
    ])
