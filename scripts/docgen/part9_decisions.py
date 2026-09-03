"""Architecture decision records, trade-offs, scalability, cost, failure modes."""

from __future__ import annotations

from docgen.builder import Guide


def _adr(g: Guide, number: int, title: str, *, status: str, context: str,
         decision: str, consequences: list[str], alternatives: list[list[str]]) -> None:
    g.h2(f"ADR-{number:03d}. {title}")
    g.table(
        ["Status", "Date"],
        [[status, "At the time of writing"]],
        caption=f"ADR-{number:03d} status.",
        widths=[1.0, 1.0],
    )
    g.h4("Context")
    g.p(context)
    g.h4("Decision")
    g.p(decision)
    g.h4("Alternatives considered")
    g.table(["Alternative", "Why it was not chosen"], alternatives,
            caption=f"ADR-{number:03d} alternatives.", widths=[1.6, 4.2])
    g.h4("Consequences")
    g.bullets(consequences)


def write(g: Guide) -> None:
    _intro(g)
    _adrs(g)
    _tradeoffs(g)
    _scalability(g)
    _performance(g)
    _cost(g)
    _failure_modes(g)


# ---------------------------------------------------------------------------
def _intro(g: Guide) -> None:
    g.h1("Architecture Decision Records", page_break=True)
    g.p(
        "An architecture decision record states a decision, the context that forced "
        "it, the alternatives that were rejected and the consequences that were "
        "accepted. The value is in the last two: anyone can see what was built, but "
        "only a record like this preserves why the obvious alternative was not."
    )
    g.callout(
        "note",
        "These records describe decisions as they stand in the repository. Where a "
        "consequence is a measurable cost that has not been measured, this document "
        "says so rather than inventing a figure.",
    )


