"""Adapters between JourneyMesh tool calls and real MCP server tools.

A remote MCP server is somebody else's contract. Its tool is not called what
our tool is called, its arguments are not our arguments, and its response is
not our schema. Something has to translate, and it must not be the agent:
``weather_agent`` should ask for a forecast and receive a forecast, without
knowing that a subprocess was started or that Tavily calls its search tool
``tavily_search``.

That translation lives here, one module per server:

    agent -> MCPClient -> providers.adapter_for(server) -> MCP server
                       <- application-shaped dict      <-

An adapter may decline. Returning ``None`` from ``to_remote`` means "this tool
has no faithful remote equivalent", and the client uses the in-process adapter
instead. Declining is better than guessing: a plausible-looking flight result
assembled from the wrong endpoint is worse than an honest estimate, and the
provider status says which one the traveller actually got.
"""

from __future__ import annotations

from app.mcp.providers.aviation import AviationAdapter
from app.mcp.providers.base import RemoteCall, ToolAdapter
from app.mcp.providers.search import SearchAdapter
from app.mcp.providers.weather import WeatherAdapter

_ADAPTERS: dict[str, ToolAdapter] = {
    "aviation": AviationAdapter(),
    "search": SearchAdapter(),
    "weather": WeatherAdapter(),
}


def adapter_for(server_name: str) -> ToolAdapter | None:
    """The adapter that translates for one MCP server, if there is one."""
    return _ADAPTERS.get(server_name)


__all__ = ["RemoteCall", "ToolAdapter", "adapter_for"]
