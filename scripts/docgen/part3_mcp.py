"""Model Context Protocol, transports, the tool registry and the Tool Guard."""

from __future__ import annotations

from docgen.builder import Guide


def write(g: Guide) -> None:
    _mcp_fundamentals(g)
    _mcp_in_journeymesh(g)
    _tool_guard(g)


# ---------------------------------------------------------------------------
def _mcp_fundamentals(g: Guide) -> None:
    g.h1("The Model Context Protocol", page_break=True)

    g.h2("The problem MCP solves")
    g.p(
        "An agent is only as useful as the things it can reach. Before MCP, every "
        "integration was bespoke: one HTTP client for the weather provider, another "
        "for the flight provider, a hand-written JSON schema for each function the "
        "model was allowed to call, and a different error shape from each. Adding a "
        "provider meant touching agent code. Swapping a provider meant rewriting it."
    )
    g.definition(
        "Model Context Protocol",
        "An open protocol that standardises how an application exposes tools, "
        "resources and prompts to a language model. Servers advertise capabilities "
        "with typed schemas; clients discover and invoke them over a defined "
        "transport; the message format is the same regardless of what the tool "
        "actually does.",
        "A universal adapter for AI tools. Instead of a different cable for every "
        "device, everything speaks one shape - so a new tool plugs in without "
        "rewiring the application.",
    )

    g.h2("Host, client and server")
    g.table(
        ["Role", "Responsibility", "In JourneyMesh"],
        [
            ["Host",
             "The application that owns the conversation and decides what a model is "
             "allowed to do",
             "The FastAPI application and the LangGraph workflow"],
            ["Client",
             "Maintains connections to servers, discovers their tools, and invokes "
             "them on behalf of the host",
             "`backend/app/mcp/client.py`"],
            ["Server",
             "Exposes a set of tools with typed argument schemas and returns "
             "structured results",
             "`aviation.py`, `search.py`, `weather_server.py`"],
        ],
        caption="The three MCP roles and their JourneyMesh implementations.",
        widths=[0.9, 3.0, 2.2],
    )

    g.diagram(
        """
+-------------------------------------------------------------+
|  HOST   FastAPI + LangGraph                                  |
|         decides what may be called and when                  |
|                                                              |
|   +------------------------------------------------------+  |
|   |  TOOL GUARD    deny-by-default authorization          |  |
|   +--------------------------|---------------------------+  |
|                              v                              |
|   +------------------------------------------------------+  |
|   |  CLIENT   app/mcp/client.py                           |  |
|   |  chooses transport, invokes, normalises, records      |  |
|   +---+----------------+-------------------+--------------+  |
+-------|----------------|-------------------|-----------------+
        |                |                   |
   stdio / HTTP     stdio / HTTP        stdio / HTTP
   / in-process     / in-process        / in-process
        |                |                   |
        v                v                   v
+---------------+ +---------------+ +------------------+
| SERVER        | | SERVER        | | SERVER           |
| aviation.py   | | search.py     | | weather_server.py|
| search_flights| | search_hotels | | get_current_...  |
| lookup_airport| | web_search    | | get_..._forecast |
+---------------+ +---------------+ +------------------+
        |                |                   |
        v                v                   v
   AviationStack       Tavily            OpenWeather
""",
        "The MCP host-client-server arrangement in JourneyMesh, with the Tool Guard "
        "sitting between the host and the client.",
    )

    g.h2("Transports")
    g.table(
        ["Transport", "How it works", "Best for", "Used here"],
        [
            ["stdio",
             "The client launches the server as a subprocess and exchanges JSON-RPC "
             "over standard input and output",
             "Local tools, development, anything that should not be on a network",
             "Yes, when a server is configured with the stdio transport"],
            ["Streamable HTTP",
             "The client posts JSON-RPC to a URL and reads a streamed response",
             "Remote or shared servers, servers that outlive one process",
             "Yes, when MCP_*_URL is configured"],
            ["In-process adapter",
             "The tool function is called directly in the same Python process, with "
             "the same argument schema and the same result shape",
             "Tests, offline evaluation, and any deployment where a provider is "
             "not configured",
             "Yes - this is the default fallback"],
        ],
        caption="The three transports and when each is used.",
        widths=[1.0, 2.4, 1.7, 1.6],
    )
    g.callout(
        "important",
        "The in-process adapter is not a mock. It runs the same tool function with the "
        "same schema validation and returns the same result shape; only the transport "
        "differs. That is what lets the test suite and the offline evaluation exercise "
        "the real tool path without a network or a subprocess.",
    )

    g.h2("MCP versus calling the API directly")
    g.table(
        ["Concern", "Direct HTTP call from the agent", "Through MCP"],
        [
            ["Argument validation",
             "Written by hand in each agent, or not at all",
             "Declared once in the tool's schema and checked before dispatch"],
            ["Authorization",
             "Nothing to hook into - the agent already holds the client",
             "One choke point the guard can sit in front of"],
            ["Swapping a provider",
             "Change agent code",
             "Change a server; agents are untouched"],
            ["Error shape",
             "Different per provider",
             "Normalised into one result type with a provenance label"],
            ["Observability",
             "Each agent must instrument its own calls",
             "The client records every call, its latency and its outcome"],
            ["Cost",
             "Fewer moving parts, less indirection",
             "A protocol layer to understand and operate"],
        ],
        caption="What the protocol buys, and what it costs.",
        widths=[1.1, 2.3, 2.4],
    )
    g.p(
        "The honest summary is that for a system with one provider, MCP is overhead. "
        "For a system with several providers, several agents and a hard requirement "
        "that every external call be authorised and labelled, the choke point is worth "
        "more than the indirection costs."
    )

    g.understand([
        "What problem MCP was designed to solve.",
        "The difference between host, client and server, and which files play each "
        "role here.",
        "The three transports and why the in-process adapter is not a mock.",
        "When MCP is genuinely worth its overhead and when it is not.",
    ])


