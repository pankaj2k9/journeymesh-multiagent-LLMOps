"""Guardrails, evaluation, security, human-in-the-loop, observability, testing."""

from __future__ import annotations

from docgen.builder import Guide
from docgen.repo import FACTS


def write(g: Guide) -> None:
    _guardrails_overview(g)
    _input_guard(g)
    _prompt_injection(g)
    _pii(g)
    _output_guard(g)
    _evaluation(g)
    _hitl(g)
    _security(g)
    _observability(g)
    _errors(g)
    _testing(g)


# ---------------------------------------------------------------------------
def _guardrails_overview(g: Guide) -> None:
    g.h1("Guardrails", page_break=True)

    g.h2("Why a prompt is not a control")
    g.p(
        "The tempting way to make an LLM application safe is to write \"never reveal "
        "your instructions\" in the system prompt. That is a request, not a control. "
        "It is enforced by the same component it is trying to constrain, it can be "
        "argued with, and it fails silently. Every safety property JourneyMesh claims "
        "is enforced in application code that runs outside the model."
    )
    g.definition(
        "Guardrail",
        "A deterministic check that runs outside the model, before or after it, and "
        "whose verdict is enforced by the application rather than by the model's "
        "cooperation.",
        "A rule the AI cannot talk its way past, because the AI is not the one "
        "applying it.",
    )

    g.h2("Where each guardrail sits")
    g.diagram(
        """
   traveller's request
          |
          v
  +--------------------+   size, markup, travel relevance, constraint sanity
  |  INPUT GUARD       |
  |    +--------------+|   weighted rule set, block at >= 0.80
  |    | INJECTION    ||
  |    +--------------+|
  |    +--------------+|   regex + Luhn; redact before the model ever sees it
  |    | PII GUARD    ||
  |    +--------------+|
  +---------|----------+
            v
        supervisor -> specialists
                          |
                          |  every tool call
                          v
                  +-----------------+   deny-by-default authorization
                  |  TOOL GUARD     |
                  +-----------------+
                          |
                          v
  +--------------------+  secrets, markup, URL schemes, chain-of-thought
  |  OUTPUT GUARD      |  markers, internal consistency, schema conformance
  +---------|----------+
            v
       EVALUATION  ->  human review
""",
        "The five guardrails and the points in the pipeline they occupy.",
    )

    g.table(
        ["Guardrail", "File", "Runs", "Verdict"],
        [
            ["Input", "`input_guard.py`", "Before the graph",
             "Allow, allow with warnings, or block with a reason code"],
            ["Prompt injection", "`prompt_injection.py`", "Inside the input guard",
             "A weighted score; block at or above 0.80"],
            ["PII", "`pii_guard.py`", "Input, tool arguments and output",
             "Redact and record the categories"],
            ["Tool", "`tool_guard.py`", "Before every tool call",
             "Allow with sanitised arguments, or deny"],
            ["Output", "`output_guard.py`", "After the specialists",
             "Allow, warn, or fail with named failures"],
        ],
        caption="The five guardrails.",
        widths=[1.0, 1.3, 1.3, 2.2],
    )

    g.callout(
        "note",
        "Every guardrail decision is appended to state['guardrail_results'] and "
        "surfaced to the interface. A traveller can see that a check ran and what it "
        "concluded; a reviewer can reconstruct why something was refused.",
    )


