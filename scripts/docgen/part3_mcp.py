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
             "Tests, offline evaluation, and free-tier hosting where a subprocess is "
             "not affordable",
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

    g.h2("The three servers")
    g.table(
        ["Server", "File", "Tools", "Upstream provider"],
        [
            ["Aviation", "`app/mcp/aviation.py`",
             "`search_flights`, `lookup_airport`",
             "AviationStack, plus a reference table fallback"],
            ["Search", "`app/mcp/search.py`",
             "`search_hotels`, `web_search`",
             "Tavily"],
            ["Weather", "`app/mcp/weather_server.py`",
             "`get_current_weather`, `get_weather_forecast`",
             "OpenWeather"],
        ],
        caption="The MCP servers shipped with JourneyMesh.",
        widths=[0.9, 1.6, 1.9, 1.8],
    )

    g.h2("Configuration")
    g.p(
        "Each server is configured by a transport variable and an optional URL. "
        "Setting the transport to 'disabled' is a supported, first-class state: the "
        "client falls back to the in-process adapter and the system keeps working, "
        "which is exactly the configuration used on the free hosting tier."
    )
    g.table(
        ["Variable", "Values", "Effect"],
        [
            ["`MCP_AVIATION_TRANSPORT`", "stdio, http, disabled",
             "How the aviation server is reached"],
            ["`MCP_AVIATION_URL`", "A URL, or empty",
             "Required only for the http transport"],
            ["`MCP_SEARCH_TRANSPORT`", "stdio, http, disabled", "As above"],
            ["`MCP_SEARCH_URL`", "A URL, or empty", "As above"],
            ["`MCP_WEATHER_TRANSPORT`", "stdio, http, disabled", "As above"],
            ["`MCP_WEATHER_URL`", "A URL, or empty", "As above"],
        ],
        caption="MCP configuration, from backend/.env.example. Every value ships "
                "empty or 'disabled'; nothing here is a secret.",
        widths=[1.7, 1.6, 2.5],
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
        +-- transport = http      -> streamable HTTP JSON-RPC
        +-- transport = stdio     -> subprocess JSON-RPC
        +-- transport = disabled  -> in-process adapter
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

    g.understand([
        "Which three servers exist, which tools they expose and which providers they "
        "front.",
        "What 'disabled' means as a transport and why it is a supported state.",
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
