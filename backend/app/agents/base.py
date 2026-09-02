"""Shared plumbing for JourneyMesh agents.

An agent decides *what* should happen for its slice of the journey. It never
talks to a provider directly - it asks the MCP client, which asks the Tool
Guard first. It never talks to another agent - it reads and writes the shared
TravelState.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.graph.state import TravelState, add_message, add_provider_status, record_error
from app.mcp.client import MCPClient, ToolCallResult, get_mcp_client
from app.observability import metrics
from app.observability.logging import get_logger
from app.observability.tracing import span
from app.services.llm_service import LLMService, get_llm_service


class BaseAgent(ABC):
    """Base class carrying the tool client, the model and safe logging."""

    name: str = "agent"
    provider_kind: str = "search"

    def __init__(
        self,
        *,
        mcp_client: MCPClient | None = None,
        llm: LLMService | None = None,
    ) -> None:
        self.mcp = mcp_client or get_mcp_client()
        self.llm = llm or get_llm_service()
        self.logger = get_logger(f"journeymesh.agents.{self.name}")

    # ---- lifecycle -------------------------------------------------------
    async def run(self, state: TravelState) -> TravelState:
        """Execute the agent and fold its output back into the state."""
        with span(f"agent:{self.name}", kind="agent"):
            metrics.increment("agent.runs", agent=self.name)
            try:
                await self.execute(state)
            except Exception as exc:  # noqa: BLE001 - one agent must not sink the journey
                self.logger.exception("agent failed", extra={"agent": self.name})
                record_error(state, f"{self.name} failed: {type(exc).__name__}")
                self.note(state, f"{self.label()} could not complete and was skipped.")
                metrics.increment("agent.failures", agent=self.name)

        run_log = state.setdefault("agents_run", [])
        if self.name not in run_log:
            run_log.append(self.name)
        return state

    @abstractmethod
    async def execute(self, state: TravelState) -> None:
        """Do the agent's work, mutating ``state`` in place."""

    # ---- helpers ---------------------------------------------------------
    def label(self) -> str:
        return self.name.replace("_", " ").title()

    def note(self, state: TravelState, content: str) -> None:
        """Add a safe execution summary. Never a model's private reasoning."""
        add_message(state, role="agent", content=content, agent=self.name)

    async def call_tool(
        self,
        state: TravelState,
        tool: str,
        arguments: dict[str, Any],
        *,
        provider: str,
        kind: str | None = None,
    ) -> ToolCallResult:
        """Invoke an MCP tool and record its provider status on the state."""
        result = await self.mcp.call(tool, agent=self.name, arguments=arguments)
        state["tool_calls"] = int(state.get("tool_calls", 0)) + 1

        status = result.provider_status(kind or self.provider_kind, provider)
        add_provider_status(state, status.model_dump(mode="json"))

        if result.blocked:
            self.note(state, f"A {tool} call was blocked by the tool guard.")
        elif not result.ok:
            self.note(state, f"The {provider} provider was unavailable for {tool}.")
        return result

    def track_llm(self, state: TravelState) -> None:
        state["llm_calls"] = self.llm.usage.count

    def constraints(self, state: TravelState) -> dict[str, Any]:
        return state.get("trip_constraints") or {}