# ---------------------------------------------------------------------------
def _input_guard(g: Guide) -> None:
    g.h1("The Input Guard", page_break=True)

    g.p(
        "Pydantic has already established that the request is structurally valid. The "
        "input guard adds the semantic layer and produces one auditable decision "
        "object carrying the outcome, a reason code, a human-readable message, "
        "guidance, any warnings, the redaction categories, the sanitised query, the "
        "injection score and the rules that matched."
    )

    g.h2("The checks")
    g.table(
        ["Check", "Limit or rule", "Why"],
        [
            ["Query length", "`MAX_QUERY_LENGTH` = 4000 characters",
             "A prompt-stuffing attempt and an accidental paste look the same; both "
             "are refused early"],
            ["Travellers", "`MAX_TRAVELERS` = 20",
             "Beyond this it is not a trip, it is a tour operation"],
            ["Trip length", "`MAX_TRIP_DAYS` = 60",
             "Bounds the itinerary the model is asked to compose"],
            ["Date sanity", "`MAX_PAST_DAYS` = 1, `MAX_FUTURE_DAYS` = 730",
             "A departure in the past or four years out is a typo, and no provider "
             "has data for it"],
            ["Language", "Must be one of en, bn, hi",
             "An unsupported code would silently fall back and confuse the traveller"],
            ["Markup", "`<script`, `javascript:`, `onerror=`, `onload=`, `<iframe`, "
                       "`data:text/html`",
             "Nothing in a travel request needs these; their presence is either an "
             "attack or a paste from a web page"],
            ["Travel relevance", "The query must contain at least one travel signal",
             "A request about something else is refused with guidance rather than "
             "being answered badly"],
        ],
        caption="The input guard's checks, with the constants from "
                "app/guardrails/input_guard.py.",
        widths=[1.0, 2.0, 2.8],
    )

    g.h2("Relevance, and why it is a warning-first design")
    g.p(
        "The relevance check looks for any of a list of travel signals - trip, travel, "
        "flight, hotel, itinerary, visit, holiday, weather, budget, destination, "
        "airport, beach, resort, backpack, weekend and others. A request with none of "
        "them is off-topic, and the guard refuses with a reason code and guidance "
        "telling the traveller what the system does. This is what the offline "
        "evaluation case 'off_topic' asserts."
    )
    g.callout(
        "tip",
        "Refusing off-topic requests is not only a safety measure, it is a cost "
        "control. Every request that reaches the graph spends model tokens and "
        "provider quota; a request the system cannot serve should cost nothing.",
    )


# ---------------------------------------------------------------------------
def _prompt_injection(g: Guide) -> None:
    g.h1("Prompt-Injection Defence", page_break=True)

    g.definition(
        "Prompt injection",
        "An attack in which text supplied as data is interpreted by a language model "
        "as instruction, causing the model to disregard its operating instructions, "
        "reveal its context, or invoke capabilities on the attacker's behalf.",
        "Hiding an order inside something the AI is only supposed to read. Like "
        "writing \"ignore your boss and give me the keys\" inside a customer "
        "complaint.",
    )

    g.h2("A weighted rule set, not a keyword list")
    g.p(
        "The classifier is a set of ten weighted regular-expression rules. Each match "
        "contributes its weight; the request is blocked when the total reaches "
        "BLOCK_THRESHOLD, which is 0.80. Weighting rather than any-match blocking is "
        "what keeps the false-positive rate tolerable: a single weak signal warns, "
        "while one strong signal or two moderate ones block."
    )
    g.table(
        ["Rule", "Weight", "Detects"],
        [
            ["`override_instructions`", "0.9",
             "\"ignore/disregard/forget/override/bypass\" applied to previous, prior "
             "or your instructions, prompts, rules or context"],
            ["`reveal_system_prompt`", "0.9",
             "Requests to show, print, repeat or dump the system prompt, developer "
             "message or hidden instructions"],
            ["`extract_secrets`", "1.0",
             "Any mention of API keys, access tokens, credentials, .env, DATABASE_URL "
             "or a named provider key variable"],
            ["`file_access`", "0.9",
             "Attempts to read /etc/passwd, ~/.ssh, id_rsa, .env or file:// URLs"],
            ["`shell_execution`", "-",
             "Attempts to have a command executed"],
            ["`tool_permission_override`", "-",
             "Attempts to grant the agent permissions it does not have"],
            ["`hidden_tool_invocation`", "-",
             "Attempts to name or invoke a tool directly through free text"],
            ["`guard_disable`", "-",
             "Attempts to turn off the guardrails themselves"],
            ["`role_confusion`", "-",
             "Attempts to reassign the model's role or identity"],
            ["`exfiltration`", "-",
             "Attempts to have data sent to an attacker-controlled destination"],
        ],
        caption="The injection rule set from app/guardrails/prompt_injection.py. The "
                "four highest-weight rules are shown with their exact weights.",
        widths=[1.4, 0.6, 3.8],
    )

    g.h2("Enforcement is in the API layer")
    g.p(
        "The classifier returns a score, a blocked flag and the rules that matched. "
        "The verdict is enforced by the input guard and the route handler, which is "
        "the point: the model is never asked whether it thinks the request was an "
        "injection attempt. A blocked request produces a 400, an audit event and "
        "guidance for the traveller, and never reaches an agent."
    )
    g.callout(
        "warning",
        "No pattern-based classifier catches everything. This one is a first line, "
        "not a proof. The defence that actually bounds the damage is the Tool Guard: "
        "even a successful injection cannot make an agent call a tool it is not "
        "authorised for, exceed a call budget, or perform a write operation, because "
        "those decisions are made outside the model entirely.",
    )