# ---------------------------------------------------------------------------
def _adrs(g: Guide) -> None:
    _adr(
        g, 1, "Use a supervised multi-agent architecture",
        status="Accepted",
        context=(
            "Travel planning spans several information domains with different sources "
            "of truth. A single prompt has to be good at all of them at once, cannot "
            "be partially re-run, and gives no way to tell a looked-up price from an "
            "invented one."
        ),
        decision=(
            "A supervisor selects specialist agents at run time. Each specialist owns "
            "one domain and one slice of a shared state."
        ),
        alternatives=[
            ["A single prompt with a long instruction",
             "No partial re-execution; no provenance; one prompt has to be good at "
             "everything"],
            ["A single agent in a tool-calling loop",
             "Control flow and domain reasoning are owned by the same model, so a bad "
             "routing decision corrupts the whole answer, and loops are hard to bound"],
            ["Autonomous agent-to-agent negotiation",
             "Non-deterministic, unbounded in cost, and effectively untestable case by "
             "case"],
        ],
        consequences=[
            "Each agent's prompt is small and can be tested in isolation.",
            "Selective re-execution becomes possible, which is the system's most "
            "distinctive behaviour.",
            "State design has to be explicit and ownership has to be respected.",
            "There are more moving parts than a single-prompt system, and the "
            "supervisor becomes a critical component.",
        ],
    )

    _adr(
        g, 2, "Orchestrate with LangGraph rather than a chain",
        status="Accepted",
        context=(
            "The workflow must stop, wait for a human, and later resume in a possibly "
            "different process, taking one of two different paths depending on what "
            "the human decided."
        ),
        decision=(
            "Model the workflow as a LangGraph StateGraph with a conditional entry "
            "edge and a checkpointer."
        ),
        alternatives=[
            ["A LangChain chain",
             "A fixed sequence cannot branch on content and has nowhere to pause"],
            ["Hand-written async orchestration",
             "Would need its own checkpointing, resumption and state-merge semantics - "
             "that is the library"],
            ["A workflow engine such as Temporal",
             "Correct at a larger scale, but a heavy operational dependency for a "
             "single free-tier container"],
        ],
        consequences=[
            "The pause is durable rather than an open request.",
            "State must be JSON-compatible so it survives the checkpoint round trip.",
            "The graph and the checkpoint store are a second persistence concern "
            "alongside the application tables.",
        ],
    )

    _adr(
        g, 3, "End the graph at human review instead of looping",
        status="Accepted",
        context=(
            "A running graph cannot wait for a person for an unbounded time. The HTTP "
            "request would time out, and on a free tier the container may sleep "
            "between the draft and the decision."
        ),
        decision=(
            "The draft run ends at the human_review node. The state is checkpointed "
            "and the trip persisted; a later invocation resumes and the entry router "
            "chooses the revise or finalise branch."
        ),
        alternatives=[
            ["LangGraph's interrupt mechanism with a held request",
             "Still ties the pause to a live request and a live process"],
            ["Polling from the browser with the run held in memory",
             "Loses everything when the container recycles, which on a free tier is "
             "routine"],
        ],
        consequences=[
            "The pause survives a process restart, a redeploy and a container sleep.",
            "There is no edge from human_review back into the specialists, which looks "
            "like an omission until the reason is known - hence this record.",
            "Resumption logic lives in the entry router and must stay correct.",
        ],
    )

    _adr(
        g, 4, "Route deterministically in Python, not with a model",
        status="Accepted",
        context=(
            "The supervisor's decision runs on every request and every revision and "
            "determines which agents execute."
        ),
        decision=(
            "Routing is an intent vocabulary plus regular expressions over the request "
            "text, with a full-trip fallback when nothing matches."
        ),
        alternatives=[
            ["Ask the model for a JSON array of agents",
             "Adds a model call to every interaction, can only be tested "
             "statistically, and fails when the model is unavailable"],
            ["Train a classifier",
             "Needs labelled data that does not exist for this project, and is far "
             "more machinery than the problem justifies"],
        ],
        consequences=[
            "Routing decisions can be asserted exactly in tests.",
            "Zero cost and zero latency for the decision.",
            "Unusual phrasings that share no vocabulary with the intent lists fall "
            "back to selecting every agent - a complete plan rather than an empty one, "
            "but not the minimal one.",
        ],
    )

    _adr(
        g, 5, "Reach every external tool through MCP",
        status="Accepted",
        context=(
            "Several providers, several agents, and a hard requirement that every "
            "external call be authorised, bounded and labelled."
        ),
        decision=(
            "All tools are exposed through MCP servers and reached through one client, "
            "with an in-process adapter as the fallback transport."
        ),
        alternatives=[
            ["Direct HTTP clients inside each agent",
             "No single choke point for authorization, no uniform error shape, and a "
             "provider change touches agent code"],
            ["A plain internal tool registry",
             "Most of the benefit, but gives up the interoperability and the typed "
             "discovery that make the protocol worth learning"],
        ],
        consequences=[
            "One place to authorise, instrument and normalise every external call.",
            "A provider can be swapped without touching an agent.",
            "A protocol layer to understand and operate, which for a single-provider "
            "system would be pure overhead.",
        ],
    )

    _adr(
        g, 6, "Deny by default in the Tool Guard",
        status="Accepted",
        context=(
            "The boundary between a model's suggestion and an action in the world is "
            "the most security-relevant point in the system."
        ),
        decision=(
            "A tool absent from TOOL_POLICIES cannot be called. Every call is checked "
            "for registration, enablement, agent authorization, argument schema, "
            "forbidden keys, operation class and per-run budget."
        ),
        alternatives=[
            ["A denylist of dangerous tools",
             "A forgotten entry becomes a permission, which is the wrong direction for "
             "a mistake to fail in"],
            ["Trust the agent's prompt",
             "A prompt is a request, not a control"],
        ],
        consequences=[
            "A forgotten policy produces a refusal and an audit event, not an "
            "unauthorised call.",
            "Even a successful prompt injection cannot reach an unauthorised tool.",
            "Adding a tool requires adding a policy, which is deliberate friction.",
        ],
    )

    _adr(
        g, 7, "Label the provenance of every value",
        status="Accepted",
        context=(
            "An LLM system can produce a confident price that came from nowhere. "
            "Hiding that is the actual harm."
        ),
        decision=(
            "Every value carries one of LIVE, SEARCH_DERIVED, ESTIMATE or UNAVAILABLE, "
            "and the interface shows it."
        ),
        alternatives=[
            ["Present everything uniformly",
             "Dishonest, and makes a degraded response indistinguishable from a good "
             "one"],
            ["Fail when live data is unavailable",
             "An estimate-based plan is genuinely useful; refusing to produce one "
             "helps nobody"],
        ],
        consequences=[
            "A traveller can tell a quoted price from an indicative one.",
            "Provider outages degrade the response visibly instead of silently.",
            "Every agent must classify its own output, and the client canonicalises "
            "any label it does not recognise.",
        ],
    )

    _adr(
        g, 8, "Compute the budget without a model",
        status="Accepted",
        context=(
            "Arithmetic is the one part of a travel plan where correctness is binary, "
            "and it is a known weak point for language models."
        ),
        decision=(
            "The budget agent calls no tools and no model. It is Python arithmetic "
            "over what the flight and hotel agents found, plus reference figures for "
            "unpriced categories."
        ),
        alternatives=[
            ["Ask the model to total the costs",
             "Introduces arithmetic errors into the one place they are unambiguous"],
            ["Ask the model and verify with a rule",
             "The rule is the answer; the model call is then pure cost"],
        ],
        consequences=[
            "Budget totals are exactly reproducible.",
            "The budget_consistency evaluation dimension can assert the arithmetic "
            "directly.",
            "The budget cannot express nuance a model might have added, which is an "
            "acceptable loss.",
        ],
    )

    _adr(
        g, 9, "Use Neon rather than the hosting platform's database",
        status="Accepted",
        context=(
            "A free-tier database attached to a web service typically shares that "
            "service's lifetime and expiry."
        ),
        decision=(
            "PostgreSQL is Neon, reached only through DATABASE_URL. There is no "
            "database block in the Render blueprint."
        ),
        alternatives=[
            ["The platform's own managed PostgreSQL",
             "Couples the data's lifetime to the service, and moving hosts means "
             "migrating the database"],
            ["SQLite on a persistent disk",
             "Free-tier containers have ephemeral filesystems; the data would not "
             "survive a redeploy"],
        ],
        consequences=[
            "The application has no idea who hosts its database.",
            "Compute scales to zero when idle, so the connection settings must handle "
            "cold starts and dead pooled connections.",
            "Moving the application to another host requires no data migration.",
        ],
    )

    _adr(
        g, 10, "Ship one production image serving both API and interface",
        status="Accepted",
        context=(
            "A free tier that allows one web service, and an interface that must be "
            "served from somewhere."
        ),
        decision=(
            "A three-stage Dockerfile builds the React bundle and serves it from the "
            "Python application, with a router-safe SPA fallback."
        ),
        alternatives=[
            ["Separate frontend and backend services",
             "Two free services, cross-origin configuration, and two cold starts per "
             "interaction"],
            ["A static host for the interface plus an API service",
             "Reasonable, and a natural next step; it adds a second deployment path "
             "and CORS configuration that the single image does not need"],
        ],
        consequences=[
            "Same-origin, so no CORS in production.",
            "One deployment, one health check, one cold start.",
            "The interface cannot be scaled or cached independently of the API.",
        ],
    )

    _adr(
        g, 11, "Deploy through GitHub Actions, with Render auto-deploy off",
        status="Accepted",
        context=(
            "If both the platform's own watcher and a CI-driven hook are active, every "
            "merge deploys twice and the two races each other."
        ),
        decision=(
            "`autoDeploy: false` in the blueprint, and a Deploy workflow triggered by "
            "the successful completion of CI on main."
        ),
        alternatives=[
            ["Let Render deploy on push",
             "Deploys code that has not passed CI"],
            ["Both",
             "Double deployment and a race"],
        ],
        consequences=[
            "Nothing reaches production without passing CI first.",
            "The deploy hook is a credential and must be held only as a GitHub secret.",
            "A service created by hand in the dashboard must have auto-deploy switched "
            "off manually.",
        ],
    )

    _adr(
        g, 12, "Make LangSmith optional at every level",
        status="Accepted",
        context=(
            "Tracing is valuable for an agentic system and must never be the reason a "
            "traveller cannot get a plan."
        ),
        decision=(
            "All tracing goes through a single `span()` integration point that becomes "
            "a no-op when tracing is disabled, unconfigured or the library is absent."
        ),
        alternatives=[
            ["Instrument agents directly with the tracing SDK",
             "Couples every agent to the vendor and makes its absence a failure"],
            ["Require tracing in production",
             "An outage at the tracing provider would become an outage here"],
        ],
        consequences=[
            "The system runs identically with tracing on or off.",
            "Only allowlisted, sanitised metadata leaves the process.",
            "The trace is less rich than direct instrumentation would be, which is the "
            "price of the isolation.",
        ],
    )

    _adr(
        g, 13, "Two themes only, defaulting to light",
        status="Accepted",
        context=(
            "A system-following third option was implemented and then removed after "
            "use showed it was more confusing than helpful."
        ),
        decision=(
            "`Theme` is the literal type `'light' | 'dark'`, the default is light, and "
            "the choice persists under `journeymesh_theme`."
        ),
        alternatives=[
            ["Light, dark and system",
             "Three states to test, and an interface that changes appearance because "
             "the operating system crossed sunset"],
            ["Dark only",
             "Excludes travellers who prefer light, and print and screenshots suffer"],
        ],
        consequences=[
            "Two states to design, test and document.",
            "A returning traveller sees exactly what they chose.",
            "Someone whose whole system is dark must choose dark once here too.",
        ],
    )


