"""MCP client.

Responsibilities are deliberately narrow: take an authorised tool call,
choose a transport, invoke it, normalise failures and record provider status.
Authorization happens before the client is reached; the client re-checks with
the guard so that no code path can bypass it.
"""

from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.core.constants import DATA_SOURCES, EVENT_PROVIDER_FAILURE, SOURCE_UNAVAILABLE
from app.core.exceptions import ToolAuthorizationError
from app.guardrails.tool_guard import ToolDecision, ToolGuard, get_tool_guard
from app.mcp import registry
from app.mcp.config import MCPServerConfig
from app.observability import metrics
from app.observability.logging import get_logger
from app.observability.tracing import span
from app.schemas.common import ProviderStatus
from app.security import audit

logger = get_logger("journeymesh.mcp.client")


def _mcp_sdk_available() -> bool:
    """True when the MCP SDK is installed and a real server can be reached."""
    global _SDK_AVAILABLE
    if _SDK_AVAILABLE is None:
        import importlib.util

        _SDK_AVAILABLE = importlib.util.find_spec("mcp") is not None
        if not _SDK_AVAILABLE:
            logger.info(
                "MCP SDK is not installed - tools run through their in-process adapters"
            )
    return _SDK_AVAILABLE


_SDK_AVAILABLE: bool | None = None


class ToolCallResult:
    """Outcome of one tool invocation."""

    def __init__(
        self,
        *,
        tool: str,
        agent: str,
        ok: bool,
        data: dict[str, Any] | None = None,
        error: str | None = None,
        decision: ToolDecision | None = None,
        latency_ms: int = 0,
        transport: str = "in_process",
    ) -> None:
        self.tool = tool
        self.agent = agent
        self.ok = ok
        self.data = data or {}
        self.error = error
        self.decision = decision
        self.latency_ms = latency_ms
        self.transport = transport

    @property
    def blocked(self) -> bool:
        return self.decision is not None and not self.decision.allowed

    def provider_status(self, kind: str, provider: str) -> ProviderStatus:
        source = self.data.get("source") if self.ok else None
        if source not in DATA_SOURCES:
            source = SOURCE_UNAVAILABLE
        return ProviderStatus(
            provider=provider,
            kind=kind,  # type: ignore[arg-type]
            ok=self.ok,
            source=source,
            latency_ms=self.latency_ms,
            message=self.error,
            retrieved_at=datetime.now(timezone.utc),
        )


class MCPClient:
    """Dispatches tool calls to MCP servers or their in-process adapters."""

    def __init__(self, guard: ToolGuard | None = None) -> None:
        self.guard = guard or get_tool_guard()
        self.calls: list[ToolCallResult] = []

    def reset(self) -> None:
        self.calls.clear()

    async def call(
        self,
        tool: str,
        *,
        agent: str,
        arguments: dict[str, Any] | None = None,
        user_confirmed: bool = False,
        raise_on_block: bool = False,
    ) -> ToolCallResult:
        """Authorise and invoke ``tool`` on behalf of ``agent``."""
        decision = self.guard.authorize(
            tool=tool, agent=agent, arguments=arguments or {}, user_confirmed=user_confirmed
        )
        if not decision.allowed:
            audit.record(
                "TOOL_CALL_BLOCKED",
                detail={"tool": tool, "agent": agent, "rule": decision.rule},
                actor=agent,
            )
            metrics.increment("tool.blocked", tool=tool, agent=agent)
            result = ToolCallResult(
                tool=tool, agent=agent, ok=False, error=decision.reason, decision=decision
            )
            self.calls.append(result)
            if raise_on_block:
                raise ToolAuthorizationError(decision.reason or "Tool call blocked.")
            return result

        descriptor = registry.get(tool)
        if descriptor is None:  # pragma: no cover - guard already rejects unknown tools
            result = ToolCallResult(
                tool=tool, agent=agent, ok=False, error=f"Unknown tool '{tool}'.", decision=decision
            )
            self.calls.append(result)
            return result

        server = registry.server_for(tool)
        transport = "in_process"
        if server is not None and server.enabled and _mcp_sdk_available():
            transport = server.transport

        with span(f"tool:{tool}", kind="tool", agent=agent, transport=transport) as current:
            try:
                if transport in ("stdio", "streamable_http") and server is not None:
                    data = await self._call_remote(server, descriptor, decision.sanitized_arguments)
                else:
                    data = await self._call_in_process(descriptor, decision.sanitized_arguments)
                ok, error = True, None
            except Exception as exc:  # noqa: BLE001 - provider failures are data, not crashes
                logger.warning(
                    "tool call failed",
                    extra={"tool": tool, "agent": agent, "error": str(exc)},
                )
                audit.record(
                    EVENT_PROVIDER_FAILURE,
                    detail={"tool": tool, "agent": agent, "error": type(exc).__name__},
                    actor=agent,
                )
                data, ok, error = {}, False, f"{type(exc).__name__}: {exc}"
                current.success = False

        latency = current.latency_ms or 0
        metrics.increment("tool.calls", tool=tool, agent=agent)
        metrics.observe("tool.latency", latency, tool=tool)

        result = ToolCallResult(
            tool=tool,
            agent=agent,
            ok=ok,
            data=data,
            error=error,
            decision=decision,
            latency_ms=latency,
            transport=transport,
        )
        self.calls.append(result)
        return result

    # ---- transports -----------------------------------------------------
    async def _call_in_process(
        self, descriptor: registry.ToolDescriptor, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        implementation = descriptor.implementation
        outcome = implementation(**arguments)
        if inspect.isawaitable(outcome):
            outcome = await outcome
        return outcome  # type: ignore[return-value]

    async def _call_remote(
        self,
        server: MCPServerConfig,
        descriptor: registry.ToolDescriptor,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Invoke a tool on a real MCP server.

        Falls back to the in-process adapter when the MCP SDK is not installed
        or the server cannot be reached, so a misconfigured transport degrades
        instead of failing the journey.
        """
        settings = get_settings()
        try:
            payload = await self._mcp_session_call(
                server, descriptor.remote_name or descriptor.name, arguments, settings
            )
            return payload
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "remote MCP call failed, using in-process adapter",
                extra={"server": server.name, "tool": descriptor.name, "error": str(exc)},
            )
            data = await self._call_in_process(descriptor, arguments)
            data.setdefault("notes", []).append(
                f"The {server.name} MCP server was unreachable; JourneyMesh used its local adapter."
            )
            return data

    async def _mcp_session_call(
        self,
        server: MCPServerConfig,
        remote_tool: str,
        arguments: dict[str, Any],
        settings: Any,
    ) -> dict[str, Any]:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        if server.transport == "streamable_http":
            from mcp.client.streamable_http import streamablehttp_client

            async with streamablehttp_client(server.url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    response = await session.call_tool(remote_tool, arguments)
                    return _unwrap_mcp_content(response)

        params = StdioServerParameters(
            command=server.command or "python",
            args=list(server.args),
            env=None,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                response = await session.call_tool(remote_tool, arguments)
                return _unwrap_mcp_content(response)


def _unwrap_mcp_content(response: Any) -> dict[str, Any]:
    """Normalise an MCP tool response into a plain dictionary."""
    structured = getattr(response, "structuredContent", None)
    if isinstance(structured, dict):
        return structured

    content = getattr(response, "content", None) or []
    for item in content:
        text = getattr(item, "text", None)
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {"raw": str(response)}


_client: MCPClient | None = None


def get_mcp_client() -> MCPClient:
    global _client
    if _client is None:
        _client = MCPClient()
    return _client


def reset_mcp_client() -> None:
    global _client
    _client = None