# ---------------------------------------------------------------------------
def _pii(g: Guide) -> None:
    g.h1("Personal Data Protection", page_break=True)

    g.p(
        "A travel planner is a natural place for people to type passport numbers and "
        "card details. JourneyMesh does not want them, does not need them, and takes "
        "active steps to make sure they never reach a model, a provider, a log, a "
        "trace or the database."
    )

    g.h2("What is detected")
    g.table(
        ["Category", "Detected by", "Replaced with"],
        [
            ["Credit card", "A digit pattern validated with the Luhn checksum",
             "A card placeholder"],
            ["Passport", "\"passport\" plus a one-or-two-letter, six-to-nine-digit "
                         "identifier", "A passport placeholder"],
            ["National id", "nid, national id, aadhaar or ssn plus a digit run",
             "A national-id placeholder"],
            ["Bank account", "An IBAN-shaped token", "A bank placeholder"],
            ["Email", "A standard address pattern", "An email placeholder"],
            ["Phone", "An international-format digit run, after a shape test",
             "A phone placeholder"],
            ["Credential", "sk / gsk / pk / tvly / api / key / token / bearer "
                           "followed by a long token", "A credential placeholder"],
        ],
        caption="PII categories, from app/guardrails/pii_guard.py.",
        widths=[1.1, 2.9, 1.8],
    )

    g.h2("Precision matters more than recall here")
    g.p(
        "An over-eager redactor is worse than useless: it destroys the request. Two "
        "specific defences exist because of real defects found during development."
    )
    g.numbered([
        "The Luhn checksum. A sixteen-digit number is only treated as a card if it "
        "passes the checksum every real card number satisfies. A booking reference or "
        "a flight number that happens to be sixteen digits does not.",
        "The phone shape test. `_looks_like_phone` explicitly rejects anything "
        "matching an ISO date - the pattern `\\d{4}-\\d{2}-\\d{2}` - and anything with "
        "fewer than nine digits. Without it, \"2026-11-10\" was being redacted as a "
        "phone number, which removed the departure date from the request.",
    ])

    g.h2("Where redaction happens")
    g.table(
        ["Point", "Function", "Effect"],
        [
            ["Before the model", "`sanitize_for_model()`",
             "The model receives redacted text; the original never leaves the "
             "process"],
            ["Before a tool call", "The Tool Guard calls the PII guard",
             "Arguments are redacted before dispatch, and the categories are recorded "
             "on the decision"],
            ["On the way out", "`sanitize_payload()`",
             "The assembled response is walked recursively and any personal data is "
             "removed before it is stored or returned"],
        ],
        caption="The three redaction points.",
        widths=[1.2, 1.7, 2.9],
    )

    g.h2("Document hints")
    g.p(
        "Some phrases signal a travel-document conversation even without a matching "
        "number - \"passport number\", \"visa number\", \"national id\", \"driving "
        "licence\", \"credit card\", \"cvv\", \"bank account\", \"routing number\". "
        "`mentions_travel_documents()` detects these so the system can warn a "
        "traveller that it does not want that information, rather than waiting for "
        "them to type it."
    )

    g.callout(
        "important",
        "Only the redaction categories are recorded - never the value, never a partial "
        "value, never a hash of one. The audit trail says \"a card number was "
        "removed\", which is everything an operator needs and nothing an attacker "
        "could use.",
    )


