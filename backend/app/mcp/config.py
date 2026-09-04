"""MCP transport configuration.

Transport, endpoint and credentials are configuration concerns; tool
discovery and invocation are not. Keeping them apart means a provider can be
swapped by changing environment variables only, and it means nothing in
``app/agents`` has to know that a weather lookup is a subprocess while a
search is an HTTPS call.

Three servers, three different shapes, for three different reasons:

    search     streamable_http   Tavily hosts it. There is nothing to run
                                 locally, and the key is a query parameter,
                                 which is why the URL is built here and
                                 redacted everywhere else.

    aviation   stdio             AviationStack's MCP server is published as a
                                 Python package. `uvx` fetches and runs it in
                                 an isolated environment, so it does not have
                                 to be a dependency of this application.

    weather    stdio             We wrote this one. It lives in this package
                                 and is started with the interpreter already
                                 running, so it works identically on a laptop,
                                 in Docker and on the VPS.

Resolution is deliberate about the difference between "configured" and
"usable". ``auto`` means "use MCP if this deployment can actually reach a
server", so a missing API key degrades to the in-process adapter instead of
producing a startup error or, worse, a server that claims to be enabled and
silently fails on every call.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from app.core.config import get_settings

Transport = Literal["stdio", "streamable_http", "disabled"]

VALID_TRANSPORTS = ("stdio", "streamable_http", "disabled")

# What a user may write in MCP_*_TRANSPORT. "auto" resolves per server below.
CONFIGURABLE_TRANSPORTS = ("auto", "stdio", "streamable_http", "disabled")

# The module that is the weather MCP server. Resolved relative to this file so
# no absolute path is ever hard-coded and the same value works on a Mac, in a
# container and on the VPS.
WEATHER_SERVER_MODULE = "app.mcp.weather_server"
WEATHER_SERVER_PATH = Path(__file__).resolve().parent / "weather_server.py"


@dataclass(frozen=True)
class MCPServerConfig:
    """How to reach one MCP server."""

    name: str
    transport: Transport
    url: str | None = None
    command: str | None = None
    args: tuple[str, ...] = field(default_factory=tuple)
    # Extra variables the child process needs. Merged over the minimal safe
    # environment in `app.mcp.client`, never over the full parent environment.
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 30
    description: str = ""
    # Why this server is not usable, when it is not. Surfaced by the health
    # endpoint so "why is my search deterministic?" has an answer that does
    # not require reading source.
    unavailable_reason: str | None = None

    @property
    def enabled(self) -> bool:
        if self.transport == "disabled":
            return False
        if self.transport == "streamable_http":
            return bool(self.url)
        if self.transport == "stdio":
            return bool(self.command)
        return False

    @property
    def safe_url(self) -> str | None:
        """The endpoint with credentials masked. Safe to log or return."""
        from app.mcp.security import redact_url

        return redact_url(self.url)

    def describe(self) -> dict[str, object]:
        """A status dictionary that can never carry a secret."""
        return {
            "name": self.name,
            "transport": self.transport,
            "enabled": self.enabled,
            "url": self.safe_url,
            "url_configured": bool(self.url),
            "command": self.command,
            "args": list(self.args),
            "description": self.description,
            "unavailable_reason": self.unavailable_reason,
        }


def _normalise(value: str | None, default: str = "auto") -> str:
    """Map what a user wrote onto a transport name this module understands."""
    candidate = (value or "").strip().lower().replace("-", "_")
    if candidate in ("http", "streamable_http"):
        return "streamable_http"
    if candidate == "stdio":
        return "stdio"
    if candidate in ("disabled", "off", "none", "false"):
        return "disabled"
    if candidate == "auto":
        return "auto"
    if candidate == "":
        return default
    # An unrecognised value is a configuration mistake. Disabling is the safe
    # reading: the in-process adapter still answers, and the health endpoint
    # reports why.
    return "disabled"


def _aviation_launcher(settings) -> tuple[str, tuple[str, ...]] | None:
    """How to start the AviationStack MCP server, if it can be started.

    Two shapes, in order of preference:

    1. The package's own console script, when `uv tool install` has already
       put it on PATH. This is what the production image does at build time,
       so a call is a local process start: no index lookup, no download, no
       writable cache needed, and it works on a host with no outbound access.

    2. `uvx <package>`, which resolves and fetches on first use. This is the
       developer path - it works on a laptop with uv installed and nothing
       pre-provisioned - and the fallback if the console script is absent.

    Returns None when neither is available, which is what makes `auto`
    degrade to the in-process adapter instead of failing at call time.
    """
    installed = shutil.which(settings.mcp_aviation_package)
    if installed:
        return installed, ()

    launcher = shutil.which(settings.mcp_aviation_command)
    if launcher:
        return launcher, (settings.mcp_aviation_package,)

    return None


# ---- per-server resolution -------------------------------------------------
def _search_config(settings, timeout: int) -> MCPServerConfig:
    requested = _normalise(settings.mcp_search_transport)
    url = settings.tavily_mcp_url()

    if requested == "auto":
        transport: Transport = "streamable_http" if url else "disabled"
        reason = None if url else "No TAVILY_API_KEY, so the in-process search adapter is used."
    elif requested == "streamable_http":
        transport = "streamable_http"
        reason = None if url else "MCP_SEARCH_TRANSPORT=streamable_http but no TAVILY_API_KEY or MCP_SEARCH_URL."
    elif requested == "stdio":
        # Tavily is a hosted service; there is no local server to launch.
        transport = "disabled"
        reason = "Search has no local MCP server. Use streamable_http or leave it on auto."
    else:
        transport = "disabled"
        reason = "Disabled by configuration."

    return MCPServerConfig(
        name="search",
        transport=transport,
        url=url if transport == "streamable_http" else None,
        timeout_seconds=timeout,
        description="Tavily hosted MCP: web search for hotel and destination research.",
        unavailable_reason=reason,
    )


def _aviation_config(settings, timeout: int) -> MCPServerConfig:
    requested = _normalise(settings.mcp_aviation_transport)
    api_key = settings.aviation_api_key
    launcher = _aviation_launcher(settings)

    # An explicit URL means someone is running the server themselves.
    if requested in ("auto", "streamable_http") and settings.mcp_aviation_url:
        return MCPServerConfig(
            name="aviation",
            transport="streamable_http",
            url=settings.mcp_aviation_url,
            timeout_seconds=timeout,
            description="AviationStack MCP over HTTP.",
        )

    if requested == "disabled":
        return MCPServerConfig(
            name="aviation",
            transport="disabled",
            timeout_seconds=timeout,
            description="AviationStack MCP: flight schedules, routes and airports.",
            unavailable_reason="Disabled by configuration.",
        )

    # stdio, requested explicitly or reached through auto.
    reason: str | None = None
    if not api_key:
        reason = (
            "No AVIATIONSTACK_API_KEY or AVIATION_STACK_API_KEY, so the "
            "in-process aviation adapter is used."
        )
    elif launcher is None:
        reason = (
            f"Neither '{settings.mcp_aviation_package}' nor "
            f"'{settings.mcp_aviation_command}' is on PATH, so the AviationStack "
            "MCP server cannot be launched. Install uv, or set "
            "MCP_AVIATION_TRANSPORT=disabled to silence this."
        )

    usable = reason is None
    if requested == "auto" and not usable:
        transport: Transport = "disabled"
    else:
        transport = "stdio"

    command, args = launcher if launcher else (settings.mcp_aviation_command, (settings.mcp_aviation_package,))

    return MCPServerConfig(
        name="aviation",
        transport=transport,
        command=command if transport == "stdio" else None,
        args=args if transport == "stdio" else (),
        # The package reads AVIATION_STACK_API_KEY. Passing both spellings
        # costs nothing and means either name in the environment works.
        env=(
            {"AVIATION_STACK_API_KEY": api_key, "AVIATIONSTACK_API_KEY": api_key}
            if api_key
            else {}
        ),
        timeout_seconds=timeout,
        description="AviationStack MCP: flight schedules, routes and airports.",
        unavailable_reason=reason,
    )


def _weather_config(settings, timeout: int) -> MCPServerConfig:
    requested = _normalise(settings.mcp_weather_transport)

    if requested in ("auto", "streamable_http") and settings.mcp_weather_url:
        return MCPServerConfig(
            name="weather",
            transport="streamable_http",
            url=settings.mcp_weather_url,
            timeout_seconds=timeout,
            description="JourneyMesh weather MCP server over HTTP.",
        )

    if requested == "disabled":
        return MCPServerConfig(
            name="weather",
            transport="disabled",
            timeout_seconds=timeout,
            description="JourneyMesh custom weather MCP server.",
            unavailable_reason="Disabled by configuration.",
        )

    # The default, and the reason weather is the one server that is always on:
    # it ships inside this package, so `sys.executable -m app.mcp.weather_server`
    # works wherever the application works. Without OPENWEATHER_API_KEY it
    # still answers, with every value labelled an ESTIMATE.
    note = (
        None
        if settings.openweather_api_key
        else "No OPENWEATHER_API_KEY: the MCP server answers with labelled ESTIMATE data."
    )
    return MCPServerConfig(
        name="weather",
        transport="stdio",
        command=sys.executable,
        args=("-m", WEATHER_SERVER_MODULE),
        env=(
            {"OPENWEATHER_API_KEY": settings.openweather_api_key}
            if settings.openweather_api_key
            else {}
        ),
        timeout_seconds=timeout,
        description="JourneyMesh custom weather MCP server (FastMCP, stdio).",
        unavailable_reason=note,
    )


def server_configs() -> dict[str, MCPServerConfig]:
    """Build the MCP server table from settings."""
    settings = get_settings()
    timeout = settings.mcp_timeout_seconds

    return {
        "aviation": _aviation_config(settings, timeout),
        "search": _search_config(settings, timeout),
        "weather": _weather_config(settings, timeout),
    }


def get_server_config(name: str) -> MCPServerConfig | None:
    return server_configs().get(name)
