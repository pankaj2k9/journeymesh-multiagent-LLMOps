"""Agentic AI, LangGraph, the shared state, the supervisor and the specialists."""

from __future__ import annotations

from docgen.builder import Guide


def write(g: Guide) -> None:
    _agentic_ai(g)
    _langgraph(g)
    _journeymesh_graph(g)
    _state(g)
    _supervisor(g)
    _specialists(g)


# ---------------------------------------------------------------------------
def _agentic_ai(g: Guide) -> None:
    g.h1("Agentic AI from First Principles", page_break=True)

    g.h2("What an agent is")
    g.definition(
        "Agent",
        "A software component that is given a goal rather than a procedure, that "
        "chooses which actions to take to reach that goal, that can invoke tools to "
        "affect or observe the world outside itself, and that decides for itself when "
        "the goal has been met.",
        "A junior colleague you brief instead of instruct. You say what you want, "
        "they work out the steps, look things up, and come back when they are done.",
    )
    g.p(
        "The word is used loosely in industry, so it helps to name what an agent is "
        "not. A single prompt with a long instruction is not an agent - it has no "
        "actions. A script that calls a model three times in a fixed order is not an "
        "agent either - the order was decided by the programmer, not by the system. "
        "The defining property is that some part of the control flow is decided at "
        "run time from the content of the request."
    )

    g.h2("Single agent, multi-agent, and why JourneyMesh is the second")
    g.table(
        ["Shape", "How it works", "Strengths", "Weaknesses"],
        [
            ["Single prompt",
             "One model call with all instructions",
             "Simplest, cheapest, lowest latency",
             "One long prompt has to be good at everything; no way to re-run part of "
             "the answer; hallucinated facts are indistinguishable from real ones"],
            ["Single agent with tools",
             "One model in a loop, choosing tools until it stops",
             "Flexible; one place to reason about",
             "Loops can run away; the model owns both domain reasoning and control "
             "flow, so a bad routing decision corrupts the whole answer"],
            ["Multi-agent, supervised",
             "A supervisor selects specialists; each specialist owns one domain and "
             "one slice of state",
             "Each prompt is small and testable; partial re-execution is possible; "
             "failures are contained to one domain",
             "More moving parts; the supervisor becomes a critical component; state "
             "design has to be explicit"],
            ["Multi-agent, autonomous",
             "Agents converse with each other and negotiate",
             "Can handle open-ended problems",
             "Non-deterministic, hard to bound in cost, very hard to test"],
        ],
        caption="Agent architectures, and the trade that JourneyMesh accepts.",
        widths=[1.1, 1.8, 1.6, 2.3],
    )
    g.p(
        "JourneyMesh is the third row. Travel planning decomposes cleanly into "
        "domains that have different sources of truth - an airline schedule, a hotel "
        "listing, a forecast, arithmetic, and a plan - and the value of the system is "
        "in coordinating them, not in one very clever prompt. The fourth row was "
        "rejected deliberately: agents that talk to each other cannot be bounded in "
        "cost and cannot be tested case by case."
    )

    g.h2("The vocabulary used throughout this guide")
    g.table(
        ["Term", "Meaning in JourneyMesh"],
        [
            ["Supervisor", "The agent that decides which specialists run. It never "
                           "plans a trip itself."],
            ["Specialist", "One of flight, hotel, weather, budget or itinerary. Owns "
                           "exactly one key of the shared state."],
            ["State", "TravelState - the single dictionary every node reads from and "
                      "writes to."],
            ["Node", "One step in the LangGraph workflow. Takes a state, returns a "
                     "state."],
            ["Edge", "A declared transition between nodes. Conditional edges choose "
                     "at run time."],
            ["Tool", "A named, schema-checked capability reached through MCP - "
                     "search_flights, get_weather_forecast and so on."],
            ["Checkpoint", "A persisted snapshot of the state, keyed by thread, that "
                           "lets a run pause and resume."],
            ["Provenance label", "LIVE, SEARCH_DERIVED, ESTIMATE or UNAVAILABLE - how "
                                 "a given number was obtained."],
        ],
        caption="Core vocabulary.",
        widths=[1.2, 4.6],
    )

    g.understand([
        "What distinguishes an agent from a prompt and from a fixed script.",
        "Why travel planning suits a supervised multi-agent shape.",
        "Why fully autonomous agent-to-agent negotiation was rejected here.",
        "What supervisor, specialist, state, node, edge, tool and checkpoint mean in "
        "this codebase.",
    ])


