# JourneyMesh - architecture notes

Supporting detail for the overview in the [README](../README.md). This document covers the
request lifecycle, the module boundaries and the decisions behind them.

---

## 1. Request lifecycle

### 1.1 Planning a journey

```text
POST /api/v1/trips/plan
  |
  |  RequestContextMiddleware      request id, fresh trace
  |  RequestSizeLimitMiddleware    reject oversized bodies before parsing
  |  RateLimitMiddleware           fixed window per client
  |  SecurityHeadersMiddleware     CSP and friends on the way out
  v
TripPlanRequest (Pydantic)         structure, enums, date order, currency
  v
input_guard.check_request          relevance, semantics, injection, PII
  |
  +-- blocked --> GuardrailBlockedResponse  (HTTP 200, status: "blocked")
  v
TravelWorkflow.plan
  |
  |  new_state()                   a TravelState for this trip id
  |  supervisor                    selected_agents + execution_reason
  |  specialists                   in AGENT_EXECUTION_ORDER, filtered
  |  output_guard                  schema, secrets, markup, consistency
  |  evaluation                    ten dimensions, deterministic first
  |  human_review                  status -> awaiting_review, graph ends
  v
TravelService persists trip, results, first review row, messages, audit
  v
TripPlanResponse
```

### 1.2 Approving

```text
POST /api/v1/trips/{trip_id}/approve
  -> ReviewService loads the checkpointed state (or rebuilds it from storage)
  -> workflow.approve() re-enters the graph on the "finalise" branch
  -> final_response_agent renders the journey in en / bn / hi
  -> trip.status = approved, results and review row persisted
```

### 1.3 Requesting changes

```text
POST /api/v1/trips/{trip_id}/request-changes
  -> revision limit checked first  (409 revision_limit_reached)
  -> input_guard.check_change_request  (injection, PII, size)
  -> workflow.revise() re-enters on the "revise" branch
       supervisor.analyse_change  -> change_scope + selected_agents + constraint updates
       specialists                -> only the selected agents run
       output_guard, evaluation, human_review
  -> revision_count += 1, review row recorded with the change scope
```

---

## 2. Module boundaries

| Module | Answers | Does not |
| --- | --- | --- |
| `agents/supervisor.py` | which agents run | plan any part of the trip |
| `agents/*_agent.py` | what happens in one slice | call another agent, or a provider directly |
| `graph/state.py` | what everyone shares | contain behaviour |
| `graph/travel_graph.py` | in what order, and where it pauses | decide *what* to run |
| `mcp/config.py` | how a server is reached, and whether it can be | know about tools |
| `mcp/registry.py` | which tool lives where | decide permission |
| `guardrails/tool_guard.py` | may this call happen | perform the call |
| `mcp/client.py` | perform the call, normalise failures | bypass the guard |
| `mcp/providers/*` | translate our contract to one server's | decide transport |
| `mcp/lifecycle.py` | start, probe and stop MCP sessions | interpret a result |
| `mcp/security.py` | redact a URL or an error | decide what is called |
| `graph/human_review.py` | the shape of the pause and the resume | route the graph |
| `guardrails/*` | what may enter and leave a model | judge quality |
| `evaluation/*` | how good the result is | change the result |
| `services/*` | HTTP concerns meeting the graph | contain agent logic |
| `db/*` | what survives | know about agents |

The rule that makes this hold: **agents communicate only through `TravelState`**. That is
what allows an agent to be skipped without any other agent noticing, which is the whole
basis of selective re-execution.

---

## 3. Selective re-execution

Dependencies are declared once:

```python
AGENT_DEPENDENTS = {
    "flight_agent":    ("budget_agent", "itinerary_agent"),
    "hotel_agent":     ("budget_agent", "itinerary_agent"),
    "weather_agent":   ("itinerary_agent",),
    "budget_agent":    ("itinerary_agent",),
    "itinerary_agent": (),
}
```

`analyse_change` produces a scope from the change text, subtracts anything the traveller
explicitly asked to keep, expands the remainder through `AGENT_DEPENDENTS`, and orders the
result by `AGENT_EXECUTION_ORDER`. Agents outside that set are simply not invoked, so their
slice of the state is carried forward unchanged - not copied, not regenerated.

```text
"Find a cheaper hotel under $120 per night, keep my flights."

  keyword scope     : {hotel_agent, budget_agent, flight_agent}
  preservation      : {flight_agent}          <- "keep my flights"
  scope             : {hotel_agent, budget_agent}
  + dependents      : {hotel_agent, budget_agent, itinerary_agent}
  ordered           : [hotel_agent, budget_agent, itinerary_agent]
  constraint update : max_hotel_price_per_night = 120
  preserved         : flight_results, weather_info
```

---

## 4. Data provenance

Four labels travel with every value that could be mistaken for a fact:

| Label | Meaning |
| --- | --- |
| `LIVE` | a provider confirmed it at the time recorded |
| `SEARCH_DERIVED` | extracted from public research, not a booking system |
| `ESTIMATE` | produced by a JourneyMesh planning model |
| `UNAVAILABLE` | no provider could supply it |

The budget agent keeps `confirmed_cost_total` and `estimated_cost_total` apart, every cost
line carries its own `BudgetLine` provenance with the basis stated in words, the evaluation
module fails a journey whose priced items are unlabelled, and the interface renders the
label next to the number. An estimate is never displayed as a live price.

---

## 5. Failure behaviour

| Failure | What happens |
| --- | --- |
| A provider is down | the tool call returns `ok: false`, the agent records provider status and continues |
| An agent raises | the error is recorded on the state, a safe note is added, the rest of the journey proceeds |
| An MCP server is unreachable | the client falls back to the in-process adapter and says so in the notes |
| An MCP adapter cannot map a tool faithfully | it declines, and the in-process implementation answers instead |
| An MCP server answers in an unexpected shape | the response is discarded rather than half-parsed |
| An MCP credential appears in an error | `security.safe_error` redacts it before it is logged or returned |
| The model returns unparseable JSON | the deterministic path is used; the parse failure is counted, not surfaced |
| The output guard fails | the journey is not shown; the failure is audited and evaluated as unsafe |
| The database is not configured | an ephemeral database is used and the health endpoint reports it |
| The revision limit is reached | the review node returns `revision_limit_reached`; the loop cannot continue |

Nothing in this list produces a stack trace in a response body.

---

## 6. How the graph pauses for a person

`human_review` calls LangGraph's `interrupt()`. The run is suspended there, the
checkpointer records both the state and the fact that this node is mid-execution, and
`ainvoke` returns an `__interrupt__` payload rather than a finished state.
`Command(resume={"action": ...})` continues that *same* node call: `interrupt()` returns
the decision, and the conditional edge after it routes to `final_response` on an approval,
or back through `supervisor_revision` on a change request.

Nothing is held open. The pause lives in the checkpointer, not in a Python object, so a
restarted worker — or an entirely different process — can continue a run somebody else
started. A test asserts exactly that.

Two details are worth knowing, because both were found the hard way:

- **A node's state changes persist from its return value, and `interrupt()` raises.**
  Anything written in the same node before the pause is discarded. `review_gate` is a
  separate node immediately before, so "awaiting review" is committed while the journey is
  actually waiting. Without it the API reported `pending` for a paused journey.
- **A missing checkpoint is not an error.** `MemorySaver` loses everything on restart, and
  a restored database may have no checkpoint row. When no interrupt is pending, the
  decision is applied to the state and the graph is re-entered through `entry_router`
  instead. It is a documented fallback and it logs when it happens.

`trip_id` is the LangGraph `thread_id`. One identifier, mapped in one place.
