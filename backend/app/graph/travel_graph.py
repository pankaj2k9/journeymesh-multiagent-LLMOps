"""The JourneyMesh LangGraph workflow.

    entry router
      |-- plan ------> supervisor ------\\
      |-- revise ----> supervisor_rev --+--> specialists --> output_guard
      |                                                          |
      |                                                    evaluation
      |                                                          |
      |                                                    human_review --> END
      |
      '-- finalise --> final_response --> END

``human_review`` calls LangGraph's ``interrupt()``. The run is checkpointed at
that exact point and ``ainvoke`` returns an ``__interrupt__`` payload rather
than a finished state. ``Command(resume={"action": ...})`` continues the *same*
node call, and the conditional edge that follows sends the run to the final
response or back through a revision. Nothing is replanned that the traveller
did not ask to change.

See ``app/graph/human_review.py`` for both sides of the resume contract.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.agents import AGENT_REGISTRY, FinalResponseAgent, SupervisorAgent
from app.core.config import get_settings
from app.core.constants import (
    EVENT_REVISION_LIMIT_REACHED,
    REVIEW_APPROVED,
    REVIEW_AWAITING,
    REVIEW_CHANGES_REQUESTED,
    REVIEW_LIMIT_REACHED,
    TRIP_APPROVED,
    TRIP_AWAITING_REVIEW,
    TRIP_REVISING,
)
from app.evaluation.evaluator import Evaluator
from app.graph.human_review import (
    ACTION_APPROVE,
    ACTION_REQUEST_CHANGES,
    build_request,
    normalise_decision,
    status_for,
)
from app.graph.routing import (
    ENTRY_FINALISE,
    ENTRY_PLAN,
    ENTRY_REVISE,
    after_review,
    agents_to_run,
    entry_router,
)
from app.graph.state import (
    TravelState,
    add_guardrail_result,
    add_message,
    new_state,
    touch,
)
from app.guardrails import output_guard
from app.mcp.client import MCPClient, get_mcp_client
from app.observability import langsmith, metrics
from app.observability.logging import get_logger
from app.observability.tracing import span
from app.schemas.travel import TripConstraints, TripPlanRequest
from app.security import audit
from app.services.llm_service import LLMService, get_llm_service

logger = get_logger("journeymesh.graph")


class TravelWorkflow:
    """Builds and runs the JourneyMesh graph."""

    def __init__(
        self,
        *,
        mcp_client: MCPClient | None = None,
        llm: LLMService | None = None,
        checkpointer: Any = None,
    ) -> None:
        self.mcp = mcp_client or get_mcp_client()
        self.llm = llm or get_llm_service()
        self.supervisor = SupervisorAgent(llm=self.llm)
        self.final_agent = FinalResponseAgent(mcp_client=self.mcp, llm=self.llm)
        self.evaluator = Evaluator(llm=self.llm)
        self.checkpointer = checkpointer if checkpointer is not None else build_checkpointer()
        self.graph = self._build()

    # ---- graph construction ---------------------------------------------
    def _build(self) -> Any:
        builder = StateGraph(TravelState)

        builder.add_node("supervisor", self._supervisor_node)
        builder.add_node("supervisor_revision", self._revision_node)
        builder.add_node("specialists", self._specialists_node)
        builder.add_node("output_guard", self._output_guard_node)
        builder.add_node("evaluation", self._evaluation_node)
        builder.add_node("review_gate", self._review_gate_node)
        builder.add_node("human_review", self._human_review_node)
        builder.add_node("final_response", self._final_response_node)

        builder.add_conditional_edges(
            START,
            entry_router,
            {
                ENTRY_PLAN: "supervisor",
                ENTRY_REVISE: "supervisor_revision",
                ENTRY_FINALISE: "final_response",
            },
        )
        builder.add_edge("supervisor", "specialists")
        builder.add_edge("supervisor_revision", "specialists")
        builder.add_edge("specialists", "output_guard")
        builder.add_edge("output_guard", "evaluation")
        builder.add_edge("evaluation", "review_gate")
        builder.add_edge("review_gate", "human_review")
        # After the interrupt resolves, the decision routes the run: approve
        # goes straight to the final response, a change request loops back
        # through a revision and returns here for another review.
        builder.add_conditional_edges(
            "human_review",
            after_review,
            {
                "final_response": "final_response",
                "supervisor_revision": "supervisor_revision",
                "await_review": END,
            },
        )
        builder.add_edge("final_response", END)

        if self.checkpointer is not None:
            return builder.compile(checkpointer=self.checkpointer)
        return builder.compile()

    # ---- nodes -----------------------------------------------------------
    async def _supervisor_node(self, state: TravelState) -> TravelState:
        return await self.supervisor.plan(state)

    async def _revision_node(self, state: TravelState) -> TravelState:
        requested = state.get("requested_changes") or ""
        return await self.supervisor.plan_revision(state, requested)

    async def _specialists_node(self, state: TravelState) -> TravelState:
        order = agents_to_run(state)
        state["agents_run"] = []
        with span("specialists", kind="graph", agents=",".join(order)):
            for agent_name in order:
                agent_cls = AGENT_REGISTRY.get(agent_name)
                if agent_cls is None:
                    continue
                agent = agent_cls(mcp_client=self.mcp, llm=self.llm)
                await agent.run(state)
        state["llm_calls"] = self.llm.usage.count
        return touch(state)

    async def _output_guard_node(self, state: TravelState) -> TravelState:
        payload = {
            "selected_agents": state.get("selected_agents") or [],
            "flights": state.get("flight_results") or {},
            "hotels": state.get("hotel_results") or {},
            "weather": state.get("weather_info") or {},
            "budget": state.get("budget_analysis") or {},
            "itinerary": state.get("itinerary_plan") or {},
        }
        constraints = TripConstraints.model_validate(state.get("trip_constraints") or {})
        with span("Output Guard", kind="guardrail", stage="output"):
            decision = output_guard.check_payload(payload, constraints=constraints)
        add_guardrail_result(state, decision.to_dict())

        if not decision.allowed:
            audit.record(
                "OUTPUT_VALIDATION_FAILED",
                detail={"failures": decision.failures},
                trip_id=state.get("trip_id"),
            )
            add_message(
                state,
                role="system",
                content="The generated journey did not pass output validation.",
            )
        elif decision.warnings:
            add_message(
                state,
                role="system",
                content="Output check warnings: " + "; ".join(decision.warnings[:3]),
            )
        return touch(state)

    async def _evaluation_node(self, state: TravelState) -> TravelState:
        with span("Evaluation", kind="evaluation", trip_id=state.get("trip_id")):
            result = await self.evaluator.evaluate(state)
        state["evaluation_results"] = result.model_dump(mode="json")
        add_message(
            state,
            role="system",
            content=(
                f"Quality score {result.overall_score:.2f} "
                f"({'passed' if result.passed else 'needs attention'})."
            ),
        )
        return touch(state)

    async def _review_gate_node(self, state: TravelState) -> TravelState:
        """Mark the journey as awaiting review, and commit that.

        This is a separate node from the interrupt on purpose. A node's state
        changes are persisted from its RETURN value, and `interrupt()` raises
        rather than returning - so anything written in the same node before
        the pause is discarded. Splitting them means the checkpoint, the
        database and the API all agree that the journey is awaiting review
        while it is actually paused.
        """
        settings = get_settings()
        limit = settings.max_revision_count
        limit_reached = int(state.get("revision_count", 1)) > limit

        if limit_reached:
            state["human_review_status"] = REVIEW_LIMIT_REACHED
            audit.record(EVENT_REVISION_LIMIT_REACHED, trip_id=state.get("trip_id"))
            add_message(
                state,
                role="system",
                content=(
                    f"The revision limit of {limit} has been reached. "
                    "Approve the current plan or start a new journey."
                ),
            )
        else:
            state["human_review_status"] = REVIEW_AWAITING
            add_message(
                state,
                role="system",
                content="Draft ready for review. Approve it or request changes.",
            )

        state["trip_status"] = TRIP_AWAITING_REVIEW
        state["review_decision"] = None

        with span(
            "Human Review",
            kind="chain",
            trip_id=state.get("trip_id"),
            revision_number=state.get("revision_count"),
        ) as review_span:
            review_span.attributes["human_review_status"] = state["human_review_status"]
        metrics.increment("graph.awaiting_review")
        return touch(state)

    async def _human_review_node(self, state: TravelState) -> TravelState:
        """Pause for a person, using LangGraph's native interrupt.

        `interrupt()` raises a control-flow signal LangGraph catches. The
        checkpointer records that this node is mid-execution and `ainvoke`
        returns with `__interrupt__` set instead of a finished state. When
        `Command(resume=value)` arrives, this same call resumes and
        `interrupt()` returns `value` - so everything below runs exactly once,
        with the decision in hand.
        """
        limit_reached = state.get("human_review_status") == REVIEW_LIMIT_REACHED

        # ---- the pause ---------------------------------------------------
        raw_decision = interrupt(build_request(state, limit_reached=limit_reached))
        # ---- resumed -----------------------------------------------------

        decision = normalise_decision(raw_decision)
        action = decision.get("action")
        state["review_decision"] = dict(decision)

        if action == ACTION_APPROVE:
            state["human_review_status"] = REVIEW_APPROVED
            state["trip_status"] = TRIP_APPROVED
            if decision.get("response_language"):
                language = decision["response_language"]
                constraints = dict(state.get("trip_constraints") or {})
                constraints["response_language"] = language
                state["trip_constraints"] = constraints
                state["response_language"] = language
            add_message(state, role="user", content="Approved the draft journey.")
            metrics.increment("graph.review_approved")

        elif action == ACTION_REQUEST_CHANGES:
            feedback = decision.get("feedback", "")
            state["human_review_status"] = REVIEW_CHANGES_REQUESTED
            state["trip_status"] = TRIP_REVISING
            state["requested_changes"] = feedback
            state["revision_count"] = int(state.get("revision_count", 1)) + 1
            add_message(state, role="user", content=feedback or "Requested changes.")
            metrics.increment("graph.review_changes_requested")

        else:
            # An unrecognised resume value. The journey stays reviewable
            # rather than being finalised on a decision nobody made.
            add_message(
                state,
                role="system",
                content=(
                    "The review decision was not recognised; the journey is "
                    "still awaiting review."
                ),
            )

        state["review_iteration"] = int(state.get("review_iteration", 0)) + 1
        return touch(state)

    async def _final_response_node(self, state: TravelState) -> TravelState:
        await self.final_agent.run(state)
        state["trip_status"] = TRIP_APPROVED
        state["human_review_status"] = REVIEW_APPROVED
        metrics.increment("graph.approved")
        return touch(state)

    # ---- public API ------------------------------------------------------
    def config(self, trip_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": trip_id}}

    def _trace_config(self, state: TravelState, phase: str) -> dict[str, Any]:
        """A run name and safe metadata so a trace is readable in LangSmith.

        Naming the run after the phase and revision is what makes selective
        re-execution legible: "Trip Planning - Revision 2" lists only the
        agents that actually re-ran.
        """
        trip_id = state.get("trip_id", "")
        revision = int(state.get("revision_count", 1))
        constraints = state.get("trip_constraints") or {}

        names = {
            "plan": "JourneyMesh Trip Request",
            "revise": f"JourneyMesh Trip Planning - Revision {revision}",
            "approve": "JourneyMesh Final Response",
        }
        return langsmith.run_config(
            name=names.get(phase, "JourneyMesh"),
            tags=["journeymesh", phase, f"revision:{revision}"],
            metadata={
                "trip_id": trip_id,
                "session_id": state.get("session_id"),
                "revision_number": revision,
                "selected_agents": state.get("selected_agents"),
                "change_scope": state.get("change_scope"),
                "human_review_status": state.get("human_review_status"),
                "response_language": constraints.get("response_language"),
                "destination": constraints.get("destination"),
                "origin": constraints.get("origin"),
                "travelers": constraints.get("travelers"),
                "trip_days": constraints.get("trip_days"),
            },
            base=self.config(trip_id),
        )

    async def plan(
        self,
        *,
        trip_id: str,
        request: TripPlanRequest,
        sanitized_query: str | None = None,
        session_id: str | None = None,
        request_id: str | None = None,
    ) -> TravelState:
        """Draft a journey and pause at the human review stage."""
        constraints = request.to_constraints()
        state = new_state(
            trip_id=trip_id,
            user_query=sanitized_query or request.query,
            trip_constraints=constraints.model_dump(mode="json"),
            session_id=session_id or request.session_id,
            request_id=request_id,
            response_language=request.response_language,
        )
        add_message(state, role="user", content=state["user_query"])
        return await self._invoke(state, trip_id, phase="plan")

    async def revise(
        self, state: TravelState, *, requested_changes: str
    ) -> TravelState:
        """Resume the paused review asking for changes.

        The graph is sitting inside `interrupt()` in `human_review`. Sending
        `Command(resume=...)` returns that value from the interrupt, the node
        records the request, and the conditional edge routes to
        `supervisor_revision` - which re-runs only the agents the change
        affects and comes back to review. Nothing restarts from START.
        """
        return await self._resume(
            state,
            {"action": ACTION_REQUEST_CHANGES, "feedback": requested_changes},
            phase="revise",
        )

    async def approve(self, state: TravelState) -> TravelState:
        """Resume the paused review with an approval.

        The interrupt returns, the node marks the journey approved, and the
        conditional edge routes straight to `final_response`. No specialist
        agent runs again.
        """
        payload: dict[str, Any] = {"action": ACTION_APPROVE}
        language = state.get("response_language") or (
            (state.get("trip_constraints") or {}).get("response_language")
        )
        if language:
            payload["response_language"] = language
        return await self._resume(state, payload, phase="approve")

    # ---- resuming --------------------------------------------------------
    async def _resume(
        self, state: TravelState, decision: dict[str, Any], *, phase: str
    ) -> TravelState:
        """Continue an interrupted run, or replay it if the pause is gone.

        The native path is `Command(resume=...)`, and it is used whenever the
        checkpointer still holds a pending interrupt for this thread.

        The replay path exists because a checkpoint can legitimately be
        missing: MemorySaver loses everything when the process restarts, and a
        journey may be reviewed days later against a database that has been
        restored. Rather than fail, the run is re-entered through
        `entry_router` with the decision already applied to the state - the
        behaviour this workflow had before interrupts. It is a fallback, and
        it says so in the logs.
        """
        state = dict(state)  # type: ignore[assignment]
        trip_id = str(state.get("trip_id") or "")
        action = decision.get("action")

        if action == ACTION_REQUEST_CHANGES:
            state["requested_changes"] = decision.get("feedback", "")
        state["review_decision"] = dict(decision)

        config = self._trace_config(state, phase)

        if self._has_pending_interrupt(trip_id):
            with span(f"graph:{phase}", kind="graph", trip_id=trip_id, resume="interrupt"):
                result = await self.graph.ainvoke(Command(resume=decision), config=config)
            return result  # type: ignore[return-value]

        logger.info(
            "no pending interrupt for this thread; replaying the decision",
            extra={"trip_id": trip_id, "phase": phase},
        )
        # Seed the state the way the interrupted node would have, then re-enter.
        state["human_review_status"] = status_for(action)
        if action == ACTION_REQUEST_CHANGES:
            state["revision_count"] = int(state.get("revision_count", 1)) + 1
            state["trip_status"] = TRIP_REVISING
            add_message(state, role="user", content=decision.get("feedback", ""))
        elif action == ACTION_APPROVE:
            state["trip_status"] = TRIP_APPROVED
        state["review_iteration"] = int(state.get("review_iteration", 0)) + 1
        return await self._invoke(state, trip_id, phase=phase)

    def _has_pending_interrupt(self, trip_id: str) -> bool:
        """Whether this thread is parked inside `interrupt()` right now."""
        if self.checkpointer is None or not trip_id:
            return False
        try:
            snapshot = self.graph.get_state(self.config(trip_id))
        except Exception as exc:  # noqa: BLE001 - a missing checkpoint is not an error
            logger.debug(
                "checkpoint lookup failed", extra={"trip_id": trip_id, "error": str(exc)}
            )
            return False

        if getattr(snapshot, "interrupts", None):
            return True
        for task in getattr(snapshot, "tasks", ()) or ():
            if getattr(task, "interrupts", None):
                return True
        return False

    async def _invoke(
        self, state: TravelState, trip_id: str, *, phase: str = "plan"
    ) -> TravelState:
        self.mcp.guard.reset()
        self.mcp.reset()

        config = self._trace_config(state, phase)
        if self.checkpointer is None:
            config.pop("configurable", None)

        with span(f"graph:{phase}", kind="graph", trip_id=trip_id, revision=state.get("revision_count")):
            result = await self.graph.ainvoke(state, config=config)
        return result  # type: ignore[return-value]

    def load_state(self, trip_id: str) -> TravelState | None:
        """Read the checkpointed state for a journey, if one exists."""
        if self.checkpointer is None:
            return None
        try:
            snapshot = self.graph.get_state(self.config(trip_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("checkpoint read failed", extra={"error": str(exc)})
            return None
        values = getattr(snapshot, "values", None)
        return values if isinstance(values, dict) and values else None


# ---- checkpointing -------------------------------------------------------
def build_checkpointer() -> Any:
    """PostgreSQL-backed checkpointing when configured, memory otherwise."""
    settings = get_settings()
    if settings.psycopg_url:
        try:
            from langgraph.checkpoint.postgres import PostgresSaver

            from app.db.database import apply_ssl_mode

            saver = PostgresSaver.from_conn_string(
                apply_ssl_mode(settings.psycopg_url, require_ssl=settings.db_require_ssl)
            )
            # ``from_conn_string`` returns a context manager in recent releases.
            if hasattr(saver, "__enter__"):
                saver = saver.__enter__()
            saver.setup()
            logger.info("LangGraph checkpoints are persisted to PostgreSQL")
            return saver
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "PostgreSQL checkpointer unavailable, falling back to memory",
                extra={"error": str(exc)},
            )

    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()


_workflow: TravelWorkflow | None = None


def get_workflow() -> TravelWorkflow:
    global _workflow
    if _workflow is None:
        _workflow = TravelWorkflow()
    return _workflow


def reset_workflow() -> None:
    global _workflow
    _workflow = None
