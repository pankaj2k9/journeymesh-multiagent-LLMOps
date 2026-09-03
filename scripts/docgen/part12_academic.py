"""The academic term-project chapter."""

from __future__ import annotations

from docgen.builder import Guide
from docgen.repo import FACTS


def write(g: Guide) -> None:
    _intro(g)
    _abstract(g)
    _literature(g)
    _methodology(g)
    _implementation(g)
    _results(g)
    _limitations(g)
    _future(g)
    _conclusion(g)


# ---------------------------------------------------------------------------
def _intro(g: Guide) -> None:
    g.h1("Academic Term Project Report", page_break=True)
    g.p(
        "This chapter presents JourneyMesh in the structure expected of a university "
        "term project or dissertation chapter. It is written so that the sections can "
        "be adapted directly into a report, and it is deliberate about what it does "
        "and does not claim: where a result would require measurement that has not "
        "been performed, it says so."
    )
    g.callout(
        "important",
        "Academic honesty is not optional and is not a formality. No latency, "
        "accuracy, user-study or performance figure appears in this chapter, because "
        "none has been measured. \"Not measured yet\" is the correct entry, and an "
        "invented number would invalidate the report it appeared in.",
    )


# ---------------------------------------------------------------------------
def _abstract(g: Guide) -> None:
    g.h1("Abstract", page_break=True)
    g.p(
        "Large language models produce fluent travel plans that may be confidently "
        "wrong about prices, schedules and availability, and that cannot be partially "
        "revised: asking for one change regenerates everything. This project presents "
        "JourneyMesh, a multilingual multi-agent travel-planning system that addresses "
        "both problems through architecture rather than prompting. A supervisor agent "
        "selects specialist agents at run time from the content of a request; the "
        "selected agents execute in dependency order over a shared typed state within a "
        "LangGraph state machine. All external capability is reached through the Model "
        "Context Protocol behind a deny-by-default authorization guard that validates "
        "the calling agent, the argument schema, the operation class and a per-run call "
        "budget. Every value carries a provenance label distinguishing live provider "
        "data from search-derived values, system estimates and unavailable data, and "
        "this label is surfaced in the interface. The workflow terminates at a human "
        "review node and persists its state to a checkpoint store, so the pause between "
        "a draft and a human decision survives process termination. On a revision, the "
        "supervisor analyses the requested change into an agent set, closes that set "
        "over a declared dependency relation, and subtracts agents the user explicitly "
        "asked to preserve; untouched results are carried forward unchanged. Draft "
        "output is screened by output guardrails and scored across ten weighted "
        "dimensions using deterministic rules, with an optional model judge. The system "
        "is implemented as a React and TypeScript interface over a Python and FastAPI "
        "service with PostgreSQL persistence, supports English, Bengali and Hindi, and "
        "is deployed as a single container image through a continuous integration "
        "pipeline. Functional correctness is established by an automated test suite and "
        "a deterministic offline evaluation suite; performance characteristics have not "
        "been measured and are identified as future work."
    )

    g.h2("Keywords")
    g.p(
        "Agentic AI; multi-agent systems; large language models; LangGraph; Model "
        "Context Protocol; AI guardrails; prompt injection; LLM evaluation; "
        "human-in-the-loop; selective re-execution; data provenance; multilingual "
        "systems; LLMOps."
    )


