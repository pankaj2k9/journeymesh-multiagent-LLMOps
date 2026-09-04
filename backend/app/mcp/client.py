"""MCP client.

Responsibilities are deliberately narrow: take an authorised tool call,
choose a transport, invoke it, normalise failures and record provider status.
Authorization happens before the client is reached; the client re-checks with
the guard so that no code path can bypass it.
"""

from __future__ import annotations

import inspect
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.core.constants import DATA_SOURCES, EVENT_PROVIDER_FAILURE, SOURCE_UNAVAILABLE
from app.core.exceptions import ToolAuthorizationError
from app.guardrails.tool_guard import ToolDecision, ToolGuard, get_tool_guard
from app.mcp import registry
from app.mcp.config import MCPServerConfig
from app.mcp.providers import RemoteCall, adapter_for
from app.mcp.security import safe_error
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
        # The last redacted failure per server. Read by the health endpoint so
        # "search fell back" has a reason attached, and reset per run so a
        # fixed provider stops being reported as broken.
        self.failures: dict[str, str] = {}

    def reset(self) -> None:
        self.calls.clear()
        self.failures.clear()

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

        # The adapter speaks the remote server's vocabulary. It may decline -
        # some tools have no faithful remote equivalent - and declining routes
        # to the in-process implementation rather than to a guess.
        adapter = adapter_for(server.name)
        remote = adapter.to_remote(descriptor.name, arguments) if adapter else None
        if remote is None:
            if adapter is not None:
                logger.debug(
                    "no remote equivalent for this tool; using the in-process adapter",
                    extra={"server": server.name, "tool": descriptor.name},
                )
                metrics.increment(f"mcp.{server.name}.no_remote_equivalent")
                return await self._call_in_process(descriptor, arguments)
            # No adapter registered at all: fall back to the descriptor's own
            # remote name and pass the arguments through unchanged.
            remote = RemoteCall(
                tool=descriptor.remote_name or descriptor.name, arguments=arguments
            )

        try:
            payload = await self._mcp_session_call(
                server, remote.tool, remote.arguments, settings
            )
            shaped = (
                adapter.from_remote(descriptor.name, payload, arguments)
                if adapter
                else payload
            )
            if shaped is None:
                # The server answered, but not in a shape we can trust.
                logger.warning(
                    "MCP response could not be interpreted; using the in-process adapter",
                    extra={"server": server.name, "tool": descriptor.name},
                )
                metrics.increment(f"mcp.{server.name}.unreadable_response")
                return await self._call_in_process(descriptor, arguments)
            return shaped
        except Exception as exc:  # noqa: BLE001
            # Isolation: this is per call and per server, so a broken weather
            # server cannot affect the search or aviation call that follows.
            # `safe_error` is what keeps a Tavily URL - which carries the API
            # key as a query parameter - out of this log line.
            detail = safe_error(exc)
            self.failures[server.name] = detail
            logger.warning(
                "remote MCP call failed, using in-process adapter",
                extra={"server": server.name, "tool": descriptor.name, "error": detail},
            )
            metrics.increment(f"mcp.{server.name}.fallback")
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

        # A managed server is already running: the FastAPI lifespan started
        # the subprocess at application startup and owns its shutdown. Reusing
        # it avoids paying a process start on every call.
        from app.mcp.lifecycle import get_manager

        manager = get_manager(server.name)
        if manager is not None:
            async with manager.acquire() as session:
                response = await session.call_tool(remote_tool, arguments)
                return _unwrap_mcp_content(response)

        # Otherwise open a session for this call and close it after. This is
        # the path in tests, before the lifespan has run, and for servers that
        # are deliberately not kept warm.
        params = StdioServerParameters(
            command=server.command or sys.executable,
            args=list(server.args),
            env=stdio_child_environment(server),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                response = await session.call_tool(remote_tool, arguments)
                return _unwrap_mcp_content(response)


# The environment a stdio MCP server is started with.
#
# The MCP SDK deliberately does NOT inherit the parent environment: with
# ``env=None`` a child receives only HOME and PATH. That is the right default -
# a subprocess has no business seeing the database password - but it also means
# a stdio weather server would start with no OPENWEATHER_API_KEY and silently
# fall back to deterministic output, which looks like a broken provider rather
# than a configuration gap.
#
# So the child gets the SDK's safe default plus an explicit allowlist: the
# provider credentials a JourneyMesh MCP server actually reads, and nothing
# else. DATABASE_URL, the LangSmith key and every other setting stay behind.
_STDIO_CHILD_ENV_ALLOWLIST = (
    "OPENWEATHER_API_KEY",
    "TAVILY_API_KEY",
    "AVIATIONSTACK_API_KEY",
    "AVIATION_STACK_API_KEY",
    "ENABLE_MOCK_DATA",
    "LOG_LEVEL",
    "LOG_FORMAT",
)

# `uvx` needs somewhere to cache the package it fetches and a home to resolve
# its own configuration from. Without these it re-downloads on every call, or
# fails outright in a container whose HOME is not writable.
_STDIO_CHILD_ENV_PASSTHROUGH = (
    "PATH",
    "HOME",
    "TMPDIR",
    "UV_CACHE_DIR",
    "UV_PYTHON",
    "XDG_CACHE_HOME",
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
    "PYTHONPATH",
)


def stdio_child_environment(server: MCPServerConfig | None = None) -> dict[str, str]:
    """The minimal environment a local MCP subprocess needs, and no more.

    The MCP SDK deliberately does not inherit the parent environment: with
    ``env=None`` a child receives only HOME and PATH. That default is right -
    a subprocess has no business seeing the database password - but it also
    means a stdio weather server starts with no OPENWEATHER_API_KEY and
    silently produces estimates, which reads as a broken provider rather than
    a configuration gap.

    So the child gets the SDK's safe default, plus a passthrough list of the
    variables a launcher needs, plus the provider credentials an MCP server
    actually reads, plus whatever the server's own config declares.
    DATABASE_URL, the LangSmith key and every other setting stay behind.

    Never log the return value: it contains credentials by design.
    """
    try:
        from mcp.client.stdio import get_default_environment

        env = dict(get_default_environment())
    except Exception:  # noqa: BLE001 - older SDKs may not expose the helper
        env = {key: os.environ[key] for key in ("HOME", "PATH") if key in os.environ}

    for key in _STDIO_CHILD_ENV_PASSTHROUGH + _STDIO_CHILD_ENV_ALLOWLIST:
        value = os.environ.get(key)
        if value:
            env[key] = value

    # Per-server variables win: they come from resolved settings rather than
    # from whatever happens to be in this process's environment.
    if server is not None:
        env.update({k: v for k, v in (server.env or {}).items() if v})

    return env


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