# ---------------------------------------------------------------------------
def _mcp_in_journeymesh(g: Guide) -> None:
    g.h1("MCP in JourneyMesh", page_break=True)

    g.h2("The three servers, and why none of them looks the same")
    g.p(
        "The three providers are not symmetric, and the design reflects that rather "
        "than forcing a uniform shape onto them. What each provider *is* decides how "
        "it is reached."
    )
    g.table(
        ["Server", "Transport", "Where it runs", "In-process fallback"],
        [
            ["Search", "`streamable_http`",
             "Tavily hosts it. There is nothing to install and nothing to launch.",
             "`app/mcp/search.py`"],
            ["Aviation", "`stdio`",
             "A third-party package, launched as a subprocess through `uv`.",
             "`app/mcp/aviation.py`"],
            ["Weather", "`stdio`",
             "Ours. `app/mcp/weather_server.py`, started by the application itself.",
             "the same module, called directly"],
        ],
        caption="The three MCP servers. Every one keeps a local implementation "
                "behind it, so an unreachable server degrades rather than fails.",
        widths=[0.8, 1.3, 2.4, 1.7],
    )
    g.p(
        "The weather server is the honest demonstration of the pattern: the same code "
        "is reachable in-process and over MCP, and swapping transports changes nothing "
        "an agent can observe."
    )

    g.h2("Configuration: MCP preferred, degradation automatic")
    g.p(
        "Every transport variable defaults to `auto`, which means: use MCP when this "
        "deployment can actually reach a server, and fall back to the local "
        "implementation when it cannot. That is what makes MCP the preferred provider "
        "without turning a missing API key into a startup failure - or, worse, into a "
        "server that claims to be enabled and fails on every call."
    )
    g.table(
        ["Value", "Meaning"],
        [
            ["`auto`", "Decide per server, from what is actually available. The default."],
            ["`stdio`", "Launch a local MCP server as a child process."],
            ["`streamable_http`", "Call a remote MCP server. `http` and "
             "`streamable-http` are accepted spellings."],
            ["`disabled`", "Never use MCP for this provider."],
        ],
        caption="The four values `MCP_*_TRANSPORT` accepts. Anything unrecognised is "
                "read as `disabled`, and the health endpoint reports why.",
        widths=[1.3, 4.5],
    )
    g.table(
        ["Provider", "`auto` resolves to", "Condition"],
        [
            ["Search", "`streamable_http`",
             "`TAVILY_API_KEY` is set. The endpoint URL is built by the application."],
            ["Aviation", "`stdio`",
             "An AviationStack key is set AND the MCP server is installed. It is "
             "pre-installed in the Docker image."],
            ["Weather", "`stdio`",
             "Always. The server ships inside the image and answers with labelled "
             "ESTIMATE data even without an API key."],
        ],
        caption="What `auto` decides, per server. `app/mcp/config.py` performs this "
                "resolution and records a human-readable reason when a server is "
                "not usable.",
        widths=[1.0, 1.5, 3.3],
    )
    g.callout(
        "note",
        "Neither `MCP_SEARCH_URL` nor the Tavily key has to be written twice. Tavily "
        "authenticates by query parameter, so the endpoint URL is itself a "
        "credential; the application builds it at use time from `TAVILY_API_KEY` "
        "alone. Setting `MCP_SEARCH_URL` is only for someone pointing at a "
        "self-hosted server.",
    )

    g.h2("How a tool call actually travels")
    g.diagram(
        """
 hotel_agent wants hotels under $100/night in Singapore
        |
        v
 client.call_tool(tool="search_hotels", agent="hotel_agent", arguments={...})
        |
        +--> ToolGuard.authorize(...)
        |       tool in TOOL_POLICIES?              deny by default if not
        |       policy["enabled"]?                  disabled tools are refused
        |       agent in policy["allowed_agents"]?  wrong agent -> refused
        |       arguments match argument_schema?    type, required, bounds
        |       any FORBIDDEN_ARGUMENT_KEYS?        stripped and recorded
        |       PII in the arguments?               redacted before dispatch
        |       operation in AUTONOMOUS_OPERATIONS? write/destructive -> refused
        |       call count < max_calls_per_run?     budget exhausted -> refused
        |
        +--> allowed: ToolDecision(allowed=True, sanitized_arguments={...})
        |
        v
 registry.resolve("search_hotels") -> the search server
        |
        +--> providers/<server> adapter translates our tool name and
        |    arguments into that server's own vocabulary
        |       ...or declines, when there is no faithful equivalent
        |
        +-- streamable_http -> HTTPS JSON-RPC session
        +-- stdio           -> subprocess JSON-RPC (managed or per call)
        +-- disabled        -> in-process adapter
        |
        v
 ToolCallResult(ok=..., data=..., latency_ms=..., transport=...)
        |
        +--> provider_status entry with a canonical provenance label
        +--> metrics counter, audit event on failure
        |
        v
 hotel_agent normalises the payload into hotel_results
""",
        "One tool call from intent to normalised result.",
    )

    g.h2("Why the client re-checks with the guard")
    g.p(
        "Authorization already happened before the client was reached. The client "
        "checks again anyway. This is defence in depth: the guard is the security "
        "boundary, and a security boundary that can be bypassed by adding one new call "
        "site is not a boundary. Re-checking costs a dictionary lookup and removes a "
        "whole class of future mistake."
    )

    g.h2("Normalising failure")
    g.p(
        "Every tool call returns a ToolCallResult whether it succeeded or not. A "
        "provider timeout, a 500, a malformed payload and a missing API key all become "
        "the same shape: ok=False, an error string, a latency measurement and a "
        "provenance label. Any source the client does not recognise is coerced to "
        "UNAVAILABLE rather than being passed through, so an unexpected label from a "
        "provider cannot propagate into the response schema."
    )
    g.callout(
        "note",
        "That coercion exists because of a real defect found during development: an "
        "internal fallback returned the source 'reference_table', which was not one of "
        "the four canonical labels, and the response model rejected it. The fix was to "
        "make the client the one place where a label is canonicalised.",
    )

    g.h2("The adapter layer: whose vocabulary wins")
    g.p(
        "A remote MCP server is somebody else's contract. Its tool is not called what "
        "our tool is called, its arguments are not our arguments, and its response is "
        "not our schema. Tavily's search tool is `tavily_search`; AviationStack "
        "exposes twelve tools, none of them shaped like a JourneyMesh flight lookup."
    )
    g.p(
        "Something has to translate, and it must not be the agent. `app/mcp/providers/` "
        "holds one adapter per server, so `weather_agent` asks for a forecast and "
        "receives a forecast without knowing that a subprocess was started or that a "
        "vendor names its tool differently."
    )
    g.p(
        "An adapter may also **decline**. Returning nothing means 'this tool has no "
        "faithful remote equivalent', and the call goes to the local implementation "
        "instead. Two tools decline on purpose:"
    )
    g.bullets([
        "`search_hotels` does more than search: it bands prices by travel style and "
        "builds the candidate records the budget agent reads. A raw list of web "
        "results cannot substitute without inventing nightly rates.",
        "`search_flights` produces priced options, and AviationStack's route endpoint "
        "carries no fares at all. Assembling one from the other would mean inventing "
        "the number a traveller is most likely to act on.",
    ])
    g.callout(
        "important",
        "Declining is better than guessing. A plausible-looking price assembled from "
        "the wrong endpoint is worse than an honest estimate, and the provenance "
        "label tells the traveller which one they actually got. This is why the "
        "health endpoint can report a server as reachable while some of its tools "
        "still answer locally - that is correct behaviour, not degradation.",
    )

    g.h2("Starting the local servers")
    g.p(
        "A `stdio` server is a child process, and somebody has to start it. Nobody "
        "should have to run `python -m app.mcp.weather_server` in a second terminal, "
        "so the application does it."
    )
    g.p(
        "FastAPI's lifespan starts the weather server at boot, keeps the session warm, "
        "restarts it if it dies, and terminates it on shutdown. The same code path "
        "runs under `uvicorn app.main:app --reload` locally and `docker compose up -d` "
        "in production: no systemd unit, no extra container, no published port, no "
        "terminal left open. It is launched with `sys.executable`, so the interpreter "
        "is always the one running the application - never `python3`, never a Conda "
        "path, never an absolute path baked in for one machine."
    )
    g.table(
        ["Strategy", "Used by", "Why"],
        [
            ["Managed", "Weather",
             "Ours, shipped in the image, called on nearly every journey. Paying a "
             "subprocess start per call would be several hundred milliseconds for "
             "nothing."],
            ["Per call", "Aviation, and every fallback",
             "A third-party server should not hold a process open for the life of the "
             "application. Also what tests use, and what probes use so they never "
             "disturb live traffic."],
        ],
        caption="Two session strategies. Either way the child is reaped: "
                "`stdio_client` is an async context manager that terminates the "
                "process on exit, and the managed path holds it in an "
                "`AsyncExitStack` the lifespan unwinds.",
        widths=[1.0, 1.6, 3.2],
    )

    g.h2("What a child process is allowed to see")
    g.p(
        "The MCP SDK deliberately does not inherit the parent environment. With "
        "`env=None` a child receives only HOME and PATH. That default is right - a "
        "subprocess has no business seeing the database password - but taken literally "
        "it means the weather server starts with no `OPENWEATHER_API_KEY` and silently "
        "produces estimates, which reads as a broken provider rather than a "
        "configuration gap."
    )
    g.p(
        "`stdio_child_environment()` therefore builds the child environment "
        "explicitly: the SDK's safe default, plus the variables a launcher needs, plus "
        "an **allowlist** of provider credentials, plus whatever that server's own "
        "configuration declares. `DATABASE_URL`, `LANGSMITH_API_KEY` and "
        "`GROQ_API_KEY` are not on the list and do not travel. A test asserts it."
    )

    g.h2("Why the search URL is treated as a secret")
    g.p(
        "Tavily takes its API key as a query parameter, which makes the endpoint URL "
        "itself a credential. That one fact drives the whole of `app/mcp/security.py`."
    )
    g.bullets([
        "`redact_url` masks any credential-shaped query parameter by name, so a "
        "logged endpoint reads `?tavilyApiKey=***` and stays useful for debugging.",
        "`safe_error` runs every MCP exception through that redaction before it "
        "reaches a log line, a trace, or an API response - SDK errors routinely quote "
        "the URL they failed on.",
        "`MCPServerConfig.describe()` redacts before anything is returned by an "
        "endpoint, so the health output can report `url_configured: true` without "
        "ever showing the URL.",
    ])
    g.p(
        "Tests assert that a configured Tavily key appears in none of the verbose "
        "health output, the MCP probe, or an error message."
    )

    g.h2("Asking what is actually working")
    g.p(
        "The health endpoint answers two different questions that cost very different "
        "amounts. `GET /api/v1/health?verbose=true` reports configuration: it reads "
        "settings and starts nothing. `GET /api/v1/health/mcp?probe=true` genuinely "
        "connects to each server and lists its tools, which means starting a "
        "subprocess or opening an HTTPS session, so it is opt-in and bounded by a "
        "timeout."
    )
    g.p(
        "Every server is probed independently and concurrently, with exceptions "
        "captured per server. One provider timing out cannot cancel or mask the state "
        "of another - the isolation the whole MCP layer is built around."
    )
    g.code(
        """
{
  "search":   {"enabled": true,  "transport": "streamable_http",
               "url": "https://mcp.tavily.com/mcp/?tavilyApiKey=***",
               "reachable": true,  "tools": ["tavily_search", ...]},
  "aviation": {"enabled": true,  "transport": "stdio",
               "reachable": false, "error": "sanitized error"},
  "weather":  {"enabled": true,  "transport": "stdio",
               "reachable": true,  "tools": ["current_weather", "weather_forecast"]}
}
""",
        caption="Listing. A probe response. No key, no authorization header, no "
                "environment dictionary - by construction, not by convention.",
    )

    g.understand([
        "Which three servers exist, why each uses a different transport, and which "
        "providers they front.",
        "What `auto` resolves to per server, and why a missing key degrades instead "
        "of failing.",
        "Why an adapter is allowed to decline, and what that means for a price.",
        "How the weather subprocess is started, supervised and terminated by the "
        "application itself.",
        "Why a child process gets an allowlist rather than the parent environment.",
        "Why the Tavily endpoint URL is a credential, and the three places it is "
        "redacted.",
        "The difference between reporting configuration and actually probing.",
        "The order of checks between an agent's intent and the provider being called.",
        "Why the client re-authorises something that was already authorised.",
    ])