# ---------------------------------------------------------------------------
def _literature(g: Guide) -> None:
    g.h1("Background and Related Work", page_break=True)

    g.h2("From prompting to agency")
    g.p(
        "The progression in LLM application design is from a single prompt, to a chain "
        "of prompts, to a model with tools, to a system of coordinated agents. Each "
        "step trades simplicity for control. A single prompt has no actions. A chain "
        "has actions in a fixed order chosen by the programmer. A tool-calling agent "
        "chooses its own actions but owns both domain reasoning and control flow. A "
        "supervised multi-agent system separates the two, which is the position "
        "JourneyMesh takes."
    )

    g.h2("Themes this project draws on")
    g.table(
        ["Theme", "Established position", "How JourneyMesh applies it"],
        [
            ["Task decomposition",
             "Complex tasks are more reliably handled by decomposition than by a "
             "single monolithic instruction",
             "Five specialists, each with a small prompt and one owned state key"],
            ["Orchestration as a state machine",
             "Graph-based orchestration with persistence supports branching, pausing "
             "and resumption that linear chains cannot",
             "A LangGraph StateGraph with a conditional entry edge and a checkpointer"],
            ["Tool use protocols",
             "Standardising tool exposure decouples capability from application code",
             "MCP servers with typed schemas, reached through one client"],
            ["Guardrails",
             "Safety properties enforced by prompt instruction are unreliable; "
             "enforcement belongs outside the model",
             "Five guardrails implemented as deterministic application code"],
            ["Prompt injection",
             "Instruction-data confusion is a recognised class of attack against "
             "LLM applications",
             "A weighted classifier before the model, and a tool guard that bounds "
             "the consequence of a bypass"],
            ["Evaluation of generative systems",
             "Reference-free, rubric-based scoring is used where ground truth is "
             "unavailable; LLM-as-judge is common but non-deterministic",
             "Ten dimensions, deterministic rules first, an optional judge second"],
            ["Human oversight",
             "Human review is the standard control where model output has real-world "
             "consequences",
             "A mandatory review before any plan is final, with bounded revisions"],
            ["Provenance and uncertainty",
             "Communicating the source and confidence of generated content is "
             "necessary for calibrated user trust",
             "Four provenance labels, applied per value and shown in the interface"],
        ],
        caption="Themes from the literature and their concrete application here.",
        widths=[1.1, 2.4, 2.3],
    )

    g.h2("Gap addressed")
    g.p(
        "Multi-agent frameworks are well documented, and human-in-the-loop review is "
        "widely discussed. What is less commonly addressed is what should happen after "
        "the human speaks. Most systems treat a change request as a new request. "
        "JourneyMesh treats it as a scoped invalidation over a declared dependency "
        "graph, with explicit user preservation, and verifies the resulting stability "
        "by asserting byte-level equality of preserved output in an automated test. "
        "That combination - dependency-scoped re-execution with user-directed "
        "preservation, verified rather than asserted - is the contribution of this "
        "project."
    )


# ---------------------------------------------------------------------------
def _methodology(g: Guide) -> None:
    g.h1("Methodology", page_break=True)

    g.h2("Research questions")
    g.numbered([
        "Can a supervisor selecting specialists from request content reduce "
        "unnecessary work relative to always executing every agent, in a way that can "
        "be asserted deterministically?",
        "Can a change request be scoped so that only the affected agents re-run, while "
        "results the user asked to keep are preserved exactly?",
        "Can safety properties of an LLM application be enforced outside the model in "
        "a way that is testable case by case?",
        "Can the quality of generated output be measured deterministically enough to "
        "gate a continuous integration pipeline?",
    ])

    g.h2("Design method")
    g.p(
        "The project follows a design-science approach: an artefact is constructed to "
        "address an identified problem, and the artefact is evaluated against criteria "
        "derived from that problem. The criteria here are functional and verifiable "
        "rather than statistical - each research question above maps to assertions in "
        "the automated test suite and cases in the offline evaluation suite."
    )

    g.table(
        ["Research question", "Evaluation method", "Artefact that answers it"],
        [
            ["Q1 - selective execution",
             "Assert the selected agent set for a corpus of request phrasings",
             "Supervisor routing tests; the `weather_only` evaluation case"],
            ["Q2 - scoped revision",
             "Run a revision and compare the preserved agent's payload before and "
             "after for equality",
             "The preservation regression test; the `cheaper_hotel_revision` "
             "evaluation case"],
            ["Q3 - external enforcement",
             "Assert that each guardrail rule produces the expected refusal, and that "
             "an unregistered tool is denied",
             "Guardrail and tool-guard tests; the `prompt_injection` and `off_topic` "
             "cases"],
            ["Q4 - deterministic scoring",
             "Run the offline suite twice with no provider keys and require identical "
             "scores",
             "The offline evaluation runner, executed in CI"],
        ],
        caption="Research questions mapped to evaluation method and artefact.",
        widths=[1.3, 2.2, 2.3],
    )

    g.h2("System design method")
    g.numbered([
        "Domain decomposition. Identify the information domains of travel planning and "
        "the dependencies between them, and encode those dependencies explicitly "
        "rather than implicitly in an execution order.",
        "State design. Define a single shared state with one owner per result key, so "
        "that preservation is well defined.",
        "Control-flow placement. Place every decision that can be made deterministically "
        "in application code, and reserve the model for composition.",
        "Boundary placement. Identify each point where untrusted input enters or a "
        "consequential action leaves, and place a deterministic check there.",
        "Measurement design. Define the quality dimensions before implementing the "
        "agents, so the agents are built against a stated standard.",
        "Verification. Encode each design claim as an executable assertion, so that "
        "the claim cannot silently become false.",
    ])

    g.h2("Tools and technologies")
    g.table(
        ["Layer", "Technology"],
        [
            ["Interface", "React 18, TypeScript, Vite, React Router, TanStack Query, "
                          "Tailwind CSS, i18next"],
            ["Service", "Python, FastAPI, Pydantic v2, pydantic-settings, Uvicorn"],
            ["Orchestration", "LangGraph, LangChain core"],
            ["Model access", "langchain-groq"],
            ["Tools", "Model Context Protocol SDK, langchain-mcp-adapters"],
            ["Persistence", "SQLAlchemy 2.0, Alembic, PostgreSQL (Neon), SQLite for "
                            "tests"],
            ["Observability", "Structured logging, in-process metrics, optional "
                              "LangSmith tracing"],
            ["Quality", "pytest, pytest-asyncio, ruff, Vitest, React Testing Library, "
                        "TypeScript compiler"],
            ["Delivery", "Docker multi-stage build, Docker Compose, GitHub Actions, "
                         "Render"],
        ],
        caption="Technology stack by layer.",
        widths=[1.2, 4.6],
    )