# ---------------------------------------------------------------------------
def _output_guard(g: Guide) -> None:
    g.h1("The Output Guard", page_break=True)

    g.p(
        "The output guard runs after JSON parsing and Pydantic validation and "
        "immediately before evaluation. It answers one question: is this response "
        "structurally complete, internally consistent, free of secrets, free of unsafe "
        "markup and free of personal data nobody asked for?"
    )

    g.table(
        ["Check", "Looks for", "Outcome"],
        [
            ["Secret leakage",
             "`gsk_`, `sk-`, `tvly-` style keys with a realistic body; "
             "`postgres://` and `postgresql://` URLs; named provider key variables; "
             "`DATABASE_URL=`",
             "Blocking failure"],
            ["Unsafe markup",
             "`<script`, `<iframe`, `javascript:`, `onerror=`, `onload=`, "
             "`onclick=`, `data:text/html`",
             "Blocking failure"],
            ["URL scheme policy",
             "`ftp://`, `file://`, `data://`; only http and https are permitted",
             "Blocking failure"],
            ["Reasoning leakage",
             "Chain-of-thought markers that indicate model reasoning has been "
             "included in user-facing content",
             "Failure"],
            ["Internal consistency",
             "Dates that contradict the request, totals that contradict the "
             "breakdown, an itinerary longer than the trip",
             "Warning or failure depending on severity"],
            ["Schema conformance",
             "The assembled payload validates against the response models",
             "Blocking failure"],
        ],
        caption="The output guard's checks.",
        widths=[1.2, 3.2, 1.4],
    )

    g.h2("Why a secret check on the way out")
    g.p(
        "The application never puts a key into a response. The check exists because "
        "the response contains model-composed text, and a model that was shown "
        "something it should not have been shown can repeat it. This is defence in "
        "depth against a failure elsewhere, and it is cheap: a handful of compiled "
        "patterns over a payload that is about to be serialised anyway."
    )
    g.callout(
        "note",
        "These same patterns are used by the CI secret scan, and they had to be "
        "tightened during development: an early version matched the literal string "
        "`gsk_` in a test fixture and in its own source. The patterns now require a "
        "realistic key body, and the scan excludes the workflow files, the compose "
        "files and the test directory.",
    )

    g.h2("What a failure does")
    g.p(
        "A blocking failure records an OUTPUT_VALIDATION_FAILED audit event and adds a "
        "system message to the conversation. The journey is not silently discarded and "
        "the traveller is not shown a raw error: the failure is visible in the "
        "guardrail panel, and the evaluation that follows treats schema_validity and "
        "safety as blocking dimensions."
    )