# ---------------------------------------------------------------------------
def _langgraph(g: Guide) -> None:
    g.h1("LangGraph", page_break=True)

    g.h2("What LangGraph is and why it exists")
    g.definition(
        "LangGraph",
        "A library for expressing an application as a directed graph of nodes over a "
        "shared, typed state, with conditional edges, persistence of state at each "
        "step, and the ability to interrupt and resume a run.",
        "A flowchart you can actually execute, that remembers where it got to. Boxes "
        "are functions, arrows are decisions, and the whole thing can be paused and "
        "picked up later.",
    )
    g.p(
        "Before LangGraph the usual way to build a multi-step LLM application was a "
        "chain: a fixed sequence of calls. Chains cannot loop, cannot branch on "
        "content, and cannot stop halfway and wait for a human. LangGraph replaces the "
        "sequence with a state machine, and that is exactly what a review-and-revise "
        "workflow needs."
    )

    g.h2("The four concepts you need")
    g.table(
        ["Concept", "In LangGraph", "In JourneyMesh"],
        [
            ["State",
             "A TypedDict describing every field the graph carries. Nodes return "
             "partial updates that are merged in.",
             "`TravelState` in `app/graph/state.py`"],
            ["Node",
             "An async or sync callable taking the state and returning a state.",
             "Seven nodes: supervisor, supervisor_revision, specialists, output_guard, "
             "evaluation, human_review, final_response"],
            ["Edge",
             "A declared transition. `add_edge` is unconditional; "
             "`add_conditional_edges` calls a router function at run time.",
             "One conditional edge from START; the rest are straight edges"],
            ["Checkpointer",
             "A pluggable store that persists the state after every node, keyed by a "
             "thread id.",
             "`MemorySaver` locally, `PostgresSaver` when a PostgreSQL URL is present"],
        ],
        caption="LangGraph concepts and where they appear in this repository.",
        widths=[1.0, 2.7, 2.1],
    )

    g.h2("A minimal LangGraph, then the real one")
    g.code(
        """
from typing import TypedDict
from langgraph.graph import END, START, StateGraph


class Counter(TypedDict, total=False):
    value: int


def increment(state: Counter) -> Counter:
    state["value"] = state.get("value", 0) + 1
    return state


builder = StateGraph(Counter)
builder.add_node("increment", increment)
builder.add_edge(START, "increment")
builder.add_edge("increment", END)
graph = builder.compile()

graph.invoke({"value": 0})     # -> {"value": 1}
""",
        caption="Listing. The smallest complete LangGraph. Everything in JourneyMesh "
                "is this shape with more nodes and a router.",
    )

    g.h2("Conditional edges")
    g.p(
        "A conditional edge is the mechanism that lets the content of a request decide "
        "the path. `add_conditional_edges` takes a source node, a router function, and "
        "a mapping from the router's return value to a destination node. The router is "
        "an ordinary function of the state: it can be unit-tested with a dictionary "
        "and no model, which is why JourneyMesh keeps all of its routing logic in "
        "plain Python rather than asking a model to choose the next node."
    )
    g.code(
        """
# backend/app/graph/travel_graph.py

builder.add_conditional_edges(
    START,
    entry_router,
    {
        ENTRY_PLAN: "supervisor",
        ENTRY_REVISE: "supervisor_revision",
        ENTRY_FINALISE: "final_response",
    },
)
""",
        caption="Listing. The single conditional edge in the JourneyMesh graph.",
    )

    g.h2("Checkpointing")
    g.definition(
        "Checkpointer",
        "A store that serialises the graph state after each node and associates it "
        "with a thread identifier, so a run can be resumed at the node it reached "
        "even in a different process.",
        "A save point in a game. The workflow writes down everything it knows before "
        "it stops, so it can carry on later from exactly where it was.",
    )
    g.p(
        "This is why TravelState is a TypedDict of JSON-compatible values rather than "
        "a Pydantic model with rich Python objects: everything in it has to survive a "
        "round trip through the checkpoint store unchanged. JourneyMesh selects the "
        "checkpointer at construction time - an in-memory saver when there is no "
        "PostgreSQL to talk to, and the PostgreSQL saver when there is - so the same "
        "graph code runs in a test, in the local compose stack and in production."
    )

    g.callout(
        "tip",
        "In an interview, the cleanest one-line answer to \"why LangGraph and not a "
        "chain?\" is: because the workflow has to stop and wait for a human, and a "
        "chain has nowhere to stop.",
    )

    g.understand([
        "What a state, a node, an edge and a checkpointer are.",
        "Why a conditional edge is what makes the workflow content-driven.",
        "Why JourneyMesh routes in Python rather than asking a model to route.",
        "Why the state has to be JSON-compatible.",
    ])