# ---------------------------------------------------------------------------
def _implementation(g: Guide) -> None:
    g.h1("Implementation", page_break=True)

    g.h2("Scale of the artefact")
    g.table(
        ["Measure", "Value"],
        [
            ["Backend Python modules", str(FACTS.backend_files)],
            ["Frontend TypeScript and TSX modules", str(FACTS.frontend_files)],
            ["Backend direct dependencies", str(len(FACTS.python_packages))],
            ["Frontend runtime dependencies", str(len(FACTS.node_deps))],
            ["Frontend development dependencies", str(len(FACTS.node_dev_deps))],
            ["Configurable environment variables", str(len(FACTS.backend_env))],
            ["Database tables", str(len(FACTS.tables))],
            ["Graph nodes", str(len(FACTS.graph_nodes))],
            ["Agents", str(len(FACTS.agents))],
            ["Tool policies", str(len(FACTS.tools))],
            ["HTTP routes", str(len(FACTS.api_routes))],
            ["Evaluation dimensions", "10"],
            ["Supported languages", "3 (English, Bengali, Hindi)"],
            ["Interface translation keys", str(FACTS.locale_keys)],
            ["Backend test functions", str(FACTS.backend_test_count)],
            ["Backend test modules", str(len(FACTS.backend_test_files))],
            ["Frontend test modules", str(len(FACTS.frontend_test_files))],
            ["Offline evaluation cases", str(len(FACTS.eval_cases))],
            ["CI/CD workflows", str(len(FACTS.workflows))],
        ],
        caption="Quantitative description of the artefact, read from the repository at "
                "document generation time.",
        widths=[3.0, 2.8],
    )

    g.h2("Key algorithms")
    g.h3("Agent selection")
    g.p(
        "Given request text, the supervisor matches it against five domain vocabularies "
        "and a whole-trip vocabulary. The union of matched domains gives the selected "
        "set; an empty match falls back to the full set. The result is ordered by the "
        "fixed dependency order so that consumers always follow producers."
    )
    g.h3("Dependency closure")
    g.p(
        "Given a seed set of agents, expand_dependents repeatedly adds the dependents "
        "of every member until the set stops growing. The relation is: flights and "
        "hotels each invalidate budget and itinerary; weather invalidates itinerary; "
        "budget invalidates itinerary; itinerary invalidates nothing. The relation is "
        "acyclic, so the closure terminates."
    )
    g.h3("Preservation")
    g.p(
        "Given request text, a bounded pattern matches a preservation verb followed "
        "within forty characters by a domain noun, and maps the noun to an agent. The "
        "matched agents are removed from the re-run set after closure, so an "
        "explicitly preserved agent is not reintroduced by dependency expansion."
    )
    g.h3("Score aggregation")
    g.p(
        "Checks are grouped by dimension and averaged, excluding skipped checks. The "
        "overall score is the weighted mean of the dimension scores using fixed "
        "dimension weights. Two dimensions - safety and schema validity - are treated "
        "as blocking regardless of the aggregate."
    )

    g.h2("Development environment")
    g.p(
        "Development was performed with a Python virtual environment and a Node "
        "toolchain driven by a single Makefile, with `make setup` performing all "
        "installation and `make dev` running both processes. Container images are "
        "defined but were not built in the development environment, because Docker was "
        "not available there; the continuous integration pipeline includes an image "
        "build job for that reason."
    )