# ---------------------------------------------------------------------------
def _evaluation(g: Guide) -> None:
    g.h1("Evaluation", page_break=True)

    g.h2("Why measure at all")
    g.p(
        "Without measurement, \"the output got better\" is an opinion. The evaluation "
        "module turns a draft journey into a set of numbers that can be compared "
        "between runs, asserted in tests, and shown to the traveller alongside the "
        "journey itself."
    )

    g.h2("Deterministic first")
    g.p(
        "The design rule is that anything checkable by rule is checked by rule. A "
        "model is only asked for an opinion on the parts that are genuinely matters of "
        "judgement, and only when EVALUATION_MODE permits it. Arithmetic, dates, "
        "schema conformance, tool authorisation and language are facts; nobody needs "
        "a language model to establish whether a budget adds up."
    )
    g.table(
        ["Mode", "Behaviour", "Used in"],
        [
            ["`deterministic`", "Rules only. Reproducible, free, fast.",
             "CI, the offline suite, and the default configuration"],
            ["Judge-enabled", "Rules first, then an optional model opinion layered "
                              "on top.",
             "Local experimentation where a key is configured"],
        ],
        caption="Evaluation modes.",
        widths=[1.2, 2.6, 2.0],
    )

    g.h2("The ten dimensions")
    g.table(
        ["Dimension", "Weight", "Asks", "Checked by"],
        [
            ["`safety`", "2.0", "Does the output contain anything it must not?",
             "Rule - blocking"],
            ["`groundedness`", "1.5",
             "Is every claim traceable to a tool result or a labelled estimate?",
             "Rule"],
            ["`schema_validity`", "1.5", "Does the payload match the response models?",
             "Rule - blocking"],
            ["`budget_consistency`", "1.3",
             "Do the components sum to the stated total, and is the status correct?",
             "Rule"],
            ["`completeness`", "1.2",
             "Did every selected agent produce a usable result?", "Rule"],
            ["`consistency`", "1.2",
             "Do the dates, durations and locations agree with each other?", "Rule"],
            ["`itinerary_feasibility`", "1.2",
             "Does the plan fit the days, the arrival and the departure?", "Rule"],
            ["`relevance`", "1.0", "Does the journey answer the request that was "
                                   "made?", "Rule, optional judge"],
            ["`tool_correctness`", "0.8",
             "Were the right tools called, by the right agents, within budget?",
             "Rule"],
            ["`language_correctness`", "0.8",
             "Is the response in the language that was asked for?", "Rule"],
        ],
        caption="DIMENSIONS and DIMENSION_WEIGHTS from "
                "app/evaluation/schemas.py.",
        widths=[1.4, 0.6, 2.6, 1.2],
    )

    g.h2("How the score is computed")
    g.p(
        "Each check produces a score and an outcome of pass, warn, fail or skipped. "
        "Skipped checks are excluded entirely. The checks belonging to a dimension are "
        "averaged to give that dimension's score, and the overall score is the "
        "weighted mean of the dimension scores using the weights above. Weighting by "
        "dimension rather than by check means adding a third safety check does not "
        "silently make safety count three times as much."
    )
    g.code(
        """
def overall_score(checks: Iterable[EvaluationCheck]) -> float:
    \"\"\"Weighted mean across dimensions, using the configured dimension weights.\"\"\"
    scores = dimension_scores(checks)
    if not scores:
        return 0.0
    weighted = sum(
        score * DIMENSION_WEIGHTS.get(dimension, 1.0)
        for dimension, score in scores.items()
    )
    total_weight = sum(DIMENSION_WEIGHTS.get(dimension, 1.0) for dimension in scores)
    return round(weighted / total_weight, 3) if total_weight else 0.0
""",
        caption="Listing. Score aggregation, from app/evaluation/metrics.py.",
    )

    g.h2("Blocking dimensions")
    g.p(
        "safety and schema_validity are blocking. A failure in either is reported by "
        "`blocking_failures()` and means the journey should not be shown at all, "
        "regardless of how well it scored elsewhere. Everything else degrades the "
        "score rather than stopping the response."
    )

    g.h2("The offline suite")
    g.p(
        f"backend/evals/cases.json holds {len(FACTS.eval_cases)} cases, each declaring "
        "the agents it expects to run, the agents that must not run, whether it should "
        "be blocked, the language it expects and a minimum score. `make eval` runs "
        "them; CI runs them on every push."
    )
    g.table(
        ["Case", "Asserts"],
        [
            ["`full_family_trip`", "All five specialists run and the journey is "
                                   "complete"],
            ["`weather_only`", "Only the weather agent runs - the supervisor does not "
                               "over-select"],
            ["`cheaper_hotel_revision`",
             "A revision re-runs hotel, budget and itinerary, and the flight results "
             "are preserved unchanged"],
            ["`bengali_response`", "The response renders in Bengali"],
            ["`hindi_response`", "The response renders in Hindi"],
            ["`prompt_injection`", "The request is blocked before any agent runs"],
            ["`off_topic`", "A non-travel request is refused with guidance"],
            ["`invalid_dates`", "An impossible date range is rejected by the input "
                                "guard"],
        ],
        caption="The offline evaluation cases, read from backend/evals/cases.json.",
        widths=[1.5, 4.3],
    )
    g.callout(
        "important",
        "These cases run in deterministic mode with no provider keys, so they produce "
        "the same result every time. That is what makes them a regression gate rather "
        "than a weather report.",
    )

    g.understand([
        "Why a prompt instruction is not a safety control.",
        "The ten dimensions, their weights, and why weighting is per dimension.",
        "Which two dimensions are blocking and what that means.",
        "Why the offline suite runs without any provider key.",
    ])


