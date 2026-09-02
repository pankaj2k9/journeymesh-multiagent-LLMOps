"""MCP tool discovery.

The registry is the single place that knows which tool lives on which server
and what its in-process implementation is. Nothing here decides whether a
call is *allowed* - that is the Tool Guard's job.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.mcp import aviation, search, weather_server
from app.mcp.config import MCPServerConfig, server_configs

ToolImpl = Callable[..., Awaitable[dict[str, Any]] | dict[str, Any]]


@dataclass(frozen=True)
class ToolDescriptor:
    name: str
    server: str
    implementation: ToolImpl
    remote_name: str | None = None
    description: str = ""


_DESCRIPTORS: tuple[ToolDescriptor, ...] = (
    ToolDescriptor(
        name="lookup_airport",
        server="aviation",
        implementation=aviation.lookup_airport,
        remote_name="lookup_airport",
        description="Resolve a city name to its primary airport.",
    ),
    ToolDescriptor(
        name="search_flights",
        server="aviation",
        implementation=aviation.search_flights,
        remote_name="search_flights",
        description="Find routes, carriers and available pricing between two cities.",
    ),
    ToolDescriptor(
        name="web_search",
        server="search",
        implementation=search.web_search,
        remote_name="search",
        description="Search the public web for destination research.",
    ),
    ToolDescriptor(
        name="search_hotels",
        server="search",
        implementation=search.search_hotels,
        remote_name="search",
        description="Find accommodation candidates for a destination.",
    ),
    ToolDescriptor(
        name="get_current_weather",
        server="weather",
        implementation=weather_server.get_current_weather,
        remote_name="current_weather",
        description="Current conditions at a destination.",
    ),
    ToolDescriptor(
        name="get_weather_forecast",
        server="weather",
        implementation=weather_server.get_weather_forecast,
        remote_name="weather_forecast",
        description="Multi-day forecast with packing and activity guidance.",
    ),
)

_BY_NAME = {descriptor.name: descriptor for descriptor in _DESCRIPTORS}


def discover() -> list[ToolDescriptor]:
    """Return every tool JourneyMesh knows how to invoke."""
    return list(_DESCRIPTORS)


def get(tool_name: str) -> ToolDescriptor | None:
    return _BY_NAME.get(tool_name)


def tools_for_server(server_name: str) -> list[ToolDescriptor]:
    return [descriptor for descriptor in _DESCRIPTORS if descriptor.server == server_name]


def server_for(tool_name: str) -> MCPServerConfig | None:
    descriptor = get(tool_name)
    if descriptor is None:
        return None
    return server_configs().get(descriptor.server)


def catalogue() -> list[dict[str, Any]]:
    """Human-readable tool catalogue, used by the health endpoint."""
    configs = server_configs()
    return [
        {
            "tool": descriptor.name,
            "server": descriptor.server,
            "transport": configs[descriptor.server].transport
            if descriptor.server in configs
            else "in_process",
            "remote": bool(descriptor.server in configs and configs[descriptor.server].enabled),
            "description": descriptor.description,
        }
        for descriptor in _DESCRIPTORS
    ]
