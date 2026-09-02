"""MCP transport configuration.

Transport, endpoint and credentials are configuration concerns; tool
discovery and invocation are not. Keeping them apart means a provider can be
swapped by changing environment variables only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.core.config import get_settings

Transport = Literal["stdio", "streamable_http", "disabled"]

VALID_TRANSPORTS = ("stdio", "streamable_http", "disabled")


@dataclass(frozen=True)
class MCPServerConfig:
    """How to reach one MCP server."""

    name: str
    transport: Transport
    url: str | None = None
    command: str | None = None
    args: tuple[str, ...] = field(default_factory=tuple)
    timeout_seconds: int = 30
    description: str = ""

    @property
    def enabled(self) -> bool:
        if self.transport == "disabled":
            return False
        if self.transport == "streamable_http":
            return bool(self.url)
        if self.transport == "stdio":
            return bool(self.command)
        return False


def _normalise(value: str | None, default: Transport = "disabled") -> Transport:
    candidate = (value or "").strip().lower().replace("-", "_")
    if candidate in ("http", "streamable-http", "streamable_http"):
        return "streamable_http"
    if candidate == "stdio":
        return "stdio"
    if candidate in ("", "disabled", "off", "none"):
        return default
    return "disabled"


def server_configs() -> dict[str, MCPServerConfig]:
    """Build the MCP server table from settings."""
    settings = get_settings()
    timeout = settings.mcp_timeout_seconds

    return {
        "aviation": MCPServerConfig(
            name="aviation",
            transport=_normalise(settings.mcp_aviation_transport),
            url=settings.mcp_aviation_url,
            timeout_seconds=timeout,
            description="Flight schedules, routes and airport lookup.",
        ),
        "search": MCPServerConfig(
            name="search",
            transport=_normalise(settings.mcp_search_transport),
            url=settings.mcp_search_url,
            timeout_seconds=timeout,
            description="Web search used for hotel and destination research.",
        ),
        "weather": MCPServerConfig(
            name="weather",
            transport=_normalise(settings.mcp_weather_transport, default="stdio"),
            url=settings.mcp_weather_url,
            command="python",
            args=("-m", "app.mcp.weather_server"),
            timeout_seconds=timeout,
            description="JourneyMesh custom weather MCP server.",
        ),
    }


def get_server_config(name: str) -> MCPServerConfig | None:
    return server_configs().get(name)