# ---------------------------------------------------------------------------
def _hitl(g: Guide) -> None:
    g.h1("Human in the Loop", page_break=True)

    g.h2("The premise")
    g.p(
        "JourneyMesh never presents a plan as final. Every draft stops at a review, "
        "and the traveller does one of two things: approve it, or say what should "
        "change. This is not a courtesy - it is the design's answer to the fact that "
        "an LLM system can be confidently wrong, and that a person is the cheapest and "
        "most reliable detector of \"that is not what I meant\"."
    )

    g.h2("The two decisions")
    g.table(
        ["Decision", "Endpoint", "What happens"],
        [
            ["Approve", "`POST /api/v1/trips/{id}/approve`",
             "review_status becomes approved, trip_status becomes approved, the graph "
             "resumes on the finalise branch and the final response agent renders the "
             "journey in the chosen language"],
            ["Request changes", "`POST /api/v1/trips/{id}/request-changes`",
             "revision_count increases, review_status becomes changes_requested, the "
             "graph resumes on the revise branch and the supervisor selects only the "
             "affected agents"],
        ],
        caption="The two human decisions and their consequences.",
        widths=[1.0, 1.9, 2.9],
    )

    g.h2("Review states")
    g.table(
        ["State", "Meaning"],
        [
            ["`pending`", "Created, not yet drafted"],
            ["`awaiting_review`", "A draft exists and a person must decide"],
            ["`changes_requested`", "A change was asked for and is being applied"],
            ["`revision_in_progress`", "A revision run is executing"],
            ["`approved`", "Finalised and rendered"],
            ["`revision_limit_reached`", "MAX_REVISION_COUNT was reached"],
        ],
        caption="Review states, from app/core/constants.py.",
        widths=[1.5, 4.3],
    )

    g.h2("The revision ceiling")
    g.p(
        "MAX_REVISION_COUNT defaults to 3. When it is reached the workflow records a "
        "REVISION_LIMIT_REACHED audit event, sets the review status accordingly and "
        "stops offering further changes. The interface shows the remaining budget "
        "before it runs out, so the limit is never a surprise. This bounds both cost "
        "and the possibility of an endless refinement loop."
    )

    g.h2("What makes this different from a chat interface")
    g.p(
        "In a chat interface, \"make the hotels cheaper\" produces an entirely new "
        "answer, and whether the flights survived is a matter of luck. Here the "
        "request is analysed into an agent set, the dependency closure is computed, "
        "explicit preservation requests are honoured, and the untouched results are "
        "carried forward byte for byte. The traveller keeps what they already agreed "
        "to."
    )


# ---------------------------------------------------------------------------
def _security(g: Guide) -> None:
    g.h1("Security", page_break=True)

    g.h2("Secrets")
    g.bullets([
        "Secrets exist only in the environment. Nothing is read from a file the "
        "application ships, and `.env` is git-ignored.",
        "`.env.example` documents every variable with an empty value. It is a "
        "template, not a configuration.",
        "No API key is ever written to the database. Provider configuration is "
        "reported as configured or not configured, never as a value.",
        "The React bundle receives no secret. Every `VITE_` variable is public by "
        "construction and is treated as such.",
        "The Render deploy hook exists only as a GitHub Actions secret named "
        "`RENDER_DEPLOY_HOOK_URL`. It is never committed and never printed in full.",
        "CI fails if an environment file is committed or if a credential-shaped "
        "string appears in the repository.",
    ])

    g.h2("HTTP security headers")
    g.table(
        ["Header", "Value and reason"],
        [
            ["Content-Security-Policy",
             "Restricts sources for scripts, styles, images and connections. The only "
             "inline script permitted is the theme initialiser, allowlisted by its "
             "exact SHA-256 hash rather than by 'unsafe-inline'"],
            ["X-Frame-Options / frame-ancestors",
             "The application may not be framed, which removes clickjacking"],
            ["X-Content-Type-Options",
             "`nosniff`, so a response is never re-interpreted as a different type"],
            ["Referrer-Policy",
             "Limits what is sent to third parties on navigation"],
            ["Server",
             "Removed. The framework banner tells an attacker what to target and "
             "tells a user nothing"],
        ],
        caption="Response headers set by SecurityHeadersMiddleware.",
        widths=[1.5, 4.3],
    )

    g.h2("Rate limiting")
    g.p(
        "A fixed window per client, configured by RATE_LIMIT_REQUESTS and "
        "RATE_LIMIT_WINDOW_SECONDS, defaulting to 60 requests per 60 seconds. It is "
        "in-process, which is correct and sufficient for a single-container "
        "deployment and is stated as a limitation rather than disguised: a "
        "multi-instance deployment needs a shared store."
    )

    g.h2("Request size")
    g.p(
        "MAX_REQUEST_SIZE bounds the body before it is parsed. This runs before the "
        "rate limiter so that an oversized body is discarded without consuming a "
        "rate-limit slot, and before Pydantic so that a very large payload is never "
        "materialised into Python objects."
    )

    g.h2("Audit trail")
    g.p(
        "app/security/audit.py appends structured events to audit_events. Every event "
        "carries a type, a severity, an actor, an optional trip id, the request id and "
        "a JSON detail object. The detail object holds rule names, tool names and "
        "agent names - never argument values, never redacted content, never a secret."
    )

    g.h2("What is deliberately not claimed")
    g.bullets([
        "There is no authentication and no authorisation between users. Journeys are "
        "scoped by an opaque session id, which is not a credential.",
        "The prompt-injection classifier is a first line, not a proof.",
        "In-process rate limiting does not survive horizontal scaling.",
        "No penetration test has been performed. Not measured yet.",
    ])


