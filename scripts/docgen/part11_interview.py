"""Interview preparation: timed explanations and fifty-plus questions."""

from __future__ import annotations

from docgen.builder import Guide
from docgen.repo import FACTS


def write(g: Guide) -> None:
    _timed(g)
    _architecture_qs(g)
    _langgraph_qs(g)
    _agent_qs(g)
    _mcp_qs(g)
    _safety_qs(g)
    _eval_qs(g)
    _backend_qs(g)
    _frontend_qs(g)
    _data_qs(g)
    _deploy_qs(g)
    _judgement_qs(g)
    _closing(g)


# ---------------------------------------------------------------------------
def _timed(g: Guide) -> None:
    g.h1("Explaining JourneyMesh Out Loud", page_break=True)
    g.p(
        "An interviewer almost always asks the same opening question in one of three "
        "sizes. Prepare all three, and match the size to the question - answering a "
        "\"tell me briefly\" with five minutes of detail is itself a signal."
    )

    g.h2("Thirty seconds")
    g.callout(
        "tip",
        "JourneyMesh is a multilingual multi-agent travel planner. A supervisor agent "
        "decides which specialist agents a request needs - flights, hotels, weather, "
        "budget, itinerary - and they run over a shared state in a LangGraph workflow. "
        "Every external call goes through the Model Context Protocol behind a "
        "deny-by-default tool guard, every value is labelled with where it came from, "
        "and every draft stops for a human. When the traveller asks for a change, only "
        "the affected agents re-run - so \"cheaper hotels, keep my flights\" keeps the "
        "flights exactly as they were.",
    )

    g.h2("Two minutes")
    g.p(
        "Open with the problem, then the shape, then the one thing that is distinctive."
    )
    g.numbered([
        "The problem. Travel planning spans domains with different sources of truth - "
        "flights, hotels, weather, money, activities - and they constrain each other. "
        "A single LLM prompt gives you fluent answers that may be confidently wrong "
        "about prices and schedules, and no way to change one part without "
        "regenerating everything.",
        "The shape. React and FastAPI, with a LangGraph state machine in between. A "
        "supervisor selects specialists at run time; each specialist owns one slice of "
        "a shared TravelState. External calls go through MCP servers behind a tool "
        "guard that denies by default. Output is checked by guardrails and scored "
        "across ten dimensions before a person sees it.",
        "The distinctive part. The graph deliberately ends at the human review rather "
        "than looping. The state is checkpointed, so the pause survives a process "
        "restart. When the traveller asks for a change, the supervisor analyses it "
        "into an agent set, expands it over a declared dependency relation, subtracts "
        "anything they asked to keep, and re-runs only that. The preserved agent's "
        "output is carried forward unchanged - and there is a regression test that "
        "asserts byte equality.",
        "The honesty layer. Every value carries a provenance label - live, "
        "search-derived, estimate or unavailable - and the interface shows it. A "
        "provider outage degrades the answer visibly instead of silently.",
    ])

    g.h2("Five minutes")
    g.p("Follow one request end to end, and name the decisions as you pass them.")
    g.table(
        ["Beat", "Say this", "Decision to name"],
        [
            ["Request",
             "A structured trip request, not a chat message. Pydantic validates it, "
             "middleware bounds and rate-limits it, input guardrails screen it for "
             "relevance, injection and personal data.",
             "Guardrails are code outside the model, not instructions inside it"],
            ["Routing",
             "The supervisor decides which specialists run - in Python, from an intent "
             "vocabulary, not by asking a model.",
             "Deterministic routing: exactly testable, free, works when the model is "
             "down"],
            ["Execution",
             "Selected agents run in dependency order over a shared state. Budget "
             "consumes flights and hotels; the itinerary consumes everything.",
             "Agents share state rather than calling each other"],
            ["Tools",
             "Every external call goes through MCP, and before that a guard that "
             "checks registration, agent authorization, argument schema, forbidden "
             "keys, operation class and a per-run call budget.",
             "Deny by default - a forgotten rule refuses rather than permits"],
            ["Quality",
             "Output guardrails, then a ten-dimension evaluation with weighted "
             "scoring, deterministic rules first.",
             "Anything checkable by rule is checked by rule"],
            ["The pause",
             "The graph ends. The state is checkpointed under the trip id. The "
             "traveller decides whenever they like.",
             "A durable pause rather than a held request"],
            ["The revision",
             "Intent detection, dependency expansion, preservation subtraction. Three "
             "agents re-run; the flights are untouched.",
             "This is the thing to spend the most time on"],
            ["Deployment",
             "One Docker image with the React build inside, on Render, with Neon "
             "PostgreSQL, deployed by GitHub Actions after CI passes, with Render's "
             "own auto-deploy off.",
             "One controlled deployment path, and a database independent of the host"],
        ],
        caption="A five-minute walkthrough, beat by beat.",
        widths=[0.9, 3.0, 1.9],
    )

    g.h2("What to have ready to draw")
    g.bullets([
        "The seven graph nodes and the conditional entry edge.",
        "The dependency relation: flights and hotels invalidate budget and itinerary; "
        "weather invalidates itinerary; budget invalidates itinerary.",
        "The tool call path: agent, guard, client, transport, provider, normalised "
        "result with a provenance label.",
        "The pipeline: push, CI, deploy workflow, Render, Neon.",
    ])