# ---------------------------------------------------------------------------
def _journeymesh_graph(g: Guide) -> None:
    g.h1("The JourneyMesh Graph", page_break=True)

    g.h2("The seven nodes")
    g.table(
        ["Node", "Runs", "Reads", "Writes"],
        [
            ["`supervisor`", "First planning pass",
             "user_query, trip_constraints",
             "selected_agents, execution_reason"],
            ["`supervisor_revision`", "Every revision",
             "requested_changes, existing results",
             "selected_agents, change_scope, execution_reason"],
            ["`specialists`", "After either supervisor",
             "selected_agents, trip_constraints",
             "flight_results, hotel_results, weather_info, budget_analysis, "
             "itinerary_plan, agents_run, llm_calls"],
            ["`output_guard`", "After the specialists",
             "every result key, trip_constraints",
             "guardrail_results"],
            ["`evaluation`", "After the output guard",
             "the whole state",
             "evaluation_results"],
            ["`human_review`", "Last node of a draft run",
             "revision_count, evaluation_results",
             "human_review_status, trip_status"],
            ["`final_response`", "Only after approval",
             "every result key, response_language",
             "final_response, trip_status"],
        ],
        caption="Every node in the graph, and the part of the state it touches.",
        widths=[1.2, 1.3, 1.6, 2.4],
    )

    g.h2("Why the graph ends at the human review")
    g.p(
        "There is no edge from human_review back into the specialists. That looks like "
        "an omission and is in fact the central design decision. A running graph cannot "
        "wait for a person for an unbounded time: the HTTP request that started it will "
        "time out, the worker process may be recycled, and a free-tier container may be "
        "suspended between the draft and the decision. So the draft run ends. The state "
        "is checkpointed and the trip is persisted with status awaiting_review."
    )
    g.p(
        "When the traveller finally decides - a minute later or a day later - a new "
        "invocation resumes from the checkpoint and the entry router sends it down the "
        "branch that decision selects: 'revise' for a change request, 'finalise' for an "
        "approval. The pause is therefore durable rather than held open in memory, and "
        "the same mechanism works whether the two halves happen in one process or in "
        "two different containers."
    )

    g.diagram(
        """
   Draft run                         (process may end here)
   ---------                                  :
   START                                      :
     |  entry_router -> "plan"                :
     v                                        :
   supervisor                                 :
     |                                        :
     v                                        :
   specialists -> output_guard -> evaluation -> human_review -> END
                                                    |
                                            checkpoint written
                                            trip.status = awaiting_review
                                                    :
                                            ... a person decides ...
                                                    :
   Resume: approve                          Resume: request changes
   ---------------                          ----------------------
   START                                    START
     | entry_router -> "finalise"             | entry_router -> "revise"
     v                                        v
   final_response -> END                    supervisor_revision
                                              |
                                              v
                                            specialists -> output_guard
                                              -> evaluation -> human_review -> END
""",
        "The draft run, the durable pause, and the two ways a run resumes.",
    )

    g.h2("Entry routing")
    g.code(
        """
# backend/app/graph/routing.py  (behaviour)
#
#   ENTRY_FINALISE  when the review has been approved
#   ENTRY_REVISE    when requested_changes is present
#   ENTRY_PLAN      otherwise - a brand new journey
""",
        caption="Listing. The three entry branches, decided by plain Python from the "
                "state alone.",
    )

    g.h2("Why the specialists share one node")
    g.p(
        "The five specialists could have been five nodes with edges between them. They "
        "are one node containing a loop instead, for three reasons. First, the set of "
        "agents that runs is decided at run time and changes between revisions, so a "
        "static five-node subgraph would need conditional edges around every node. "
        "Second, the execution order is a fixed dependency order, so there is no "
        "routing decision to express. Third, one node means one checkpoint boundary "
        "around the whole specialist phase, which keeps the persisted state small and "
        "the trace readable."
    )
    g.callout(
        "note",
        "The trade-off accepted here is that the specialists run sequentially rather "
        "than in parallel. Flights, hotels and weather are genuinely independent and "
        "could overlap; that is recorded as a future optimisation in the decisions "
        "chapter, not as a claim about current behaviour.",
    )

    g.understand([
        "What each of the seven nodes reads and writes.",
        "Why the graph ends at human_review instead of looping back.",
        "How a resumed run picks its branch without re-planning.",
        "Why the five specialists live inside a single node.",
    ])


