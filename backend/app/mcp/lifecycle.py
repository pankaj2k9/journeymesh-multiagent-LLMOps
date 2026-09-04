"""MCP session lifecycle: opening one, probing it, and closing it cleanly.

Two things live here that do not belong in the call path.

**Session strategy.** JourneyMesh opens an MCP session per invocation and
closes it when the call returns. That is a deliberate trade. A long-lived
stdio subprocess would save a few hundred milliseconds per call, but it also
has to survive uvicorn's ``--reload``, multiple async workers, a test suite
that creates and discards clients, and container shutdown - and a subprocess
that outlives its parent is a zombie holding a file descriptor. Per-call
sessions make the failure mode "this call was slow" instead of "this container
leaks processes until it is OOM-killed". `mcp.client.stdio.stdio_client` is an
async context manager that terminates the child on exit, so the process is
reaped on both the success and the failure path.

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
from contextlib import asynccontextmanager
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
