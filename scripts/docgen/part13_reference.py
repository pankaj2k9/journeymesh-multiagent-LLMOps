"""Glossary, quick revision, and references."""

from __future__ import annotations

from docgen.builder import Guide
from docgen.repo import FACTS


def write(g: Guide) -> None:
    _glossary(g)
    _revision(g)
    _file_map(g)
    _references(g)


# ---------------------------------------------------------------------------
def _glossary(g: Guide) -> None:
    g.h1("Glossary", page_break=True)
    g.p(
        "Each entry gives the technical definition first and the plain-language "
        "version second, in the same two-level form used throughout this guide."
    )

    entries = [
        ("ADR",
         "An architecture decision record: a short document stating a decision, its "
         "context, the alternatives rejected and the consequences accepted.",
         "A note explaining why the obvious alternative was not chosen."),
        ("Agent",
         "A component given a goal rather than a procedure, that selects its own "
         "actions, can invoke tools, and decides when the goal is met.",
         "A colleague you brief instead of instruct."),
        ("Agentic AI",
         "Systems in which part of the control flow is decided at run time from the "
         "content of a request rather than fixed by the programmer.",
         "AI that works out its own steps instead of following a script."),
        ("Alembic",
         "A migration tool for SQLAlchemy that versions schema changes as ordered "
         "revisions.",
         "A numbered list of changes to the database's shape."),
        ("Blocking dimension",
         "An evaluation dimension whose failure means the output must not be shown at "
         "all, regardless of the aggregate score.",
         "A check you cannot make up for by scoring well elsewhere."),
        ("Checkpointer",
         "A store that serialises graph state after each node against a thread "
         "identifier, so a run can resume in another process.",
         "A save point. The workflow writes down everything before it stops."),
        ("Conditional edge",
         "A LangGraph transition whose destination is chosen at run time by a router "
         "function of the state.",
         "A fork in the flowchart that is decided while it is running."),
        ("Content security policy",
         "An HTTP header restricting the sources a page may load scripts, styles and "
         "other resources from.",
         "A list of what the page is allowed to load, enforced by the browser."),
        ("Deny by default",
         "An authorization posture in which the absence of an explicit permission is a "
         "denial.",
         "Nothing is allowed unless it is on the list."),
        ("Dependency closure",
         "The smallest set containing a seed set and every element reachable from it "
         "under a dependency relation.",
         "Everything that has to be redone because of what you changed."),
        ("Guardrail",
         "A deterministic check outside the model whose verdict is enforced by the "
         "application rather than by the model's cooperation.",
         "A rule the AI cannot talk its way past."),
        ("HITL",
         "Human in the loop: a mandatory human decision point before output is "
         "treated as final.",
         "A person has to say yes before it counts."),
        ("i18n",
         "Internationalisation: designing so that language-specific content is data "
         "rather than code.",
         "Making the app speak more than one language without rewriting it."),
        ("JSONB",
         "PostgreSQL's binary JSON column type, queryable and indexable rather than "
         "stored as opaque text.",
         "A column holding a whole JSON object that the database can look inside."),
        ("LangGraph",
         "A library for expressing an application as a directed graph of nodes over a "
         "shared typed state, with persistence and resumption.",
         "A flowchart you can execute, that remembers where it got to."),
        ("LangSmith",
         "A tracing and evaluation service that records LLM application runs as "
         "inspectable trees.",
         "A flight recorder for AI runs."),
        ("LLMOps",
         "The operational practice of deploying, monitoring, evaluating and governing "
         "LLM applications.",
         "Everything after 'it works on my machine' for AI systems."),
        ("Luhn checksum",
         "A checksum algorithm satisfied by valid payment card numbers, used to "
         "distinguish them from arbitrary digit strings.",
         "A quick arithmetic test that tells a real card number from a random one."),
        ("MCP",
         "The Model Context Protocol: an open protocol standardising how applications "
         "expose tools, resources and prompts to language models.",
         "A universal adapter for AI tools."),
        ("Middleware",
         "A layer wrapping every request and response, applied in a defined order "
         "around the route handler.",
         "Checks that happen on the way in and on the way out."),
        ("Migration",
         "A versioned script transforming a database schema from one revision to the "
         "next.",
         "One numbered change to the database's shape."),
        ("Bind mount",
         "A host directory mapped into a container's filesystem, so the data lives "
         "outside the container's lifecycle.",
         "A folder on your computer that the container writes into."),
        ("Docker Compose",
         "A single-host orchestrator declaring a set of containers, their network, "
         "configuration and startup dependencies in one file.",
         "One file describing your whole application, started with one command."),
        ("Private networking",
         "The Compose bridge network joining the containers on one host, on which "
         "each is addressable by service name and which never crosses the public "
         "internet.",
         "A phone line between your own services that nobody outside can dial."),
        ("VPS",
         "A virtual private server: one rented Linux machine with its own IP "
         "address and root access, on which you install and operate everything "
         "yourself.",
         "A computer in a datacentre that nobody else logs into."),
        ("Container registry (GHCR)",
         "A server storing built Docker images by name and tag. CI pushes to it; "
         "the VPS pulls from it.",
         "A shelf CI puts finished images on and the server takes them from."),
        ("Shared reverse proxy (Caddy)",
         "The single process accepting every public connection on the VPS, "
         "terminating TLS with certificates it obtains and renews itself, and "
         "forwarding each domain to a container on a shared Docker network. Its "
         "own Compose project, not part of any application.",
         "The building's front door, not one flat's."),
        ("External Docker network",
         "A network created once on the host and declared ``external: true`` by "
         "every stack that joins it, so no stack owns it and bringing one down "
         "does not disturb the others.",
         "A corridor the flats open onto, which none of them owns."),
        ("Host key pinning",
         "Recording a server's SSH public host key so a client refuses to connect "
         "to anything answering with a different one.",
         "Checking the face at the door, not just the address on the envelope."),
        ("workflow_dispatch",
         "A GitHub Actions trigger that fires only when a person starts the workflow.",
         "A button. Nothing runs until somebody presses it."),
        ("Node",
         "A step in a LangGraph workflow: a callable taking state and returning "
         "state.",
         "One box in the executable flowchart."),
        ("Prompt injection",
         "An attack in which text supplied as data is interpreted by a model as "
         "instruction.",
         "Hiding an order inside something the AI was only supposed to read."),
        ("Provenance label",
         "A per-value marker recording how the value was obtained: LIVE, "
         "SEARCH_DERIVED, ESTIMATE or UNAVAILABLE.",
         "A label on every number saying where it came from."),
        ("Pydantic",
         "A validation library that builds validators from type annotations and "
         "returns typed data or a structured error.",
         "You describe what good data looks like in ordinary types."),
        ("Rate limiting",
         "Bounding how many requests a client may make within a time window.",
         "A cap on how often one person can ask."),
        ("Selective re-execution",
         "Re-running only the components affected by a change, preserving the output "
         "of those that were not.",
         "Changing one part of the answer without redoing all of it."),
        ("Server state",
         "Data owned by a remote system, of which the client holds only a copy that "
         "can go stale.",
         "Anything that really lives on the server."),
        ("Span",
         "A named, timed region of execution recorded in a trace, optionally carrying "
         "metadata.",
         "A labelled stopwatch around one step."),
        ("SPA fallback",
         "Serving the application's entry HTML for any unmatched path so a client-side "
         "router can resolve it.",
         "Giving the browser the app for any URL, and letting the app decide what to "
         "show."),
        ("State",
         "The single shared structure every node in the graph reads from and writes "
         "to.",
         "The one shared notebook all the agents write in."),
        ("Supervisor",
         "The agent that decides which specialists execute, without performing "
         "domain work itself.",
         "The one who assigns the work and does none of it."),
        ("Tool",
         "A named, schema-checked capability an agent may invoke, reached here through "
         "MCP.",
         "Something the AI can actually do, with rules about how."),
        ("Tool Guard",
         "The deny-by-default authorization component that validates every tool call "
         "before dispatch.",
         "The bouncer between what the AI wants to do and the outside world."),
        ("TypedDict",
         "A Python typing construct describing a dictionary with known keys and value "
         "types.",
         "A dictionary whose shape is written down."),
        ("Weighted mean",
         "An average in which each contributing value is scaled by an importance "
         "weight before averaging.",
         "An average where some things count for more."),
    ]
    g.table(
        ["Term", "Technical", "In plain words"],
        [[f"**{t}**" if False else t, tech, simple] for t, tech, simple in entries],
        caption="Glossary of terms used in this guide.",
        widths=[1.0, 2.6, 2.2],
        size=8.5,
    )