# ---------------------------------------------------------------------------
def _results(g: Guide) -> None:
    g.h1("Results", page_break=True)

    g.callout(
        "warning",
        "This section reports functional outcomes only. No timing, throughput, "
        "accuracy or user-study result is reported, because none was measured.",
    )

    g.h2("Functional outcomes")
    g.table(
        ["Objective", "Outcome", "Evidence"],
        [
            ["Dynamic agent selection",
             "Achieved. A request naming one domain executes one agent; a whole-trip "
             "request executes five.",
             "Supervisor routing tests; the `weather_only` case"],
            ["Selective re-execution with preservation",
             "Achieved. A hotel-and-price change with an explicit flight preservation "
             "re-runs hotel, budget and itinerary, and the flight payload is "
             "unchanged.",
             "The preservation regression test; the `cheaper_hotel_revision` case"],
            ["Deny-by-default tool authorization",
             "Achieved. An unregistered tool, an unauthorised agent, a malformed "
             "argument set, a forbidden argument key, a write operation and an "
             "exhausted budget are each refused.",
             "Tool-guard tests"],
            ["Input and output guardrails",
             "Achieved. Injection attempts, off-topic requests, impossible dates, "
             "oversized bodies and unsafe markup are refused; output is screened for "
             "secrets, markup, URL schemes and consistency.",
             "Guardrail tests; the `prompt_injection`, `off_topic` and `invalid_dates` "
             "cases"],
            ["Personal data protection",
             "Achieved. Cards, passports, national ids, bank accounts, emails, phones "
             "and credentials are redacted before the model, before tools and before "
             "storage, with dates and short digit runs correctly excluded.",
             "PII guard tests"],
            ["Ten-dimension evaluation",
             "Achieved. Deterministic scoring runs without any provider key and is "
             "reproducible.",
             "Evaluation tests; the offline suite in CI"],
            ["Human-in-the-loop with a durable pause",
             "Achieved. The draft run terminates, the state is checkpointed, and a "
             "later invocation resumes on the branch the decision selects.",
             "Review service tests; end-to-end smoke run"],
            ["Multilingual response",
             "Achieved. Approved journeys render in English, Bengali or Hindi from a "
             "server-side catalogue.",
             "The `bengali_response` and `hindi_response` cases; i18n parity test"],
            ["Light and dark theming",
             "Achieved. Two designed palettes over semantic tokens, with flash "
             "prevention under a hash-allowlisted content security policy.",
             "Theme tests; the compiled-CSS coverage test"],
            ["Containerisation and CI/CD",
             "Configured. Image definitions, compose stack, quality gate and a single "
             "controlled deployment path are present in the repository.",
             "Dockerfile, compose files, two workflow files, render.yaml"],
        ],
        caption="Each objective and its verified outcome.",
        widths=[1.3, 2.6, 1.9],
    )

    g.h2("Verification summary")
    g.table(
        ["Gate", "Status"],
        [
            ["Backend test suite", "Passing"],
            ["Frontend test suite", "Passing"],
            ["Python lint (ruff)", "Clean"],
            ["TypeScript project check", "Clean"],
            ["Production frontend build", "Succeeds"],
            ["Offline evaluation suite", "All cases pass their declared expectations"],
            ["Alembic offline render", "Succeeds"],
            ["Container image build", "Verified in CI only; not built locally"],
            ["Deployed instance", "Not asserted by this document"],
        ],
        caption="Verification status of each quality gate.",
        widths=[2.4, 3.4],
    )

    g.h2("Not measured")
    g.table(
        ["Quantity", "Status"],
        [
            ["End-to-end planning latency", "Not measured yet"],
            ["Per-agent execution time", "Not measured yet"],
            ["Throughput under concurrent load", "Not measured yet"],
            ["Memory and CPU at steady state", "Not measured yet"],
            ["Container image size", "Not measured yet"],
            ["Cold-start time (application or database)", "Not measured yet"],
            ["Prompt-injection detection precision and recall",
             "Not measured yet - no labelled corpus exists"],
            ["Itinerary quality judged by human raters",
             "Not measured yet - no user study was conducted"],
            ["Cost per journey", "Not measured yet"],
        ],
        caption="Quantities that would require measurement and have not been "
                "measured.",
        widths=[3.2, 2.6],
    )