# ---------------------------------------------------------------------------
def _observability(g: Guide) -> None:
    g.h1("Observability", page_break=True)

    g.h2("Structured logging")
    g.p(
        "Logs are JSON in production and human-readable in development, controlled by "
        "LOG_FORMAT. Every line carries the request id attached by "
        "RequestContextMiddleware, so a single traveller's request can be followed "
        "across middleware, service, graph, agent and tool."
    )

    g.h2("Metrics")
    g.p(
        "app/observability/metrics.py keeps in-process counters - requests, model "
        "calls, tool calls, guardrail decisions, provider failures - exposed through "
        "the verbose health endpoint. They reset when the process restarts, which is "
        "stated plainly: they are a snapshot for an operator, not a time series."
    )

    g.h2("Tracing, and the single integration point")
    g.p(
        "Every traced region in the codebase goes through `span()` in "
        "app/observability/tracing.py. That is the only place that knows LangSmith "
        "exists. If tracing is disabled, unconfigured, or the library is absent, "
        "`span()` becomes a no-op context manager and the application behaves "
        "identically."
    )
    g.code(
        """
with span("Output Guard", kind="guardrail", stage="output"):
    decision = output_guard.check_payload(payload, constraints=constraints)
""",
        caption="Listing. Every traced region has this shape. Nothing in the domain "
                "layer imports LangSmith.",
    )
    g.callout(
        "important",
        "LangSmith is never a hard runtime dependency for generating a trip. A missing "
        "key, an unreachable endpoint or an uninstalled library must not fail a "
        "journey - and a test asserts exactly that.",
    )

    g.h2("Sanitised metadata")
    g.p(
        "`sanitize_metadata()` in app/observability/langsmith.py applies an allowlist "
        "to everything sent to the tracing service, redacts personal data, and "
        "truncates long values. Trip identifiers, agent names, revision numbers and "
        "durations are sent; the traveller's free text, tool arguments and provider "
        "payloads are not."
    )
    g.table(
        ["Sent to LangSmith", "Not sent"],
        [
            ["Trip id, revision number, request id",
             "The traveller's free-text query"],
            ["Agent names and the selected agent set", "Tool arguments"],
            ["Node names and durations", "Provider response payloads"],
            ["Guardrail rule names and outcomes", "Any redacted value"],
            ["Evaluation dimension names", "Any environment variable"],
        ],
        caption="The tracing allowlist.",
        widths=[2.9, 2.9],
    )

    g.h2("Run naming")
    g.p(
        "Runs are named \"JourneyMesh Trip Planning - Revision N\", so a revision is "
        "distinguishable from the draft it came from at a glance in the trace list. "
        "That naming is applied by `_trace_config()` on the workflow."
    )


# ---------------------------------------------------------------------------
def _errors(g: Guide) -> None:
    g.h1("Error Handling and Degradation", page_break=True)

    g.h2("The principle")
    g.p(
        "A travel planner that fails entirely because one provider is down is worse "
        "than one that says \"I could not price the flights, here is everything "
        "else, and here is what is an estimate\". Every external dependency in "
        "JourneyMesh has a defined degraded state, and the system's job is to be "
        "explicit about which one it is in."
    )

    g.table(
        ["Failure", "Degraded behaviour", "Visible as"],
        [
            ["No model key configured",
             "Deterministic mode: agents produce structured results from tools and "
             "reference data",
             "`llm: deterministic` on the health endpoint"],
            ["Model call fails",
             "The agent records the error and returns what it has",
             "An entry in `state['errors']` and a warning in the guardrail panel"],
            ["A travel provider is unreachable",
             "Reference data is used and the result is labelled ESTIMATE",
             "An ESTIMATE badge beside the value"],
            ["No provider data at all",
             "The section is labelled UNAVAILABLE rather than filled with a guess",
             "An UNAVAILABLE badge and an empty state"],
            ["MCP SDK not installed",
             "In-process adapters run the same tool functions",
             "The MCP transport reported as in-process"],
            ["A tool exceeds its call budget",
             "The call is refused and the agent proceeds",
             "A TOOL_CALL_BLOCKED audit event"],
            ["LangSmith unavailable",
             "`span()` is a no-op; the journey completes normally",
             "Nothing - by design"],
            ["Database unreachable at start-up",
             "Start-up fails loudly rather than serving a broken service",
             "A failed deployment"],
            ["A migration fails",
             "The entrypoint stops before the server binds a port",
             "A failed deployment, with the migration error in the logs"],
        ],
        caption="Every failure mode and its defined degradation.",
        widths=[1.4, 2.5, 1.9],
    )

    g.h2("Errors that are not degraded")
    g.p(
        "Two classes of failure are deliberately hard. A guardrail block is a refusal, "
        "not a degradation - the request does not proceed in a weakened form. And a "
        "failed migration stops the deployment, because serving an application against "
        "a schema it does not expect is the one failure mode that can corrupt data "
        "rather than merely disappoint a traveller."
    )