# ---------------------------------------------------------------------------
def _state(g: Guide) -> None:
    g.h1("TravelState - the Shared Context", page_break=True)

    g.p(
        "TravelState is the only thing the agents share. They never call each other, "
        "never hold references to each other, and never see each other's prompts. One "
        "agent's output becomes another agent's input purely because they read and "
        "write the same dictionary. That indirection is what makes selective "
        "re-execution possible at all."
    )

    g.h2("The fields")
    g.table(
        ["Group", "Field", "Type", "Meaning"],
        [
            ["Request", "`user_query`", "str", "The traveller's own words"],
            ["Request", "`trip_constraints`", "dict", "The validated structured form"],
            ["Request", "`response_language`", "str", "en, bn or hi"],
            ["Supervisor", "`selected_agents`", "list[str]", "Who will run this pass"],
            ["Supervisor", "`execution_reason`", "str",
             "Why, in words a person can read"],
            ["Supervisor", "`change_scope`", "list[str]",
             "Which domains a revision touches"],
            ["Supervisor", "`agents_run`", "list[str]", "Who actually ran"],
            ["Results", "`flight_results`", "dict", "Owned by the flight agent"],
            ["Results", "`hotel_results`", "dict", "Owned by the hotel agent"],
            ["Results", "`weather_info`", "dict", "Owned by the weather agent"],
            ["Results", "`budget_analysis`", "dict", "Owned by the budget agent"],
            ["Results", "`itinerary_plan`", "dict", "Owned by the itinerary agent"],
            ["Results", "`final_response`", "dict",
             "Owned by the final response agent"],
            ["Quality", "`provider_status`", "list[dict]",
             "One entry per external call, with its provenance label"],
            ["Quality", "`evaluation_results`", "dict", "Ten-dimension scores"],
            ["Quality", "`guardrail_results`", "list[dict]",
             "Every guardrail decision, in order"],
            ["Review", "`human_review_status`", "str",
             "pending, awaiting_review, approved, changes_requested, "
             "revision_in_progress, revision_limit_reached"],
            ["Review", "`requested_changes`", "str | None",
             "The traveller's revision request"],
            ["Review", "`revision_count`", "int", "Bounded by MAX_REVISION_COUNT"],
            ["Review", "`review_iteration`", "int", "Review passes completed"],
            ["Review", "`trip_status`", "str",
             "draft, awaiting_review, revision_in_progress, approved, failed, "
             "rejected"],
            ["Telemetry", "`messages`", "list[dict]",
             "Safe execution notes - never model reasoning"],
            ["Telemetry", "`llm_calls`", "int", "Model calls this run"],
            ["Telemetry", "`tool_calls`", "int", "Tool invocations this run"],
            ["Telemetry", "`errors`", "list[str]", "De-duplicated failure notes"],
            ["Identity", "`trip_id`", "str", "Primary key and checkpoint thread id"],
            ["Identity", "`session_id`", "str | None",
             "Browser session, for history"],
            ["Identity", "`request_id`", "str | None", "Correlates logs and traces"],
            ["Identity", "`created_at` / `updated_at`", "str", "ISO-8601 UTC"],
        ],
        caption="Every field of TravelState, from app/graph/state.py.",
        widths=[0.9, 1.5, 1.1, 3.0],
        size=8.5,
    )

    g.h2("Ownership")
    g.p(
        "Each specialist owns exactly one result key, declared in AGENT_STATE_KEYS. No "
        "agent writes into another agent's key. The budget agent reads flight_results "
        "and hotel_results but only ever writes budget_analysis. This is enforced by "
        "convention and by test rather than by the type system, and it is what allows "
        "a preserved agent's output to be carried forward untouched."
    )
    g.code(
        """
AGENT_STATE_KEYS: dict[str, str] = {
    "flight_agent": "flight_results",
    "hotel_agent": "hotel_results",
    "weather_agent": "weather_info",
    "budget_agent": "budget_analysis",
    "itinerary_agent": "itinerary_plan",
}
""",
        caption="Listing. The ownership map that selective re-execution depends on.",
    )

    g.h2("What deliberately is not in the state")
    g.bullets([
        "No API keys, database URLs or credentials of any kind. The state is "
        "checkpointed to the database and sent to LangSmith when tracing is on; "
        "anything in it is effectively published to both.",
        "No raw provider responses. Each agent normalises what it received into the "
        "project's own schema, so a provider changing its response shape cannot ripple "
        "into the checkpoint format.",
        "No model chain-of-thought. The messages list holds short execution notes "
        "written by the code, not the model's internal reasoning.",
        "No Python objects that do not serialise to JSON. Datetimes are ISO strings, "
        "money is a float with a separate currency field.",
    ])

    g.understand([
        "Why agents communicate through state instead of calling each other.",
        "Which agent owns which key, and why that ownership must not be violated.",
        "Why the state contains no secrets and no raw provider payloads.",
        "Why every value in the state is JSON-compatible.",
    ])