# ---------------------------------------------------------------------------
def _tradeoffs(g: Guide) -> None:
    g.h1("Trade-offs in One Table", page_break=True)
    g.table(
        ["Choice", "Gained", "Given up"],
        [
            ["Multi-agent over single prompt",
             "Partial re-execution, testable prompts, contained failures",
             "More components, an explicit state contract"],
            ["Deterministic routing",
             "Exact tests, zero cost, works without a model",
             "Weaker on phrasings outside the vocabulary"],
            ["MCP over direct HTTP",
             "One authorization choke point, provider swappability",
             "A protocol layer to operate"],
            ["Sequential specialists",
             "One checkpoint boundary, a readable trace, simple ordering",
             "Flights, hotels and weather could have overlapped"],
            ["JSON columns for results",
             "Agent payloads can evolve without a migration",
             "Cannot query inside a result without reading it"],
            ["Single production image",
             "Same-origin, one deployment, one cold start",
             "Interface and API cannot scale independently"],
            ["In-process rate limiting",
             "No extra service on a single-container deployment",
             "Does not survive horizontal scaling"],
            ["Session id instead of accounts",
             "History without a password, no credentials to leak",
             "Not authentication; anyone with the id can read those journeys"],
            ["Deterministic evaluation by default",
             "Reproducible scores that can gate CI",
             "Cannot judge subjective quality without the optional judge"],
            ["Free hosting tier",
             "Zero cost, a real public deployment",
             "Cold starts, limited memory, a capped worker count"],
        ],
        caption="Every significant trade-off, and what each one cost.",
        widths=[1.5, 2.2, 2.1],
    )