# ---------------------------------------------------------------------------
def _testing(g: Guide) -> None:
    g.h1("Testing", page_break=True)

    g.p(
        f"The backend has {FACTS.backend_test_count} test functions across "
        f"{len(FACTS.backend_test_files)} files; the frontend has "
        f"{len(FACTS.frontend_test_files)} test files. Parametrised tests expand to "
        "more executed cases than there are functions."
    )

    g.h2("What is tested, and how")
    g.table(
        ["Area", "Approach"],
        [
            ["Supervisor routing",
             "Dozens of phrasings pinned to their expected agent set. This is a pure "
             "function of a string, so the assertions are exact"],
            ["Selective re-execution",
             "A revision is run and the preserved agent's payload is compared before "
             "and after for equality"],
            ["Tool Guard",
             "Each of the seven checks has a case that triggers it, plus a case for "
             "an unregistered tool being denied by default"],
            ["Guardrails",
             "Injection strings, PII strings, oversized bodies, unsafe markup and "
             "off-topic requests, each with the expected reason code"],
            ["Evaluation",
             "Every rule is exercised on a state that should pass and one that should "
             "fail, and the weighting arithmetic is asserted directly"],
            ["API routes",
             "FastAPI's TestClient against an ephemeral SQLite backend"],
            ["Observability",
             "Tracing is asserted to be a no-op when disabled, and metadata "
             "sanitisation is asserted on a payload containing PII"],
            ["Frontend components",
             "Testing Library renders BudgetSection, PlannerForm and ReviewPanel and "
             "queries them the way a user would"],
            ["Theme",
             "The provider, the toggle, persistence, the pre-paint script and a "
             "coverage test that scans the compiled CSS for both palettes"],
            ["i18n",
             "Catalogue parity: every key English defines must exist in Bengali and "
             "Hindi"],
        ],
        caption="Test coverage by area.",
        widths=[1.4, 4.4],
    )

    g.h2("Two tests worth describing")
    g.h3("The theme coverage test")
    g.p(
        "This test reads the compiled CSS from disk and asserts that both the light "
        "and the dark value of every token are present, and that no component has "
        "reintroduced a literal Tailwind colour. It reads from disk with node:fs "
        "rather than importing the stylesheet, because Vitest does not process CSS "
        "imports and the raw import returned an empty string."
    )
    g.callout(
        "note",
        "Its class-name pattern needed a negative lookahead so that JourneyMesh's own "
        "semantic `neutral-fg`, `neutral-bg` and `neutral-line` tokens are not "
        "mistaken for Tailwind's literal `neutral` palette.",
    )

    g.h3("The preservation regression test")
    g.p(
        "This is the test that protects the system's most distinctive behaviour. It "
        "plans a journey, requests \"cheaper hotels under $100, keep my flights\", and "
        "asserts three things: that hotel, budget and itinerary re-ran; that the "
        "flight agent did not; and that the flight payload is identical to the one "
        "from the first pass."
    )

    g.h2("Running them")
    g.table(
        ["Command", "Runs"],
        [
            ["`make test`", "Backend and frontend suites"],
            ["`make backend-test`", "pytest"],
            ["`make frontend-test`", "Vitest"],
            ["`make lint`", "ruff"],
            ["`make typecheck`", "`tsc --noEmit`"],
            ["`make eval`", "The offline evaluation suite"],
            ["`make verify`", "Everything above plus a production build"],
        ],
        caption="Test commands.",
        widths=[1.6, 4.2],
    )