# ---------------------------------------------------------------------------
def _revision(g: Guide) -> None:
    g.h1("Quick Revision", page_break=True)
    g.p(
        "One page of the facts most worth having available without thinking. Read it "
        "before an interview or a viva."
    )

    g.h2("The numbers")
    g.table(
        ["Fact", "Value"],
        [
            ["Graph nodes", f"7 - {', '.join(FACTS.graph_nodes)}"],
            ["Specialist agents", "5 - flight, hotel, weather, budget, itinerary"],
            ["Plus", "supervisor and final response"],
            ["Execution order", "flight, hotel, weather, budget, itinerary"],
            ["Provenance labels", "LIVE, SEARCH_DERIVED, ESTIMATE, UNAVAILABLE"],
            ["Guardrails", "input, prompt injection, PII, tool, output"],
            ["Injection block threshold", "0.80"],
            ["Evaluation dimensions", "10"],
            ["Blocking dimensions", "safety, schema_validity"],
            ["Highest weight", "safety at 2.0"],
            ["Revision ceiling", "MAX_REVISION_COUNT, default 3"],
            ["Languages", "en (default), bn, hi"],
            ["Themes", "light (default), dark"],
            ["Database tables", f"{len(FACTS.tables)} - {', '.join(FACTS.tables)}"],
            ["Tool policies", f"{len(FACTS.tools)} declared, 6 enabled"],
            ["HTTP routes", str(len(FACTS.api_routes))],
            ["Offline evaluation cases", str(len(FACTS.eval_cases))],
            ["Backend test functions", str(FACTS.backend_test_count)],
            ["Image stages", "3 - frontend builder, backend builder, application"],
            ["Container user", "non-root, uid 10001"],
            ["Health path", "/api/v1/health"],
        ],
        caption="Facts worth knowing cold.",
        widths=[1.8, 4.0],
    )

    g.h2("The dependency relation")
    g.diagram(
        """
   flight  ---> budget ---> itinerary
       \\           ^            ^
        \\          |            |
   hotel  ---------+------------+
                                ^
   weather -----------------------

   flight    invalidates  budget, itinerary
   hotel     invalidates  budget, itinerary
   weather   invalidates  itinerary
   budget    invalidates  itinerary
   itinerary invalidates  nothing
""",
        "AGENT_DEPENDENTS, the relation that scopes every revision.",
    )

    g.h2("Ten sentences that carry most of the design")
    g.numbered([
        "A supervisor decides which specialists run; it never plans a trip itself.",
        "Routing is deterministic Python, so every decision can be asserted exactly.",
        "Agents share one TypedDict and never call each other, and each owns exactly "
        "one result key.",
        "The graph ends at human review; the pause is a checkpoint, not a held "
        "request.",
        "A revision seeds an agent set from intent, closes it over the dependency "
        "relation, then subtracts what the traveller asked to keep.",
        "Every external call goes through MCP behind a guard that denies by default.",
        "Every value carries a provenance label, and the interface shows it.",
        "The budget agent uses no model, because arithmetic is not a language task.",
        "Guardrails are code outside the model; a prompt instruction is not a "
        "control.",
        "Anything checkable by rule is checked by rule - including nine of the ten "
        "evaluation dimensions.",
    ])

    g.h2("Three things never to say")
    g.bullets([
        "A latency, throughput or accuracy figure. None has been measured; \"not "
        "measured yet\" is the correct answer.",
        "That the system is secure. It has specific controls with specific limits, and "
        "no penetration test has been performed.",
        "That the images have been verified running in production. They are built by "
        "CI; local Docker was unavailable.",
    ])


