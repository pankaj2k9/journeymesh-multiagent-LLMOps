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
| `mcp/config.py` | how a server is reached | know about tools |
| `mcp/registry.py` | which tool lives where | decide permission |
| `guardrails/tool_guard.py` | may this call happen | perform the call |
| `mcp/client.py` | perform the call, normalise failures | bypass the guard |
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
| The model returns unparseable JSON | the deterministic path is used; the parse failure is counted, not surfaced |
| The output guard fails | the journey is not shown; the failure is audited and evaluated as unsafe |
| The database is not configured | an ephemeral database is used and the health endpoint reports it |
| The revision limit is reached | the review node returns `revision_limit_reached`; the loop cannot continue |

Nothing in this list produces a stack trace in a response body.

---

## 6. Why the graph ends at review

An alternative would be to interrupt inside a running graph and hold the process open.
JourneyMesh ends the run at the review node instead, because:

- the pause may last minutes or days, and no process should be held open for that;
- the API is deployable to a serverless runtime, where a held-open run is not possible;
- the checkpoint is then the only thing that has to survive, which PostgreSQL already does;
- re-entering through a conditional edge keyed on `human_review_status` makes the three
  entry points (plan, revise, finalise) explicit and individually testable.

The cost is one extra branch at the graph entry. The benefit is a review step that behaves
identically whether the traveller answers in five seconds or next week.