# ---------------------------------------------------------------------------
def _scalability(g: Guide) -> None:
    g.h1("Scalability", page_break=True)

    g.h2("What the current shape supports")
    g.p(
        "One container, two workers, an in-process rate limiter and an in-process "
        "metrics counter. That is a correct design for a single-instance deployment "
        "and an honest one: nothing pretends to be distributed."
    )

    g.h2("What breaks first, and in what order")
    g.table(
        ["Order", "Constraint", "Symptom", "Change required"],
        [
            ["1", "Sequential specialists",
             "A full plan takes as long as the sum of its agents",
             "Run flights, hotels and weather concurrently; keep budget and itinerary "
             "after them"],
            ["2", "In-process rate limiting",
             "With two instances a client gets twice the intended allowance",
             "Move the counter to a shared store"],
            ["3", "In-process metrics",
             "Each instance reports only its own numbers",
             "Export to a metrics backend rather than the health endpoint"],
            ["4", "Free-tier memory",
             "The worker count cannot rise", "A larger instance"],
            ["5", "Database connections",
             "Pool exhaustion as instances multiply",
             "A connection pooler in front of PostgreSQL"],
            ["6", "Provider quotas",
             "Rate limits at the provider, not in this application",
             "Caching by destination and date, and provider-side quota management"],
            ["7", "One image for interface and API",
             "The interface cannot be cached at an edge independently",
             "Split the interface onto a static host or CDN"],
        ],
        caption="The scaling path, in the order the constraints actually bite.",
        widths=[0.4, 1.4, 1.9, 2.1],
    )

    g.callout(
        "important",
        "The graph itself scales without change. It is stateless between "
        "invocations - all state is in the checkpoint and the database - so any "
        "instance can resume any run. That is a consequence of ending the graph at "
        "human review rather than holding a run open.",
    )


# ---------------------------------------------------------------------------
def _performance(g: Guide) -> None:
    g.h1("Performance", page_break=True)

    g.callout(
        "warning",
        "No latency, throughput or resource benchmark has been run against this "
        "deployment. Every quantity below that would require measurement is recorded "
        "as \"Not measured yet\". This document does not estimate numbers it has not "
        "observed.",
    )

    g.table(
        ["Quantity", "Status"],
        [
            ["End-to-end planning latency", "Not measured yet"],
            ["Per-agent execution time", "Not measured yet"],
            ["Model call latency", "Not measured yet"],
            ["Provider call latency", "Not measured yet"],
            ["Render cold-start time", "Not measured yet"],
            ["Neon cold-start time", "Not measured yet"],
            ["Requests per second sustained", "Not measured yet"],
            ["Container memory at steady state", "Not measured yet"],
            ["Production image size", "Not measured yet"],
        ],
        caption="Performance quantities and their measurement status.",
        widths=[2.9, 2.9],
    )

    g.h2("What is known without measurement")
    g.bullets([
        "The specialists run sequentially, so a full plan cannot be faster than the "
        "sum of the agents it selects.",
        "A weather-only request runs one agent rather than five, which is the "
        "supervisor's main performance contribution.",
        "A revision runs only the affected agents - typically three of five for a "
        "hotel change - rather than replanning.",
        "The health endpoint performs no I/O, so its latency is independent of every "
        "external dependency.",
        "The budget agent makes no network or model call at all.",
    ])

    g.h2("Where to measure first")
    g.numbered([
        "Per-node duration in LangSmith, which is already traced and requires no new "
        "code.",
        "The metrics snapshot on the verbose health endpoint, for call counts and "
        "failure counts.",
        "Provider latency, recorded as latency_ms on every ToolCallResult and already "
        "flowing into provider_status.",
    ])