# ---------------------------------------------------------------------------
def _architecture_qs(g: Guide) -> None:
    g.h1("Interview Questions: Architecture", page_break=True)

    g.qa(
        "1. Why multi-agent rather than one well-written prompt?",
        "Because one prompt cannot be partially re-run, and cannot tell a looked-up "
        "price from an invented one.",
        "Travel planning decomposes into domains with different sources of truth. "
        "Separating them means each prompt is small and testable, a failure in one "
        "domain does not corrupt the others, each agent can label the provenance of "
        "its own output, and - most importantly - a change request can re-run three "
        "agents instead of regenerating the whole plan. A single prompt gives up all "
        "four.",
        "So when would a single prompt be the right choice?",
    )
    g.qa(
        "2. What are the layers and which way do dependencies point?",
        "Presentation, interface, orchestration, domain, integration - each depends "
        "only downward.",
        "The rule is what makes the system testable. The orchestration layer knows "
        "about agents but not HTTP, so the graph can be driven from a test or the "
        "evaluation runner. The domain layer knows about tools but not transports, so "
        "swapping a provider does not touch agent code. The interface layer owns "
        "validation and security, so by the time an agent sees a value it is already "
        "typed and screened.",
        "Where does that rule get violated, if anywhere?",
    )
    g.qa(
        "3. How do the agents communicate?",
        "Only through a shared TypedDict called TravelState. They never call each "
        "other.",
        "Each specialist owns exactly one key, declared in AGENT_STATE_KEYS. The "
        "budget agent reads flight_results and hotel_results but writes only "
        "budget_analysis. That indirection is precisely what allows a preserved "
        "agent's output to be carried forward untouched during a revision - there is "
        "nobody else who could have modified it.",
        "What enforces that ownership? Convention, or the type system?",
    )
    g.qa(
        "4. What is the hardest problem you solved in this project?",
        "Making a revision change exactly the right amount - no more and no less.",
        "\"Cheaper hotels, keep my flights\" has to change the hotels, recompute the "
        "budget and the itinerary because they depend on the hotels, and leave the "
        "flights alone. That needed three separate mechanisms: intent detection to "
        "seed the set, a declared dependency relation to close it, and a preservation "
        "pattern to subtract from it. Getting the third one right required a bounded "
        "regex so \"keep my flights\" does not match across an unrelated clause.",
        "What would break if you got the dependency relation wrong in each direction?",
    )
    g.qa(
        "5. What would you change if you rebuilt it?",
        "Run the independent specialists concurrently, and move rate limiting to a "
        "shared store.",
        "Flights, hotels and weather have no dependency on each other and currently "
        "run in sequence, so a full plan takes the sum of their times rather than the "
        "maximum. That is the first thing I would change. The second is the in-process "
        "rate limiter, which is correct for one container and silently wrong for two.",
        "Why did you not do the concurrency in the first place?",
    )


# ---------------------------------------------------------------------------
def _langgraph_qs(g: Guide) -> None:
    g.h1("Interview Questions: LangGraph and Orchestration", page_break=True)

    g.qa(
        "6. Why LangGraph rather than a LangChain chain?",
        "Because the workflow has to stop and wait for a human, and a chain has "
        "nowhere to stop.",
        "A chain is a fixed sequence. It cannot branch on content, cannot loop, and "
        "cannot pause. LangGraph gives a state machine with conditional edges and a "
        "checkpointer, which is exactly what a review-and-revise workflow needs.",
        "What would you have used if LangGraph did not exist?",
    )
    g.qa(
        "7. Why does the graph end at human review instead of looping back?",
        "Because a running graph cannot wait for a person for an unbounded time.",
        "The HTTP request would time out, the worker may be recycled, and on a free "
        "tier the container genuinely sleeps between the draft and the decision. So "
        "the run ends, the state is checkpointed and the trip is persisted with status "
        "awaiting_review. A later invocation resumes and the entry router picks the "
        "revise or finalise branch. The pause is durable rather than held open.",
        "What does that cost you compared with an in-process interrupt?",
    )
    g.qa(
        "8. What is a checkpointer and why does it constrain your state design?",
        "It serialises the state after each node so a run can resume elsewhere - which "
        "means everything in the state must be JSON-compatible.",
        "That is why TravelState is a TypedDict of plain values rather than a Pydantic "
        "model holding rich Python objects. Datetimes are ISO strings, money is a "
        "float with a separate currency field. JourneyMesh uses an in-memory saver "
        "when there is no PostgreSQL and the PostgreSQL saver when there is, with "
        "identical graph code.",
        "What is the checkpoint thread id here, and why that choice?",
    )
    g.qa(
        "9. Why are the five specialists one node rather than five?",
        "Because the set that runs is decided at run time and the order is a fixed "
        "dependency order, so there is no routing decision to express between them.",
        "Five nodes would need conditional edges around every one of them to express "
        "\"maybe run, maybe skip\". One node also means one checkpoint boundary around "
        "the whole specialist phase, which keeps the persisted state smaller and the "
        "trace readable. The cost is that they run sequentially.",
        "How would you introduce concurrency without losing that?",
    )
    g.qa(
        "10. Walk me through the conditional entry edge.",
        "One router function reads the state and returns plan, revise or finalise.",
        "Approved reviews go to finalise, a present requested_changes goes to revise, "
        "and anything else is a new journey and goes to plan. It is plain Python over "
        "the state, so it is unit-testable with a dictionary and no model.",
        "What happens if a resumed run's state is inconsistent - approved and with "
        "requested changes?",
    )