# ---------------------------------------------------------------------------
def _supervisor(g: Guide) -> None:
    g.h1("The Supervisor Agent", page_break=True)

    g.p(
        "The supervisor is the most important agent and does the least work. Its whole "
        "job is to answer one question - which specialists does this request actually "
        "need? - and then get out of the way. It never looks up a flight, never "
        "computes a budget and never writes a line of the itinerary."
    )

    g.h2("Why routing is deterministic")
    g.p(
        "The obvious implementation is to ask the model: give it the request and a "
        "list of agents and let it return a JSON array. JourneyMesh does the routing "
        "in Python instead, with an intent vocabulary and a set of regular "
        "expressions. Three reasons:"
    )
    g.numbered([
        "Testability. A routing decision that is a pure function of a string can be "
        "asserted exactly. The test suite pins dozens of phrasings to their expected "
        "agent sets; a model-based router can only be tested statistically.",
        "Cost and latency. Routing happens on every request and on every revision. A "
        "model call there is a fixed tax on every interaction for a decision that "
        "keyword matching gets right.",
        "Failure containment. If the model is unavailable, deterministic routing still "
        "produces a sensible agent set, and the specialists degrade individually "
        "rather than the whole request failing at step one.",
    ])
    g.callout(
        "important",
        "This is a considered trade, not an aversion to models. Deterministic routing "
        "is weaker on unusual phrasings that share no vocabulary with the intent "
        "lists. The mitigation is that the full-trip fallback selects every agent when "
        "nothing matches, so an unrecognised request produces a complete plan rather "
        "than an empty one.",
    )

    g.h2("The intent vocabulary")
    g.table(
        ["Domain", "Representative terms", "Selects"],
        [
            ["Flights", "flight, fly, airline, airfare, airport, departure, layover, "
                        "nonstop, red-eye, boarding", "`flight_agent`"],
            ["Accommodation", "hotel, stay, accommodation, hostel, resort, airbnb, "
                              "guesthouse, room, lodging, check-in", "`hotel_agent`"],
            ["Weather", "weather, forecast, rain, temperature, climate, monsoon, snow, "
                        "humid, storm, packing", "`weather_agent`"],
            ["Money", "budget, cost, price, cheap, cheaper, expensive, afford, spend, "
                      "under $, per night, total, save", "`budget_agent`"],
            ["Activities", "itinerary, plan, schedule, day-by-day, activities, things "
                           "to do, sightseeing, attractions", "`itinerary_agent`"],
            ["Whole trip", "complete, full trip, complete trip, whole trip, entire "
                           "trip, everything, end to end",
             "All except weather"],
        ],
        caption="The intent vocabulary from app/agents/supervisor.py.",
        widths=[1.0, 3.4, 1.4],
    )

    g.callout(
        "important",
        "Matching is by word, not by substring. That distinction is not academic: "
        "an earlier version matched substrings, so \"hotels\" contained \"hot\" and "
        "every request mentioning a hotel also looked like a question about the "
        "weather. The vocabulary is compiled into one bounded pattern per domain.",
    )

    g.h2("Dependencies between agents at selection time")
    g.p(
        "Two rules widen the selection beyond what the traveller named, and both "
        "exist because a result would otherwise be misleading rather than merely "
        "incomplete."
    )
    g.numbered([
        "A stated budget pulls in the flight and hotel agents. Those are the two "
        "largest cost lines; a budget computed without them would look precise and "
        "be wrong.",
        "A multi-night itinerary pulls in the hotel agent, because a day-by-day "
        "plan with nowhere to sleep is not a plan.",
    ])
    g.p(
        "The weather agent is deliberately not among them. A forecast is retrieved "
        "when the traveller asks about conditions, packing or the season, and not "
        "otherwise - so a request for flights and hotels does not spend a provider "
        "call on a section nobody wanted. The offline case `full_family_trip` "
        "asserts this by forbidding the weather agent, and "
        "`test_weather_joins_the_team_only_when_it_is_asked_for` asserts the other "
        "direction."
    )

    g.h2("Structured extraction alongside routing")
    g.p(
        "The supervisor also reads facts out of the free text that the structured form "
        "may not carry. A price ceiling is matched by a pattern covering \"under\", "
        "\"below\", \"less than\", \"maximum\", \"no more than\" and \"within\", with "
        "an optional per-night qualifier. A trip length is read from \"a 5-day trip\", "
        "\"3 nights\" or \"four days in Kyoto\", including written-out numbers from two "
        "to ten, and is bounded to a sane range so a typo cannot request a thirty-year "
        "itinerary."
    )
    g.code(
        """
def duration_from_text(text: str) -> tuple[int | None, int | None]:
    \"\"\"Read a trip length out of free text. Returns (trip_days, nights).\"\"\"
    match = _DAYS_IN_TEXT.search(text or "")
    if match:
        days = int(match.group(1))
        if 1 <= days <= 30:
            return days, max(days - 1, 0)

    match = _NIGHTS_IN_TEXT.search(text or "")
    if match:
        nights = int(match.group(1))
        if 1 <= nights <= 30:
            return nights + 1, nights
    ...
""",
        caption="Listing. Duration extraction, with the range check that keeps an "
                "absurd value out of the itinerary.",
    )

    g.h2("Revision analysis")
    g.p(
        "On a revision the supervisor runs a different method. analyse_change matches "
        "the requested change against the same vocabulary to get a seed set, "
        "expand_dependents closes that set over AGENT_DEPENDENTS, and "
        "preservation_requests subtracts anything the traveller explicitly asked to "
        "keep. The result is written to selected_agents and change_scope, and the "
        "human-readable execution_reason explains the decision in the interface."
    )
    g.code(
        """
_PRESERVE = re.compile(
    r"\\b(?:keep|retain|leave|don'?t\\s+change|do\\s+not\\s+change|no\\s+change\\s+to|"
    r"same|unchanged|as\\s+is)\\b[^.!?]{0,40}?\\b"
    r"(flight|flights|hotel|hotels|stay|accommodation|weather|forecast|budget|"
    r"itinerary|activities|plan)\\b",
    re.IGNORECASE,
)


def preservation_requests(text: str) -> set[str]:
    \"\"\"Agents the traveller explicitly asked JourneyMesh to leave alone.\"\"\"
    return {
        _PRESERVE_TARGETS[match.group(1).lower()]
        for match in _PRESERVE.finditer(text or "")
        if match.group(1).lower() in _PRESERVE_TARGETS
    }
""",
        caption="Listing. The preservation pattern behind \"keep my flights\". The "
                "bounded gap of forty characters stops it matching across an unrelated "
                "clause.",
    )

    g.understand([
        "What the supervisor decides and what it deliberately never does.",
        "The three reasons routing is Python rather than a model call, and the "
        "weakness that choice accepts.",
        "How a price ceiling and a trip length are read out of free text.",
        "How analyse_change, expand_dependents and preservation_requests combine on a "
        "revision.",
    ])