# ---------------------------------------------------------------------------
def _file_map(g: Guide) -> None:
    g.h1("Where Everything Lives", page_break=True)
    g.table(
        ["I want to understand", "Read"],
        [
            ["Every constant and name", "`backend/app/core/constants.py`"],
            ["Configuration and settings", "`backend/app/core/config.py`"],
            ["Server-side translation", "`backend/app/core/i18n.py`"],
            ["The shared state", "`backend/app/graph/state.py`"],
            ["The workflow", "`backend/app/graph/travel_graph.py`"],
            ["Entry routing and agent ordering", "`backend/app/graph/routing.py`"],
            ["Agent selection and revision analysis",
             "`backend/app/agents/supervisor.py`"],
            ["Common agent behaviour", "`backend/app/agents/base.py`"],
            ["An individual agent", "`backend/app/agents/<name>_agent.py`"],
            ["Tool authorization policy", "`backend/app/guardrails/policies.py`"],
            ["Tool authorization enforcement", "`backend/app/guardrails/tool_guard.py`"],
            ["Input screening", "`backend/app/guardrails/input_guard.py`"],
            ["Injection detection", "`backend/app/guardrails/prompt_injection.py`"],
            ["Personal data redaction", "`backend/app/guardrails/pii_guard.py`"],
            ["Output screening", "`backend/app/guardrails/output_guard.py`"],
            ["Evaluation dimensions and weights",
             "`backend/app/evaluation/schemas.py`"],
            ["Evaluation checks", "`backend/app/evaluation/rules.py`"],
            ["Score aggregation", "`backend/app/evaluation/metrics.py`"],
            ["Offline evaluation runner", "`backend/app/evaluation/runner.py`"],
            ["The MCP client", "`backend/app/mcp/client.py`"],
            ["MCP servers", "`backend/app/mcp/{aviation,search,weather_server}.py`"],
            ["HTTP routes", "`backend/app/api/routes/`"],
            ["SPA mounting", "`backend/app/api/static_site.py`"],
            ["Security headers and the CSP", "`backend/app/security/headers.py`"],
            ["Rate limiting", "`backend/app/security/rate_limit.py`"],
            ["The audit trail", "`backend/app/security/audit.py`"],
            ["Tracing", "`backend/app/observability/tracing.py`"],
            ["LangSmith integration", "`backend/app/observability/langsmith.py`"],
            ["Database models", "`backend/app/db/models.py`"],
            ["Engine and pool configuration", "`backend/app/db/database.py`"],
            ["The data layer of the interface", "`frontend/src/hooks/useTrips.ts`"],
            ["The only place fetch appears", "`frontend/src/api/client.ts`"],
            ["Theme primitives", "`frontend/src/theme/theme.ts`"],
            ["Both palettes", "`frontend/src/index.css`"],
            ["Design tokens", "`frontend/tailwind.config.js`"],
            ["The production image", "`Dockerfile`"],
            ["Container start-up", "`backend/docker-entrypoint.sh`"],
            ["The compose stack", "`docker-compose.yml`"],
            ["The quality gate", "`.github/workflows/ci.yml`"],
            ["The deployment path", "`.github/workflows/deploy.yml`"],
            ["The production stack", "`deploy/docker-compose.prod.yml`"],
            ["The VPS-level shared reverse proxy", "`deploy/proxy/docker-compose.yml`, "
             "`deploy/proxy/Caddyfile`"],
            ["Preparing and backing up the VPS", "`deploy/bootstrap-vps.sh`, "
             "`deploy/backup.sh`"],
            ["The local stack", "`docker-compose.yml`, `docker-compose.dev.yml`"],
            ["Every developer command", "`Makefile`"],
            ["Deployment verification", "`scripts/verify_deployment.py`"],
            ["End-to-end smoke test", "`scripts/smoke.py`"],
            ["This document's generator", "`scripts/docgen/`"],
        ],
        caption="A direct index from question to file.",
        widths=[2.4, 3.4],
        size=8.5,
    )