# ---------------------------------------------------------------------------
def _agent_qs(g: Guide) -> None:
    g.h1("Interview Questions: Agents", page_break=True)

    g.qa(
        "11. Why is the supervisor's routing deterministic rather than model-driven?",
        "Testability, cost and failure containment.",
        "Routing runs on every request and every revision. A pure function of a string "
        "can be pinned to exact expected agent sets in tests; a model router can only "
        "be tested statistically. It also costs nothing, adds no latency, and still "
        "works when the model is unavailable. The weakness is unusual phrasings, and "
        "the mitigation is a full-trip fallback that selects everything rather than "
        "nothing.",
        "How would you know if the vocabulary was missing an important phrasing?",
    )
    g.qa(
        "12. How does a revision decide which agents to re-run?",
        "Intent detection seeds a set, dependency expansion closes it, preservation "
        "requests subtract from it.",
        "\"Cheaper hotels under $100, keep my flights\" seeds hotel from the "
        "accommodation vocabulary and budget from the money vocabulary. "
        "expand_dependents adds itinerary because both hotel and budget invalidate it. "
        "preservation_requests matches \"keep my flights\" and removes the flight "
        "agent. Three agents run; the flight results are carried forward unchanged.",
        "What if they said \"cheaper flights, keep my flights\"?",
    )
    g.qa(
        "13. Why does the budget agent not use a model?",
        "Because arithmetic is the one part of a travel plan where correctness is "
        "binary, and it is a known weak point for language models.",
        "It calls no tools and no model. It is Python over what the flight and hotel "
        "agents found, plus reference figures for unpriced categories. That makes "
        "budget totals exactly reproducible and lets the budget_consistency evaluation "
        "dimension assert the arithmetic directly rather than judge it.",
        "What does that cost you in the output?",
    )
    g.qa(
        "14. What is a provenance label and why do you have them?",
        "A per-value marker - LIVE, SEARCH_DERIVED, ESTIMATE or UNAVAILABLE - saying "
        "how that value was obtained.",
        "It is the honest answer to hallucination. Rather than claiming every figure "
        "is authoritative, the system says where each one came from and shows it as a "
        "badge. A plan built entirely from estimates is still useful; one that silently "
        "mixes estimates with live prices is not. The MCP client canonicalises any "
        "unrecognised label to UNAVAILABLE so an unexpected value cannot propagate.",
        "Who decides the label - the agent or the client?",
    )
    g.qa(
        "15. Why do agents emit message codes instead of translated text?",
        "So translation lives in one place and adding a language is a catalogue entry "
        "rather than five prompt changes.",
        "Specialists emit codes and structured values; the final response agent renders "
        "them through the server-side catalogue. Five agents would otherwise each need "
        "to know three languages, and a model may translate the same phrase "
        "inconsistently between runs.",
        "How do you verify the catalogues stay in sync?",
    )
    g.qa(
        "16. What happens when one agent fails?",
        "It records the failure, labels its output, and the journey continues without "
        "it.",
        "The agent base class catches exceptions, appends to state['errors'] and "
        "converts the failure into a provenance label - ESTIMATE if reference data can "
        "substitute, UNAVAILABLE if nothing can. A travel planner that fails entirely "
        "because one provider is down is worse than one that says what it could not "
        "price.",
        "Which failures are deliberately not degraded?",
    )
    g.qa(
        "17. How does the system extract a budget or a duration from free text?",
        "Bounded regular expressions in the supervisor, with sanity limits.",
        "A price ceiling pattern covers under, below, less than, maximum, no more than "
        "and within, with an optional per-night qualifier. Duration reads \"a 5-day "
        "trip\", \"3 nights\" or \"four days\" including written-out numbers, and "
        "rejects anything outside one to thirty days so a typo cannot request an "
        "absurd itinerary.",
        "Why not have the model extract these?",
    )