# ---------------------------------------------------------------------------
def _tool_guard(g: Guide) -> None:
    g.h1("The MCP Tool Guard", page_break=True)

    g.p(
        "The Tool Guard answers one question - may this agent call this tool with "
        "these arguments right now? - and it answers 'no' unless every condition is "
        "met. It is the single most security-relevant component in the system, because "
        "it is the boundary between a model's suggestion and an action in the world."
    )

    g.h2("Deny by default")
    g.definition(
        "Deny by default",
        "An authorization posture in which the absence of an explicit permission is a "
        "denial, rather than the absence of an explicit prohibition being a "
        "permission.",
        "Nothing is allowed unless it is on the list. Forgetting to add a rule makes "
        "the system refuse, not comply.",
    )
    g.p(
        "A tool that is not in TOOL_POLICIES cannot be called, no matter who asks. "
        "This matters more than it sounds: it means a model that invents a tool name, "
        "a prompt injection that names a plausible-sounding tool, and a developer who "
        "adds a tool function but forgets the policy all produce the same outcome - a "
        "refusal and an audit event."
    )

    g.h2("The seven checks")
    g.table(
        ["#", "Check", "Fails when", "Consequence"],
        [
            ["1", "Registration",
             "The tool is absent from TOOL_POLICIES", "Denied"],
            ["2", "Enablement",
             "policy['enabled'] is false", "Denied"],
            ["3", "Agent authorization",
             "The calling agent is not in allowed_agents", "Denied"],
            ["4", "Argument schema",
             "A required argument is missing, a type is wrong, a string is too long "
             "or a number is out of bounds", "Denied"],
            ["5", "Forbidden keys",
             "An argument key is in FORBIDDEN_ARGUMENT_KEYS", "Stripped and recorded"],
            ["6", "Operation class",
             "The operation is write or destructive and no human has confirmed",
             "Denied"],
            ["7", "Call budget",
             "The tool has already been called max_calls_per_run times this run",
             "Denied"],
        ],
        caption="The checks the guard performs, in order.",
        widths=[0.3, 1.3, 2.5, 1.4],
    )

    g.h2("Operation classes")
    g.p(
        "Every tool declares an operation class. JourneyMesh performs read and search "
        "operations autonomously; write and destructive operations always require "
        "human confirmation and are shipped disabled. Booking a flight and cancelling "
        "a reservation are declared in the policy table precisely so that the "
        "authorization surface is visible and reviewable, not because they are wired "
        "to anything."
    )
    g.table(
        ["Operation", "Meaning", "Autonomous?", "Tools"],
        [
            ["`read`", "Fetches a fact and changes nothing", "Yes",
             "`lookup_airport`, `get_current_weather`, `get_weather_forecast`"],
            ["`search`", "Queries a corpus and changes nothing", "Yes",
             "`search_flights`, `search_hotels`, `web_search`"],
            ["`write`", "Creates or modifies external state", "No - disabled",
             "`book_flight`, `book_hotel`"],
            ["`destructive`", "Removes external state", "No - disabled",
             "`cancel_reservation`"],
        ],
        caption="Operation classes and the tools in each.",
        widths=[0.9, 1.9, 1.1, 2.1],
    )

    g.h2("The full policy table")
    g.table(
        ["Tool", "Agents", "Operation", "Risk", "Budget", "Enabled"],
        [
            ["`search_flights`", "flight", "search", "low", "4", "Yes"],
            ["`lookup_airport`", "flight", "read", "low", "8", "Yes"],
            ["`search_hotels`", "hotel", "search", "low", "4", "Yes"],
            ["`web_search`", "hotel, itinerary", "search", "low", "6", "Yes"],
            ["`get_current_weather`", "weather", "read", "low", "3", "Yes"],
            ["`get_weather_forecast`", "weather", "read", "low", "3", "Yes"],
            ["`book_flight`", "flight", "write", "high", "-", "No"],
            ["`book_hotel`", "hotel", "write", "high", "-", "No"],
            ["`cancel_reservation`", "flight, hotel", "destructive", "high", "-",
             "No"],
        ],
        caption="TOOL_POLICIES in full, from app/guardrails/policies.py.",
        widths=[1.6, 1.3, 0.9, 0.6, 0.6, 0.7],
    )

    g.h2("Per-run call budgets")
    g.p(
        "max_calls_per_run bounds how many times one tool may be invoked within a "
        "single graph run. It is a cost control and a loop breaker. Without it, an "
        "agent that retried on an unhelpful result could burn an entire provider quota "
        "on one request; with it, the eighth airport lookup is refused and the agent "
        "proceeds with what it has."
    )

    g.h2("Forbidden argument keys")
    g.p(
        "Some argument names must never leave the process regardless of what a model "
        "produced. The guard strips them and records the redaction on the decision, so "
        "the fact that something was removed is visible in the audit trail without the "
        "value itself ever being logged."
    )
    g.code(
        """
FORBIDDEN_ARGUMENT_KEYS = frozenset(
    {
        "api_key", "apikey", "token", "authorization", "password", "secret",
        "passport", "passport_number", "national_id",
        "credit_card", "card_number", "cvv",
        "database_url",
    }
)
""",
        caption="Listing. Argument names that are stripped before any tool is called.",
    )

    g.h2("The decision record")
    g.p(
        "Every authorization produces a ToolDecision, and every decision is appended "
        "to state['guardrail_results'] as a dictionary. The record names the tool, the "
        "agent, the outcome, the rule that decided it, the operation class, the risk "
        "level and any redactions - but never an argument value. That is the audit "
        "trail: enough to reconstruct why something was refused, with nothing "
        "sensitive in it."
    )

    g.callout(
        "warning",
        "The guard is stateful for the duration of a run because call budgets are "
        "counted per run. A guard instance must therefore not be shared between "
        "concurrent runs; the workflow constructs it per run for exactly this reason.",
    )

    g.understand([
        "Why deny-by-default changes what a forgotten rule does.",
        "The seven checks and the order they run in.",
        "Why booking and cancellation tools are declared but disabled.",
        "What a per-run call budget protects against.",
        "Why the decision record contains rules and redaction names but never "
        "argument values.",
    ])