# ---------------------------------------------------------------------------
def _cost(g: Guide) -> None:
    g.h1("Cost", page_break=True)

    g.table(
        ["Component", "Tier", "Cost"],
        [
            ["GitHub", "Free for public repositories", "None"],
            ["GitHub Actions", "Free minutes for public repositories", "None"],
            ["Render web service", "Free", "None, with sleep-when-idle"],
            ["Neon PostgreSQL", "Free", "None, with compute scaling to zero"],
            ["LangSmith", "Free tier", "None within the free trace allowance"],
            ["Groq", "Depends on the account", "Usage-based"],
            ["Tavily, AviationStack, OpenWeather", "Free tiers available",
             "Usage-based beyond the free allowance"],
        ],
        caption="The cost model. Provider spend depends on the account and usage; no "
                "figure is asserted here.",
        widths=[1.9, 1.9, 2.0],
    )

    g.h2("The controls that bound spend")
    g.bullets([
        "The supervisor runs only the agents a request needs, so a weather question "
        "does not cost a full plan.",
        "Revisions re-run only affected agents.",
        "MAX_REVISION_COUNT caps how many times a journey can be revised.",
        "Per-tool call budgets cap provider calls within a single run.",
        "Off-topic and injected requests are refused before any agent runs, so they "
        "cost nothing.",
        "Routing, budgeting and evaluation are deterministic, so none of them spends "
        "model tokens.",
        "The deterministic mode runs the whole system with no model key at all, which "
        "is what CI uses.",
    ])


# ---------------------------------------------------------------------------
def _failure_modes(g: Guide) -> None:
    g.h1("Failure Modes", page_break=True)
    g.table(
        ["Failure", "Detected by", "Effect", "Recovery"],
        [
            ["Model provider outage", "The LLM service",
             "Deterministic mode; structured results without model-composed prose",
             "Automatic when the provider returns"],
            ["Travel provider outage", "The MCP client",
             "ESTIMATE or UNAVAILABLE labels on the affected section",
             "Automatic; the next run uses live data"],
            ["Provider quota exhausted", "The MCP client",
             "Same as an outage, plus a PROVIDER_FAILURE audit event",
             "Wait for the quota window, or raise the plan"],
            ["Tool budget exhausted", "The Tool Guard",
             "Further calls to that tool refused this run",
             "The next run starts with a fresh budget"],
            ["Prompt injection attempt", "The injection classifier",
             "The request is refused with a reason code before any agent runs",
             "None needed"],
            ["Personal data submitted", "The PII guard",
             "Redacted before the model, before the tools and before storage",
             "None needed"],
            ["Output contains a secret", "The output guard",
             "Blocking failure and an audit event",
             "Investigate - this indicates a defect upstream"],
            ["Database unreachable at start-up", "The lifespan handler",
             "Start-up fails", "Fix connectivity and redeploy"],
            ["Migration fails", "The entrypoint",
             "The server never binds a port; the deployment fails",
             "Fix the migration and redeploy"],
            ["Neon cold start", "The connection pool",
             "The first request is slow", "Automatic; pre-ping avoids a dead "
             "connection"],
            ["Render cold start", "The platform",
             "The first request after idle is slow", "Automatic"],
            ["LangSmith unreachable", "The tracing seam",
             "No trace; the journey completes normally", "Automatic"],
            ["Revision limit reached", "The review service",
             "No further changes accepted; the traveller can approve or start again",
             "Start a new journey"],
            ["Frontend build missing in the image", "`mount_frontend()`",
             "The API runs alone rather than failing to start",
             "Rebuild the image"],
        ],
        caption="Every identified failure mode, how it is detected, and what happens.",
        widths=[1.3, 1.2, 2.0, 1.5],
        size=8.5,
    )

    g.understand([
        "Why each of the thirteen decisions was made and what the alternative cost.",
        "Which constraint breaks first as load rises, and what fixes it.",
        "Why this document refuses to state a latency figure.",
        "Which controls bound the system's spend.",
        "What happens to a journey when each external dependency fails.",
    ])