# ---------------------------------------------------------------------------
def _mcp_qs(g: Guide) -> None:
    g.h1("Interview Questions: MCP and Tools", page_break=True)

    g.qa(
        "18. What is the Model Context Protocol?",
        "An open protocol standardising how an application exposes tools to a model - "
        "typed schemas, defined transports, one message shape.",
        "Three roles: the host owns the conversation and decides what is allowed, the "
        "client maintains connections and invokes tools, servers expose capabilities. "
        "Here the host is FastAPI plus the graph, the client is app/mcp/client.py, and "
        "there are three servers - aviation, search and weather.",
        "What is the difference between a resource and a tool in MCP?",
    )
    g.qa(
        "19. Why MCP instead of just calling the provider APIs?",
        "Because it gives one choke point where every external call can be authorised, "
        "bounded, instrumented and normalised.",
        "With direct HTTP clients, authorization has nowhere to live, error shapes "
        "differ per provider, and swapping a provider means changing agent code. The "
        "honest caveat is that for a single-provider system this is pure overhead - it "
        "pays off with several providers, several agents and a hard authorization "
        "requirement.",
        "So is MCP worth it for a two-agent prototype?",
    )
    g.qa(
        "20. What transports do you support?",
        "stdio, streamable HTTP, and an in-process adapter as the fallback.",
        "stdio launches the server as a subprocess and exchanges JSON-RPC over "
        "standard streams. HTTP posts JSON-RPC to a URL. The in-process adapter calls "
        "the same tool function in the same process with the same schema validation and "
        "the same result shape - it is not a mock, only a different transport, which is "
        "what lets tests and CI exercise the real tool path with no network.",
        "How does the client choose?",
    )
    g.qa(
        "21. Explain the Tool Guard.",
        "Deny-by-default authorization for every tool call: seven checks, and an "
        "unregistered tool is refused.",
        "Registration, enablement, agent authorization, argument schema, forbidden "
        "argument keys, operation class and per-run call budget. A model that invents "
        "a tool name, an injection that names a plausible tool, and a developer who "
        "forgets a policy all produce the same outcome - a refusal and an audit event.",
        "Why does the client re-check something the guard already approved?",
    )
    g.qa(
        "22. Why declare booking and cancellation tools if they are disabled?",
        "So the authorization surface is explicit and reviewable rather than implied.",
        "book_flight, book_hotel and cancel_reservation are in the policy table with "
        "operation classes of write and destructive, risk high, requires_confirmation "
        "true and enabled false. Anyone reading the policy table can see exactly what "
        "the system could do and what it currently will not.",
        "What would you need to add before enabling one of them?",
    )
    g.qa(
        "23. What is a per-run call budget for?",
        "Cost control and loop breaking.",
        "max_calls_per_run bounds how many times a tool may be invoked within one graph "
        "run - four flight searches, eight airport lookups, six web searches. Without "
        "it, an agent retrying on an unhelpful result could burn a provider quota on a "
        "single request.",
        "What happens to the agent when its budget is exhausted?",
    )


# ---------------------------------------------------------------------------
def _safety_qs(g: Guide) -> None:
    g.h1("Interview Questions: Safety and Guardrails", page_break=True)

    g.qa(
        "24. How do you defend against prompt injection?",
        "A weighted rule set that runs before any text reaches a model, enforced by the "
        "application - plus a tool guard that bounds the damage if it is bypassed.",
        "Ten weighted regular-expression rules covering instruction override, system "
        "prompt disclosure, secret extraction, file access, shell execution, permission "
        "override, hidden tool invocation, guard disabling, role confusion and "
        "exfiltration. Matches accumulate; the request is blocked at 0.80. The critical "
        "point is that the model is never asked whether the request was an injection.",
        "What does a successful injection actually get you here?",
    )
    g.qa(
        "25. Why is a system prompt instruction not a control?",
        "Because it is enforced by the component it is trying to constrain.",
        "\"Never reveal your instructions\" is a request. It can be argued with, and it "
        "fails silently. Every safety property JourneyMesh claims is enforced in "
        "application code outside the model - input guard, injection classifier, PII "
        "guard, tool guard, output guard.",
        "Is there anything you do rely on the prompt for?",
    )
    g.qa(
        "26. What personal data do you detect, and how do you avoid false positives?",
        "Cards, passports, national ids, bank accounts, emails, phones and "
        "credentials - with a Luhn check and a phone shape test.",
        "Precision matters more than recall here, because an over-eager redactor "
        "destroys the request. Sixteen-digit numbers are only treated as cards if they "
        "pass the Luhn checksum. The phone matcher explicitly rejects ISO dates and "
        "digit runs shorter than nine, because an early version was redacting "
        "\"2026-11-10\" as a phone number and removing the departure date.",
        "Where in the pipeline does redaction happen?",
    )
    g.qa(
        "27. Why check the output for secrets when you never put one there?",
        "Defence in depth - the output contains model-composed text, and a model shown "
        "something it should not have been can repeat it.",
        "The output guard scans for key-shaped strings with realistic bodies, "
        "PostgreSQL URLs, named provider key variables and DATABASE_URL assignments. It "
        "also checks unsafe markup, URL schemes, chain-of-thought markers, internal "
        "consistency and schema conformance. It is cheap, on a payload about to be "
        "serialised anyway.",
        "What do you do when it fires?",
    )
    g.qa(
        "28. What is the single most security-relevant component?",
        "The Tool Guard.",
        "It is the boundary between a model's suggestion and an action in the world. "
        "Everything else - injection detection, PII redaction, output scanning - "
        "reduces the likelihood of a bad instruction. The tool guard bounds what a bad "
        "instruction can achieve, and it does so without consulting the model at all.",
        "How would you test that boundary?",
    )
    g.qa(
        "29. What are you deliberately not claiming about security?",
        "No authentication, no proof against injection, no distributed rate limiting, "
        "and no penetration test.",
        "Journeys are scoped by an opaque session id, which is not a credential. The "
        "injection classifier is a first line, not a proof. In-process rate limiting "
        "does not survive horizontal scaling. No penetration test has been performed - "
        "not measured yet. Saying so is part of the design, because an overstated "
        "security claim is worse than a stated limitation.",
        "Which of those would you fix first?",
    )


