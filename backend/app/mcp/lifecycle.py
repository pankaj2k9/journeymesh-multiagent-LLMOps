"""MCP session lifecycle: opening one, probing it, and closing it cleanly.

Two things live here that do not belong in the call path.

**Session strategy.** Two, chosen per server.

A *managed* session is started once, by the FastAPI lifespan, and reused. The
weather server uses this: it ships inside the image, it is called on nearly
every journey, and paying a subprocess start on each call is several hundred
milliseconds for nothing. `StdioSessionManager` owns that process - it starts
it at application startup, hands out the live session, restarts it if it dies,
and terminates it on shutdown. Nobody has to run
``python -m app.mcp.weather_server`` in a terminal, locally or on the VPS.

A *per-call* session is opened and closed around one invocation. This is the
fallback whenever a managed session is not available: during tests, before the
lifespan has run, and for a server whose process has just died and not yet
been restarted. It is also what every probe uses, because a probe must not
disturb the session real traffic is using.

The reason the managed path needs care is that a subprocess outliving its
parent is a zombie holding file descriptors. `stdio_client` is an async
context manager that terminates the child on exit, so the manager holds it in
an `AsyncExitStack` and unwinds that stack on shutdown - the same teardown the
per-call path gets for free.

**Probing.** The health endpoint answers two different questions, and they
cost very different amounts. "Is this server configured?" is free and reads
settings. "Can this server actually be reached?" starts a subprocess or opens
an HTTPS connection, so it is opt-in via ``?probe=true`` and it is bounded by
a timeout.

Every probe is independent. One server failing tells you nothing about the
others, and it must not prevent them being probed - that is the isolation the
whole MCP layer is built around.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from app.mcp.config import MCPServerConfig, server_configs
from app.mcp.security import safe_error
from app.observability.logging import get_logger

logger = get_logger("journeymesh.mcp.lifecycle")

# A probe must not hang a health check. Shorter than the call timeout on
# purpose: connecting is much cheaper than answering.
PROBE_TIMEOUT_SECONDS = 12


@asynccontextmanager
async def open_session(server: MCPServerConfig) -> AsyncIterator[Any]:
    """Yield an initialised MCP session for one server, then close it.

    The nested context managers matter: leaving them tears down the JSON-RPC
    session, then the transport, then - for stdio - terminates the child
    process. Nothing is left running when this generator exits, including on
    an exception.
    """
    from mcp import ClientSession, StdioServerParameters

    if server.transport == "streamable_http":
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(server.url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
        return

    if server.transport == "stdio":
        from mcp.client.stdio import stdio_client

        from app.mcp.client import stdio_child_environment

        params = StdioServerParameters(
            command=server.command or sys.executable,
            args=list(server.args),
            env=stdio_child_environment(server),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
        return

    raise RuntimeError(f"The {server.name} MCP server is disabled.")


async def list_tools(server: MCPServerConfig) -> list[str]:
    """The tool names one MCP server advertises."""
    async with open_session(server) as session:
        response = await session.list_tools()
        return sorted(tool.name for tool in getattr(response, "tools", []) or [])


async def probe_server(server: MCPServerConfig) -> dict[str, Any]:
    """Try to reach one server and list its tools. Never raises.

    The returned dictionary is safe to serialise into an API response: the URL
    is redacted by `MCPServerConfig.describe`, and any error is passed through
    `safe_error`, which strips the Tavily key out of the message.
    """
    status: dict[str, Any] = server.describe()

    # One shape for every outcome, so a caller never has to test for a key.
    status.setdefault("reachable", False)
    status.setdefault("tools", [])
    status.setdefault("error", None)

    if not server.enabled:
        status["unavailable_reason"] = (
            status.get("unavailable_reason")
            or "This server is not enabled in this deployment."
        )
        return status

    try:
        tools = await asyncio.wait_for(list_tools(server), timeout=PROBE_TIMEOUT_SECONDS)
        status["reachable"] = True
        status["tools"] = tools
        status["error"] = None
    except asyncio.TimeoutError:
        status["reachable"] = False
        status["tools"] = []
        status["error"] = f"Timed out after {PROBE_TIMEOUT_SECONDS}s."
        logger.warning("MCP probe timed out", extra={"server": server.name})
    except Exception as exc:  # noqa: BLE001 - a probe reports, it does not raise
        detail = safe_error(exc)
        status["reachable"] = False
        status["tools"] = []
        status["error"] = detail
        logger.warning("MCP probe failed", extra={"server": server.name, "error": detail})

    return status


async def probe_all(names: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """Probe every configured server concurrently and independently.

    `gather` with `return_exceptions=True` is the isolation: one server timing
    out or crashing cannot cancel the others, so a broken weather server still
    leaves a truthful answer about search and aviation.
    """
    configs = server_configs()
    selected = [configs[name] for name in (names or configs.keys()) if name in configs]

    results = await asyncio.gather(
        *(probe_server(server) for server in selected), return_exceptions=True
    )

    report: dict[str, dict[str, Any]] = {}
    for server, result in zip(selected, results, strict=True):
        if isinstance(result, BaseException):
            report[server.name] = {
                **server.describe(),
                "reachable": False,
                "tools": [],
                "error": safe_error(result),
            }
        else:
            report[server.name] = result
    return report


# ---------------------------------------------------------------------------
# Managed stdio sessions
# ---------------------------------------------------------------------------
class StdioSessionManager:
    """Owns one long-lived stdio MCP subprocess for the life of the app.

    Started by the FastAPI lifespan, so the normal workflow is exactly:

        uvicorn app.main:app --reload      # local
        docker compose up -d               # production

    and the child process appears by itself, in the same process tree, on both.
    There is no systemd unit, no second container, no port, no HTTP route and
    no terminal to keep open.

    The manager is deliberately forgiving. A failure to start is logged and
    leaves `session` as None, which sends callers down the per-call path and
    then to the in-process adapter - a weather server that will not start must
    not stop the API from serving.
    """

    def __init__(self, server: MCPServerConfig) -> None:
        self.server = server
        self._stack: AsyncExitStack | None = None
        self._session: Any = None
        # One in-flight request at a time. A stdio transport is a single pipe
        # pair, and serialising here is cheaper than debugging interleaved
        # JSON-RPC frames.
        self._lock = asyncio.Lock()
        self._starting = asyncio.Lock()
        self.last_error: str | None = None

    @property
    def running(self) -> bool:
        return self._session is not None

    async def start(self) -> bool:
        """Spawn the subprocess and initialise the MCP session."""
        if not self.server.enabled or self.server.transport != "stdio":
            return False

        async with self._starting:
            if self._session is not None:
                return True

            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            from app.mcp.client import stdio_child_environment

            stack = AsyncExitStack()
            try:
                params = StdioServerParameters(
                    command=self.server.command or sys.executable,
                    args=list(self.server.args),
                    # The credentials the child actually needs, and nothing
                    # else. Never logged - see stdio_child_environment.
                    env=stdio_child_environment(self.server),
                )
                read, write = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(ClientSession(read, write))
                await asyncio.wait_for(session.initialize(), timeout=PROBE_TIMEOUT_SECONDS)
            except Exception as exc:  # noqa: BLE001 - a dead server is not fatal
                self.last_error = safe_error(exc)
                await stack.aclose()
                logger.warning(
                    "managed MCP server failed to start; calls will fall back",
                    extra={"server": self.server.name, "error": self.last_error},
                )
                return False

            self._stack = stack
            self._session = session
            self.last_error = None
            logger.info(
                "managed MCP server started",
                extra={"server": self.server.name, "command": self.server.command},
            )
            return True

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[Any]:
        """Borrow the live session, restarting the child if it has died."""
        if self._session is None and not await self.start():
            raise RuntimeError(f"The {self.server.name} MCP server is not running.")

        async with self._lock:
            try:
                yield self._session
            except Exception:
                # The transport may be broken rather than the request. Drop the
                # session so the next caller starts a fresh child instead of
                # writing into a closed pipe forever.
                await self._discard()
                raise

    async def _discard(self) -> None:
        stack, self._stack, self._session = self._stack, None, None
        if stack is None:
            return
        try:
            await stack.aclose()
        except Exception as exc:  # noqa: BLE001 - teardown must not raise
            logger.debug(
                "managed MCP teardown raised",
                extra={"server": self.server.name, "error": safe_error(exc)},
            )

    async def stop(self) -> None:
        """Terminate the subprocess. Called by the FastAPI lifespan."""
        if self._session is None and self._stack is None:
            return
        await self._discard()
        logger.info("managed MCP server stopped", extra={"server": self.server.name})

    def status(self) -> dict[str, Any]:
        return {
            "server": self.server.name,
            "managed": True,
            "running": self.running,
            "command": self.server.command,
            "args": list(self.server.args),
            "last_error": self.last_error,
        }


# Servers worth keeping warm: ours, shipped in this image, called constantly.
# A third-party server launched through uvx is left on the per-call path, so a
# package that misbehaves cannot hold a process open for the life of the app.
MANAGED_SERVERS = ("weather",)

_managers: dict[str, StdioSessionManager] = {}


async def start_managed_servers() -> dict[str, bool]:
    """Start every managed MCP subprocess. Called from the app lifespan."""
    configs = server_configs()
    started: dict[str, bool] = {}

    for name in MANAGED_SERVERS:
        server = configs.get(name)
        if server is None or not server.enabled or server.transport != "stdio":
            started[name] = False
            continue
        manager = StdioSessionManager(server)
        started[name] = await manager.start()
        # Registered even when the start failed, so `acquire` can retry later
        # rather than the application deciding once at boot and never again.
        _managers[name] = manager

    return started


async def stop_managed_servers() -> None:
    """Terminate every managed MCP subprocess. Called from the app lifespan."""
    for manager in list(_managers.values()):
        await manager.stop()
    _managers.clear()


def get_manager(name: str) -> StdioSessionManager | None:
    """The managed session for a server, if one is running in this process."""
    return _managers.get(name)


def managed_status() -> dict[str, dict[str, Any]]:
    return {name: manager.status() for name, manager in _managers.items()}