# ---------------------------------------------------------------------------
def _specialists(g: Guide) -> None:
    g.h1("The Specialist Agents", page_break=True)

    g.h2("What every agent has in common")
    g.p(
        "All six agents derive from a common base in app/agents/base.py, which gives "
        "each of them the same four things: a tracing span so the run appears as a "
        "named step in LangSmith, an authorised path to tools through the MCP client, "
        "a uniform failure contract, and a place to record provider status. An agent "
        "that cannot reach its provider does not raise; it records the failure, labels "
        "its output UNAVAILABLE or ESTIMATE, and lets the rest of the journey proceed."
    )
    g.table(
        ["Guarantee", "How it is provided"],
        [
            ["Every agent appears in the trace",
             "The base class opens a span named after the agent"],
            ["No agent can call an unauthorised tool",
             "Tool access is only available through the MCP client, which re-checks "
             "with the Tool Guard"],
            ["One agent's failure does not fail the journey",
             "Exceptions are caught, recorded to state['errors'] and converted to a "
             "provenance label"],
            ["Every number can be traced to a source",
             "Each external call appends an entry to state['provider_status']"],
        ],
        caption="The four guarantees the agent base class provides.",
        widths=[2.2, 3.6],
    )

    g.h2("Data provenance")
    g.definition(
        "Provenance label",
        "A per-datum marker recording how a value was obtained: LIVE from a provider "
        "API, SEARCH_DERIVED from web search results, ESTIMATE from the system's own "
        "reference tables or arithmetic, UNAVAILABLE when no source could be reached.",
        "A label on every number saying where it came from, so the traveller can tell "
        "a real price from an educated guess.",
    )
    g.p(
        "This is the honest answer to LLM hallucination. Rather than claiming every "
        "figure is authoritative, JourneyMesh states the provenance of each one and "
        "shows it in the interface as a badge. A journey assembled entirely from "
        "estimates is still useful; a journey that silently mixes estimates with live "
        "prices is not."
    )
    g.table(
        ["Label", "Means", "Shown as"],
        [
            ["`LIVE`", "A provider API returned this value", "Live data"],
            ["`SEARCH_DERIVED`", "Extracted from web search results",
             "From search"],
            ["`ESTIMATE`", "Computed by JourneyMesh from reference data",
             "Estimate"],
            ["`UNAVAILABLE`", "No source could be reached", "Unavailable"],
        ],
        caption="The four provenance labels, defined in app/core/constants.py.",
        widths=[1.3, 2.8, 1.4],
    )

    # -- individual agents ------------------------------------------------
    g.h2("Flight agent")
    g.table(
        ["Property", "Value"],
        [
            ["File", "`backend/app/agents/flight_agent.py`"],
            ["Owns", "`flight_results`"],
            ["Tools", "`search_flights`, `lookup_airport`"],
            ["Depends on", "Nothing"],
            ["Invalidates", "`budget_agent`, `itinerary_agent`"],
            ["Result marker", "`options` - an empty list means it ran and found "
                              "nothing"],
        ],
        caption="Flight agent at a glance.",
        widths=[1.2, 4.6],
    )
    g.p(
        "The flight agent resolves city names to airports before searching, because "
        "travellers write \"Dhaka\" and providers want an IATA code. When the aviation "
        "provider is unreachable it falls back to its reference table and labels the "
        "result ESTIMATE rather than returning nothing, so a budget can still be "
        "computed and the traveller can see plainly that the figure is indicative."
    )

    g.h2("Hotel agent")
    g.table(
        ["Property", "Value"],
        [
            ["File", "`backend/app/agents/hotel_agent.py`"],
            ["Owns", "`hotel_results`"],
            ["Tools", "`search_hotels`, `web_search`"],
            ["Depends on", "Nothing"],
            ["Invalidates", "`budget_agent`, `itinerary_agent`"],
            ["Result marker", "`options`"],
        ],
        caption="Hotel agent at a glance.",
        widths=[1.2, 4.6],
    )
    g.p(
        "The hotel agent honours two constraints the supervisor may have extracted "
        "from free text - a nightly price ceiling and a travel style - and passes them "
        "into the tool call as schema-checked arguments. Results derived from web "
        "search rather than a structured provider are labelled SEARCH_DERIVED, which "
        "is a weaker claim than LIVE and is displayed as such."
    )

    g.h2("Weather agent")
    g.table(
        ["Property", "Value"],
        [
            ["File", "`backend/app/agents/weather_agent.py`"],
            ["Owns", "`weather_info`"],
            ["Tools", "`get_current_weather`, `get_weather_forecast`"],
            ["Depends on", "Nothing"],
            ["Invalidates", "`itinerary_agent`"],
            ["Result marker", "`forecast`"],
        ],
        caption="Weather agent at a glance.",
        widths=[1.2, 4.6],
    )
    g.p(
        "The forecast horizon is capped at fourteen days by the tool's argument "
        "schema, because no provider gives a useful daily forecast beyond that. For a "
        "trip further out the agent returns seasonal context instead and labels it "
        "ESTIMATE - which is the honest answer, and more useful than a fabricated "
        "temperature for a date four months away."
    )

    g.h2("Budget agent")
    g.table(
        ["Property", "Value"],
        [
            ["File", "`backend/app/agents/budget_agent.py`"],
            ["Owns", "`budget_analysis`"],
            ["Tools", "None - it is pure computation"],
            ["Depends on", "`flight_results`, `hotel_results`"],
            ["Invalidates", "`itinerary_agent`"],
            ["Result marker", "`breakdown`"],
        ],
        caption="Budget agent at a glance.",
        widths=[1.2, 4.6],
    )
    g.p(
        "The budget agent calls no tools and no model. It is arithmetic over what the "
        "flight and hotel agents already found, plus reference figures for the "
        "categories nobody quoted. Asking a language model to add up numbers is a "
        "known failure mode; this agent exists so that the one part of the journey "
        "where correctness is binary is decided by Python."
    )
    g.table(
        ["Status", "Condition", "Constant"],
        [
            ["`within_budget`", "Total is comfortably under the stated budget",
             "`BUDGET_WITHIN`"],
            ["`near_limit`", "Total is at or above 92% of the budget",
             "`BUDGET_NEAR_LIMIT` / `NEAR_LIMIT_THRESHOLD`"],
            ["`over_budget`", "Total exceeds the budget", "`BUDGET_OVER`"],
            ["`insufficient_data`", "Not enough priced components to judge",
             "`BUDGET_INSUFFICIENT`"],
        ],
        caption="Budget statuses. The fourth exists so the system can say \"I do not "
                "know\" instead of guessing.",
        widths=[1.3, 2.6, 1.9],
    )

    g.h2("Itinerary agent")
    g.table(
        ["Property", "Value"],
        [
            ["File", "`backend/app/agents/itinerary_agent.py`"],
            ["Owns", "`itinerary_plan`"],
            ["Tools", "`web_search`"],
            ["Depends on", "Every agent before it"],
            ["Invalidates", "Nothing"],
            ["Result marker", "`days`"],
        ],
        caption="Itinerary agent at a glance.",
        widths=[1.2, 4.6],
    )
    g.p(
        "The itinerary agent is the one place where a language model's strengths are "
        "actually the right tool: composing a plausible, pleasant sequence of "
        "activities is a language task, not an arithmetic one. It is constrained by "
        "everything upstream - the arrival and departure times from the flights, the "
        "location from the hotels, the forecast from the weather agent, and the "
        "remaining money from the budget - so the model composes within a frame the "
        "deterministic agents built."
    )

    g.h2("Final response agent")
    g.table(
        ["Property", "Value"],
        [
            ["File", "`backend/app/agents/final_response_agent.py`"],
            ["Owns", "`final_response`"],
            ["Runs", "Only after human approval, on the finalise branch"],
            ["Depends on", "Every result key and `response_language`"],
        ],
        caption="Final response agent at a glance.",
        widths=[1.2, 4.6],
    )
    g.p(
        "The final response agent assembles the approved journey into the traveller's "
        "language. The specialists never emit prose in Bengali or Hindi: they emit "
        "message codes, and this agent renders them through the server-side catalogue "
        "in app/core/i18n.py. That keeps translation in one place and means a new "
        "language is a catalogue entry rather than a change to five agents."
    )

    g.understand([
        "The four guarantees every agent inherits from the base class.",
        "What the four provenance labels mean and why they are shown to the "
        "traveller.",
        "Which agent owns which state key, which tools it may call, and what it "
        "invalidates.",
        "Why the budget agent contains no model call at all.",
        "Why agents emit message codes instead of translated prose.",
    ])