# ---------------------------------------------------------------------------
def _eval_qs(g: Guide) -> None:
    g.h1("Interview Questions: Evaluation", page_break=True)

    g.qa(
        "30. How do you evaluate an LLM system?",
        "Ten dimensions, deterministic rules first, weighted per dimension, with two "
        "dimensions treated as blocking.",
        "Relevance, completeness, groundedness, consistency, tool correctness, schema "
        "validity, safety, language correctness, itinerary feasibility and budget "
        "consistency. Anything checkable by rule is checked by rule - arithmetic, "
        "dates, schema, tool authorisation, language are facts, not judgements. A model "
        "judge is optional and only ever adds opinions on top.",
        "Which of those ten genuinely needs a judge?",
    )
    g.qa(
        "31. Why weight by dimension rather than by check?",
        "So adding a third safety check does not silently make safety count three "
        "times as much.",
        "Checks within a dimension are averaged to a dimension score; the overall score "
        "is the weighted mean of the dimension scores. Safety carries 2.0, groundedness "
        "and schema validity 1.5, budget consistency 1.3, completeness, consistency and "
        "feasibility 1.2, relevance 1.0, tool correctness and language 0.8.",
        "How did you pick those weights?",
    )
    g.qa(
        "32. What does a blocking dimension mean?",
        "A failure there means the journey should not be shown at all, regardless of "
        "the overall score.",
        "safety and schema_validity are blocking, and blocking_failures() reports them "
        "separately. Everything else degrades the score rather than stopping the "
        "response, because a journey with a weak itinerary is still worth showing while "
        "one that fails schema validation is not.",
        "What happens in the interface when that fires?",
    )
    g.qa(
        "33. How do you stop the evaluation from being a vanity metric?",
        f"By running {len(FACTS.eval_cases)} offline cases in CI, deterministically, "
        "with declared expectations rather than a score to admire.",
        "Each case declares the agents it expects, the agents that must not run, "
        "whether it should be blocked, the expected language and a minimum score. The "
        "cheaper_hotel_revision case asserts that a revision re-runs exactly three "
        "agents and preserves the flights. They run with no provider keys, so the same "
        "input produces the same result every time and a regression is unambiguous.",
        "What would a flaky evaluation case tell you?",
    )
    g.qa(
        "34. What is groundedness and how do you check it without a judge?",
        "Whether every claim traces to a tool result or a labelled estimate - checkable "
        "because every value already carries a provenance label.",
        "This is the payoff of the provenance design. The evaluator does not have to "
        "reason about whether a price is plausible; it checks that the price came from "
        "somewhere and that the label matches the source that produced it.",
        "What kind of ungrounded claim would slip through?",
    )


# ---------------------------------------------------------------------------
def _backend_qs(g: Guide) -> None:
    g.h1("Interview Questions: Backend", page_break=True)

    g.qa(
        "35. Why FastAPI?",
        "Because route signatures are the validation layer, and most of what this "
        "system does is waiting.",
        "Async by default matters when every step waits on a model, a provider or a "
        "database. Validation as type annotation means no separate schema file to drift "
        "from the code. And the same Pydantic models validate an HTTP request and the "
        "arguments an agent receives, so there is one definition of a trip constraint.",
        "What does FastAPI not give you that you had to build?",
    )
    g.qa(
        "36. Explain your middleware order.",
        "Request id, size limit, rate limit, security headers - outermost to "
        "innermost, with CORS outside all of it.",
        "The request id is attached first so a rejection by any later layer is still "
        "correlatable. The size limit runs before the rate limiter so an oversized body "
        "is discarded without consuming a rate-limit slot. Security headers sit closest "
        "to the handler so every response - including errors produced above - carries "
        "them.",
        "FastAPI applies middleware in reverse registration order. Does your file "
        "reflect that?",
    )
    g.qa(
        "37. Why must the health endpoint be cheap?",
        "Because a health check that calls a provider turns that provider's outage into "
        "a restart loop.",
        "It calls no model, runs no graph, invokes no MCP tool, contacts no travel "
        "provider, does not talk to LangSmith and does not open a database connection. "
        "It reports configuration. The verbose form adds provider and MCP catalogues, "
        "which is still local state.",
        "How would you check the database is actually reachable, then?",
    )
    g.qa(
        "38. What does the system do with no API keys at all?",
        "It runs. That is a supported state, not a failure.",
        "The settings layer treats a blank environment variable as absent rather than "
        "as an empty string, the LLM service reports llm_available false, and agents "
        "produce structured results from tools and reference data with everything "
        "labelled ESTIMATE. The health endpoint reports llm: deterministic. That is why "
        "CI can run the whole offline evaluation suite with no secrets.",
        "How do you stop that mode from silently shipping to production?",
    )
    g.qa(
        "39. Why is there a service layer between routes and the graph?",
        "So the sequence can be called from a test or the evaluation runner without an "
        "HTTP client.",
        "travel_service owns validate, persist intent, run the workflow, persist "
        "result, shape response. review_service owns approve and request-changes, "
        "including the revision ceiling. Repositories are the only code that writes "
        "SQL-shaped operations, and agents never touch them.",
        "What would go wrong if an agent called a repository?",
    )
    g.qa(
        "40. How does one container serve both a SPA and an API?",
        "A catch-all mount with reserved prefixes and a path-traversal guard.",
        "RESERVED_PREFIXES keeps /api, the docs paths and the OpenAPI schema out of the "
        "catch-all. _safe_file resolves requested paths and refuses anything escaping "
        "the distribution directory. Any unmatched GET returns index.html with a 200, "
        "which is what React Router needs for a deep link. A missing build makes "
        "mount_frontend return False and the API runs alone rather than failing to "
        "start.",
        "Why 200 and not 404 for an unknown path?",
    )


