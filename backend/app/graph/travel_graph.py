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

The graph deliberately *ends* at ``human_review``. The run is checkpointed
there, so the workflow pauses until the traveller approves or asks for a
change; resuming re-enters the graph on the branch that decision selects,
with the previous state intact. Nothing is replanned that the traveller did
not ask to change.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents import AGENT_REGISTRY, FinalResponseAgent, SupervisorAgent
from app.core.config import get_settings
from app.core.constants import (
    EVENT_REVISION_LIMIT_REACHED,
    REVIEW_APPROVED,
    REVIEW_AWAITING,
    REVIEW_LIMIT_REACHED,
    TRIP_APPROVED,
    TRIP_AWAITING_REVIEW,
)
from app.evaluation.evaluator import Evaluator
from app.graph.routing import (
    ENTRY_FINALISE,
    ENTRY_PLAN,
    ENTRY_REVISE,
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
from app.observability import metrics
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
        builder.add_edge("evaluation", "human_review")
        builder.add_edge("human_review", END)
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

    async def _human_review_node(self, state: TravelState) -> TravelState:
        settings = get_settings()
        limit = settings.max_revision_count

        if state.get("revision_count", 1) > limit:
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
        metrics.increment("graph.awaiting_review")
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
        return await self._invoke(state, trip_id)

    async def revise(
        self, state: TravelState, *, requested_changes: str
    ) -> TravelState:
        """Re-run only the agents a requested change affects."""
        from app.core.constants import REVIEW_CHANGES_REQUESTED

        state = dict(state)  # type: ignore[assignment]
        state["human_review_status"] = REVIEW_CHANGES_REQUESTED
        state["requested_changes"] = requested_changes
        state["revision_count"] = int(state.get("revision_count", 1)) + 1
        state["review_iteration"] = int(state.get("review_iteration", 0)) + 1
        add_message(state, role="user", content=requested_changes)
        return await self._invoke(state, state.get("trip_id", ""))

    async def approve(self, state: TravelState) -> TravelState:
        """Resume the workflow after approval and produce the final journey."""
        state = dict(state)  # type: ignore[assignment]
        state["human_review_status"] = REVIEW_APPROVED
        state["review_iteration"] = int(state.get("review_iteration", 0)) + 1
        return await self._invoke(state, state.get("trip_id", ""))

    async def _invoke(self, state: TravelState, trip_id: str) -> TravelState:
        self.mcp.guard.reset()
        self.mcp.reset()
        config = self.config(trip_id) if self.checkpointer is not None else None
        with span("graph", kind="graph", trip_id=trip_id):
            if config is not None:
                result = await self.graph.ainvoke(state, config=config)
            else:
                result = await self.graph.ainvoke(state)
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

            saver = PostgresSaver.from_conn_string(settings.psycopg_url)
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