# ---------------------------------------------------------------------------
def _limitations(g: Guide) -> None:
    g.h1("Limitations", page_break=True)
    g.table(
        ["Limitation", "Consequence", "Why it was accepted"],
        [
            ["Specialists execute sequentially",
             "A full plan takes the sum of its agents rather than the maximum of the "
             "independent ones",
             "Keeps one checkpoint boundary and a readable trace; concurrency is a "
             "known next step"],
            ["Rate limiting and metrics are in-process",
             "Both are incorrect with more than one instance",
             "Correct for the single-container deployment actually used, and stated "
             "rather than hidden"],
            ["Routing is vocabulary-based",
             "Unusual phrasings fall back to selecting every agent",
             "Exact testability and zero cost were judged more valuable than coverage "
             "of rare phrasings"],
            ["No authentication",
             "A session identifier is not a credential; anyone holding it can read "
             "those journeys",
             "The system stores travel drafts and actively removes personal "
             "identifiers; accounts were out of scope"],
            ["Pattern-based injection detection",
             "Novel phrasings may evade the classifier",
             "The tool guard bounds the consequence of a bypass, which is the "
             "load-bearing control"],
            ["No caching of provider results",
             "Repeated identical searches cost repeated provider calls",
             "Correctness and freshness were prioritised in a first version"],
            ["JSON result columns",
             "Queries cannot filter inside a result payload",
             "No such query exists; promoting a field later is a migration, not a "
             "redesign"],
            ["No performance measurement",
             "No quantitative claim can be made about speed or capacity",
             "Stating this is more useful than estimating; instrumentation exists to "
             "measure it"],
            ["Container image not built locally",
             "The image build is verified only by CI",
             "Docker was unavailable in the development environment"],
            ["Free hosting tier",
             "Cold starts and limited memory affect first-request behaviour",
             "The project is a study and portfolio system; the constraint is real and "
             "documented"],
        ],
        caption="Limitations, their consequences, and the reasoning behind accepting "
                "each.",
        widths=[1.4, 2.2, 2.2],
    )


# ---------------------------------------------------------------------------
def _future(g: Guide) -> None:
    g.h1("Future Work", page_break=True)

    g.h2("Near term")
    g.numbered([
        "Concurrent execution of the independent specialists - flights, hotels and "
        "weather - preserving the dependency order for budget and itinerary.",
        "Instrumented measurement of end-to-end and per-agent latency using the "
        "existing tracing spans, replacing every \"not measured yet\" in this document "
        "with an observed figure.",
        "Provider result caching keyed by destination, date range and traveller count, "
        "with an explicit freshness policy.",
        "A shared store for rate limiting and metrics, removing the single-instance "
        "assumption.",
    ])

    g.h2("Medium term")
    g.numbered([
        "A labelled prompt-injection corpus, so detection precision and recall can be "
        "reported rather than described.",
        "A human evaluation of itinerary quality with defined rater instructions, "
        "giving the one dimension a rule cannot judge an empirical basis.",
        "User accounts, replacing the session identifier with authentication and "
        "enabling per-user history and preferences.",
        "Enabling the declared write operations - booking and cancellation - behind "
        "the existing confirmation requirement, which is the reason they were declared "
        "and disabled rather than omitted.",
    ])

    g.h2("Longer term")
    g.numbered([
        "A learned or hybrid router evaluated against the deterministic one on a "
        "phrase corpus, adopted only if it measurably improves selection without "
        "losing testability.",
        "Additional languages, which the code-and-catalogue design reduces to a "
        "catalogue contribution.",
        "Group planning, where several travellers review the same journey and the "
        "review model becomes multi-party.",
        "Richer provenance, recording not only the class of a value's source but the "
        "specific provider and the time it was obtained.",
    ])


# ---------------------------------------------------------------------------
def _conclusion(g: Guide) -> None:
    g.h1("Conclusion", page_break=True)
    g.p(
        "JourneyMesh demonstrates that the difficult properties of an LLM application - "
        "bounded behaviour, honest uncertainty, meaningful human oversight and "
        "efficient revision - are architectural properties rather than prompting "
        "problems. Placing routing, authorization, arithmetic and validation in "
        "deterministic application code, and reserving the model for composition, makes "
        "each of those properties testable case by case rather than statistically."
    )
    g.p(
        "The specific contribution is the treatment of a human change request as a "
        "scoped invalidation over a declared dependency relation, combined with "
        "explicit user-directed preservation, and verified by asserting that preserved "
        "output is byte-identical after the revision. This makes the interaction "
        "predictable in a way that regenerating an entire plan cannot be: a traveller "
        "who agreed to their flights keeps them."
    )
    g.p(
        "The system is functionally complete against its stated objectives and verified "
        "by an automated test suite and a deterministic offline evaluation suite. Its "
        "performance characteristics are unmeasured, and its principal architectural "
        "limitation - sequential execution of independent specialists - is identified "
        "with a specific remedy. Both are stated here rather than obscured, because the "
        "value of a design record lies as much in what it declines to claim as in what "
        "it reports."
    )