# ---------------------------------------------------------------------------
def _frontend_qs(g: Guide) -> None:
    g.h1("Interview Questions: Frontend", page_break=True)

    g.qa(
        "41. Why TanStack Query rather than useEffect?",
        "Because server state needs caching, invalidation and staleness policy, and "
        "useEffect makes you rebuild those in every component.",
        "One cache entry per trip id rather than one fetch per component. Cached data "
        "renders instantly on navigation and refreshes in the background. A mutation "
        "invalidates the key and every consumer re-renders - the review panel does not "
        "need to know what else on the page shows trip data.",
        "When is useEffect still the right tool?",
    )
    g.qa(
        "42. How does the dark theme work?",
        "Semantic tokens over CSS variables, class-based dark mode, and a pre-paint "
        "script to prevent the flash.",
        "No component names a colour - they say bg-surface, text-muted, "
        "text-positive-fg. Each token resolves to a CSS variable defined twice in "
        "index.css, once on :root and once under .dark. Tailwind's darkMode is 'class'. "
        "A small inline script in index.html reads the stored preference and toggles "
        "the class before the first paint.",
        "How do you allow that inline script under a content security policy?",
    )
    g.qa(
        "43. How is the inline theme script allowed by the CSP?",
        "By allowlisting its exact SHA-256 hash rather than using 'unsafe-inline'.",
        "The hash appears in both backend/app/security/headers.py and "
        "frontend/nginx.conf, so both serving paths enforce the same policy. Changing "
        "the script by one character requires regenerating the hash in both places - "
        "which is intended friction, and the symptom of forgetting is a flash of the "
        "wrong theme rather than an error.",
        "Why not a nonce?",
    )
    g.qa(
        "44. Why no system-following theme option?",
        "It was implemented and then removed: with two states, an explicit persisted "
        "choice is simpler to reason about and to test.",
        "A system option adds a third state to design and test, and produces an "
        "interface that changes appearance because the operating system crossed sunset "
        "- which reads as a bug to a user who never asked for it. Theme and language "
        "are also independent, stored under journeymesh_theme and journeymesh_language, "
        "so changing one never affects the other.",
        "What do you lose for a user whose whole system is dark?",
    )
    g.qa(
        "45. How is multilingual support done on the client?",
        "i18next with a language detector, one catalogue per language, and a parity "
        "test.",
        f"The English catalogue has {FACTS.locale_keys} keys and Bengali and Hindi "
        "mirror it. The detector reads the stored choice first, then the browser "
        "preference, then falls back to English. There are deliberately two catalogues "
        "- one for interface chrome, one on the server for agent-produced content - "
        "because they change for different reasons.",
        "What stops a locale from silently missing a key?",
    )