# ---------------------------------------------------------------------------
def _references(g: Guide) -> None:
    g.h1("References", page_break=True)

    g.h2("Primary technologies")
    g.table(
        ["Technology", "Where to read about it"],
        [
            ["LangGraph", "The LangGraph documentation - state graphs, conditional "
                          "edges, checkpointers and persistence"],
            ["LangChain", "The LangChain documentation - core message and runnable "
                          "abstractions"],
            ["Model Context Protocol", "The MCP specification and SDK documentation - "
                                       "hosts, clients, servers, transports"],
            ["LangSmith", "The LangSmith documentation - tracing, run trees and "
                          "evaluation"],
            ["FastAPI", "The FastAPI documentation - routing, dependencies, "
                        "middleware and OpenAPI"],
            ["Pydantic", "The Pydantic v2 documentation, and pydantic-settings for "
                         "configuration"],
            ["SQLAlchemy", "The SQLAlchemy 2.0 documentation - typed ORM mappings and "
                           "engine configuration"],
            ["Alembic", "The Alembic documentation - revisions, autogeneration and "
                        "offline mode"],
            ["PostgreSQL", "The PostgreSQL manual - JSON and JSONB types, indexing"],
            ["Docker Compose", "The Compose specification - services, health "
                               "conditions, overrides and profiles"],
            ["Caddy", "The Caddy documentation - automatic HTTPS, the Caddyfile "
                      "and reverse_proxy"],
            ["GHCR", "The GitHub Packages documentation - publishing and pulling "
                     "container images, and the permissions a workflow needs"],
            ["React", "The React documentation"],
            ["React Router", "The React Router documentation"],
            ["TanStack Query", "The TanStack Query documentation - queries, "
                               "mutations, invalidation"],
            ["Tailwind CSS", "The Tailwind CSS documentation - dark mode, theme "
                             "extension, arbitrary values"],
            ["i18next", "The i18next and react-i18next documentation"],
            ["Vite", "The Vite documentation"],
            ["Vitest", "The Vitest documentation"],
            ["Testing Library", "The Testing Library documentation"],
            ["Docker", "The Docker documentation - multi-stage builds, healthchecks, "
                       "Compose conditions"],
            ["GitHub Actions", "The GitHub Actions documentation - workflow_run "
                               "triggers, secrets, environments"],

        ],
        caption="Documentation for every technology used.",
        widths=[1.3, 4.5],
    )

    g.h2("Concepts")
    g.bullets([
        "Web application security - the OWASP Top Ten, and OWASP's guidance on risks "
        "specific to LLM applications, for prompt injection, insecure output handling "
        "and excessive agency.",
        "Content Security Policy - the W3C specification, for hash-based script "
        "allowlisting.",
        "Web Content Accessibility Guidelines - for the contrast ratios recorded "
        "alongside the theme tokens.",
        "The Luhn algorithm - for payment-card checksum validation.",
        "Design-science research methodology - for the artefact-and-evaluation "
        "structure used in the academic chapter.",
    ])

    g.h2("A note on sources")
    g.p(
        "This guide was generated from the JourneyMesh repository itself. Dependency "
        "lists, environment variables, database tables, graph nodes, agent names, tool "
        "policies, API routes, translation key counts, evaluation cases and test counts "
        "are read from the source at generation time rather than transcribed, so the "
        "document cannot silently drift from the code it describes. Explanatory "
        "material, design reasoning and interview preparation are original to this "
        "guide."
    )

    g.h2("Colophon")
    g.p(
        "Generated by scripts/docgen from the repository, using python-docx. The "
        "generator is part of the repository and can be re-run at any time to produce "
        "an updated document reflecting the code as it then stands."
    )