# ---------------------------------------------------------------------------
def _data_qs(g: Guide) -> None:
    g.h1("Interview Questions: Data", page_break=True)

    g.qa(
        "46. Why a relational database at all?",
        "Because the human-in-the-loop pause means the draft must outlive the request "
        "that produced it.",
        "Revisions must be countable, the audit trail must be durable and append-only, "
        "and a traveller returning tomorrow must find their journey. The relationships "
        "between a trip, its result, its reviews, its messages and its audit events are "
        "genuinely relational, and cascade deletes are worth having the database "
        "enforce.",
        "Could you have used a document store?",
    )
    g.qa(
        "47. What decides whether something is a column or JSON?",
        "If the application filters, sorts or joins on it, it is a column. Otherwise it "
        "is JSON.",
        "Status, session id and dates are columns and indexed. Agent result payloads, "
        "the budget breakdown, the evaluation summary and audit detail are JSON, "
        "because they are read as a unit and their shape evolves. The cost is that you "
        "cannot ask the database which journeys had a flight over $800 without reading "
        "the payloads - accepted, because no such query exists.",
        "What would you do if that query became necessary?",
    )
    g.qa(
        "48. How do you run PostgreSQL in production and SQLite in tests?",
        "A JSONType that resolves to JSONB on PostgreSQL and JSON-encoded text "
        "elsewhere, and one module that normalises the URL and pool options.",
        "No model, repository or service branches on the vendor. The limit is honest: "
        "JSONB containment operators and GIN indexes do not exist on SQLite, so any "
        "future query using them is PostgreSQL-only.",
        "Does that mean your tests are not testing production behaviour?",
    )
    g.qa(
        "49. Why Neon rather than the hosting platform's PostgreSQL?",
        "Because the data's lifetime should not be coupled to the web service's.",
        "A host-managed free database typically shares the service's lifetime and often "
        "expires. Neon is reached only through DATABASE_URL, so the application has no "
        "idea who hosts it, and moving the application to another host requires no data "
        "migration. Compute scales to zero when idle.",
        "What does scaling to zero cost you?",
    )
    g.qa(
        "50. What does a serverless database change about your connection settings?",
        "Pre-ping, pool recycling, a generous connect timeout, an explicit SSL mode and "
        "a statement timeout.",
        "A pooled connection can be dead after the compute slept, so pre-ping checks it "
        "before use. Connections are recycled before an idle timeout can close them "
        "underneath the application. apply_ssl_mode adds TLS to the URL if it is "
        "missing rather than expecting every operator to remember. All of it is "
        "configuration, not hard-coded.",
        "How does that interact with your health endpoint?",
    )
    g.qa(
        "51. Why Alembic when create_all would produce the same tables?",
        "Because create_all is adequate exactly once - it cannot add a column to a "
        "table with rows, cannot rename, cannot backfill.",
        "Alembic gives the schema a history and lets any database report which revision "
        "it is at. CI validates it offline with `alembic upgrade head --sql`, which "
        "needs no database. At deploy time the entrypoint runs the upgrade before the "
        "server binds a port, so a failed migration fails the deployment rather than "
        "serving against an unexpected schema.",
        "Where is create_all still used, and why is that acceptable?",
    )


# ---------------------------------------------------------------------------
def _deploy_qs(g: Guide) -> None:
    g.h1("Interview Questions: Deployment", page_break=True)

    g.qa(
        "52. Describe your production image.",
        "Three stages - a Node builder, a Python builder, and a slim runtime that "
        "receives only the built artefacts.",
        "The runtime installs only libpq5 and curl, runs as a non-root user with uid "
        "10001, removes any environment file, VCS data and test cache in the final "
        "layer, and declares a HEALTHCHECK against the same cheap endpoint the platform "
        "probes. No compiler, no npm, no source toolchain ships.",
        "What is in the image that you wish were not?",
    )
    g.qa(
        "53. Why must you not hard-code the port?",
        "Because the platform assigns it, and binding 127.0.0.1 makes the container "
        "unreachable.",
        "The entrypoint reads PORT with a default of 8000 and starts uvicorn with "
        "--host 0.0.0.0 --port \"$PORT\". Both halves matter: the bind address and the "
        "port. The image defaults PORT to 8000 for local use only.",
        "Why does the entrypoint use exec?",
    )
    g.qa(
        "54. Why is exec important in the entrypoint?",
        "So the server becomes process 1 and receives termination signals directly.",
        "Without exec the shell stays as process 1 and does not forward signals, so the "
        "platform's graceful shutdown becomes a hard kill and in-flight requests are "
        "dropped.",
        "What else does the entrypoint do besides serve?",
    )
    g.qa(
        "55. How does deployment work, and why is CI a precondition?",
        "GitHub Actions posts a Render deploy hook, triggered by CI completing "
        "successfully on main.",
        "The Deploy workflow is triggered by the CI workflow's completion, not by a "
        "push, and it checks two conditions: the run must be on main and CI must have "
        "concluded successfully. A pull request cannot reach it. Manual dispatch is "
        "allowed on its own, for the case where an environment variable changed and the "
        "service needs a restart.",
        "What stops Render deploying on its own as well?",
    )
    g.qa(
        "56. How do you avoid deploying twice on every merge?",
        "autoDeploy: false in the blueprint, so GitHub Actions is the only path.",
        "If both Render's watcher and the workflow are active, every merge triggers two "
        "builds and two restarts that race. If the service was created by hand in the "
        "dashboard rather than from the blueprint, auto-deploy has to be switched off "
        "there manually - that is the most common way a pipeline ends up racing "
        "itself.",
        "How would you notice if it were happening?",
    )
    g.qa(
        "57. How do you keep the deploy hook out of the logs?",
        "It is read from the environment into curl and never echoed, interpolated or "
        "written to the summary.",
        "It exists only as the GitHub Actions secret RENDER_DEPLOY_HOOK_URL - not in "
        "git, not in the Render environment, not in any log line. The workflow inspects "
        "the response status and at most 400 bytes of the body, which can contain a "
        "service id but never the hook.",
        "What could still leak it?",
    )
    g.qa(
        "58. Why is LangSmith optional, and how is that enforced?",
        "Because tracing must never be the reason a traveller cannot get a plan.",
        "Every traced region goes through one span() function, which becomes a no-op "
        "context manager when tracing is disabled, unconfigured or the library is "
        "absent. Nothing in the domain layer imports the tracing library. The import "
        "goes through a seam so a broken library degrades rather than raising at import "
        "time, and tests assert a full journey completes both with and without it.",
        "What metadata do you actually send?",
    )


# ---------------------------------------------------------------------------
def _judgement_qs(g: Guide) -> None:
    g.h1("Interview Questions: Judgement", page_break=True)

    g.qa(
        "59. What is over-engineered in this project?",
        "MCP, if you only ever had one provider. And the ten evaluation dimensions are "
        "more than a first version needs.",
        "The right answer to this question is a real one. MCP's value is the choke "
        "point, and that value scales with the number of providers and agents; with one "
        "of each it is indirection for its own sake. The evaluation module would have "
        "been just as useful with five dimensions and could have grown.",
        "So why did you build them anyway?",
    )
    g.qa(
        "60. What is under-engineered?",
        "Concurrency, distributed rate limiting, caching, and authentication.",
        "The specialists run sequentially when three of them are independent. Rate "
        "limiting and metrics are in-process and silently wrong with more than one "
        "instance. There is no caching of provider results by destination and date, "
        "which is the obvious cost saving. And there is no authentication - a session "
        "id is not a credential.",
        "Which of those would you do first, and why that one?",
    )
    g.qa(
        "61. How would you scale this to a thousand concurrent users?",
        "Concurrency inside the specialists first, then shared rate limiting, then a "
        "connection pooler and provider caching.",
        "The graph itself scales without change because it is stateless between "
        "invocations - all state is in the checkpoint and the database, so any instance "
        "can resume any run. That property comes directly from ending the graph at "
        "human review rather than holding a run open. Everything else on the list is "
        "infrastructure, not architecture.",
        "What would you measure to know which one is actually the bottleneck?",
    )
    g.qa(
        "62. What is your test strategy, and what is not covered?",
        f"{FACTS.backend_test_count} backend test functions and "
        f"{len(FACTS.frontend_test_files)} frontend test files, weighted towards the "
        "parts where correctness is exact.",
        "Routing, preservation, tool authorization, guardrails, evaluation arithmetic "
        "and i18n parity are all asserted exactly. What is not covered: no load test, "
        "no penetration test, no browser end-to-end test, and the Docker image has "
        "never been built locally because Docker was unavailable in the development "
        "environment - the CI docker job is what proves it.",
        "Which uncovered area worries you most?",
    )
    g.qa(
        "63. What did you get wrong and have to fix?",
        "Several things, and the fixes are more interesting than the bugs.",
        "A PII pattern was redacting ISO dates as phone numbers, which silently removed "
        "the departure date - fixed with an explicit shape test. has_result treated an "
        "empty option list as a result, so a failed agent's emptiness was preserved "
        "across a revision - fixed with result markers. The CI secret scan matched its "
        "own regular expression and the test fixtures - fixed by requiring a realistic "
        "key body and de-literalising the fixtures. And a test injecting a fake tracing "
        "module broke an unrelated import - fixed with a load seam the test can patch.",
        "What do those four have in common?",
    )
    g.qa(
        "64. Where do you rely on an LLM, and where do you refuse to?",
        "Composition yes; arithmetic, routing, authorization and validation no.",
        "The itinerary agent is the one place a model's strengths are the right tool - "
        "composing a plausible, pleasant sequence of activities is a language task. "
        "Routing, budgeting, tool authorization, schema validation and most of the "
        "evaluation are deterministic, because those are places where a wrong answer is "
        "unambiguous and a rule gets it right every time.",
        "Is there anywhere you were tempted to use a model and decided not to?",
    )


# ---------------------------------------------------------------------------
def _closing(g: Guide) -> None:
    g.h1("Questions to Ask Them", page_break=True)
    g.p(
        "An interview is bidirectional, and the questions asked reveal as much as the "
        "answers given. These are drawn from decisions this project actually forced."
    )
    g.bullets([
        "How do you evaluate LLM features before they ship - and what stops a "
        "regression from reaching production?",
        "Where does human review sit in your agentic products, and is the pause "
        "durable or held in a request?",
        "How do you handle tool authorization for agents that can take actions with "
        "external consequences?",
        "How do you communicate uncertainty in model output to end users, if at all?",
        "What is your position on deterministic control flow around models versus "
        "letting a model route?",
        "How do you bound the cost of an agentic feature in production?",
    ])

    g.callout(
        "important",
        "Two habits worth carrying into the interview. First, never state a number you "
        "have not measured - \"not measured yet\" is a strong answer and an invented "
        "latency is a fatal one. Second, when asked what is wrong with the project, "
        "answer honestly and specifically; a candidate who can name the weakness in "
        "their own design is describing engineering judgement, not admitting failure.",
    )
