"""Weather MCP adapter.

The simplest of the three, because we wrote the server. Its tools take the
same arguments the in-process functions take and return the same schema, so
the adapter is close to an identity mapping - which is the point: the local
adapter and the MCP server are two transports for one contract, and swapping
between them must not change what an agent sees.
"""

from __future__ import annotations

from typing import Any

from app.mcp.providers.base import RemoteCall

_TOOLS = {
    "get_current_weather": "current_weather",
    "get_weather_forecast": "weather_forecast",
}


class WeatherAdapter:
    def to_remote(self, tool: str, arguments: dict[str, Any]) -> RemoteCall | None:
        remote = _TOOLS.get(tool)
        if remote is None:
            return None

        args: dict[str, Any] = {}
        location = arguments.get("location") or arguments.get("city")
        if not location:
            return None
        args["location"] = location

        if remote == "weather_forecast":
            days = arguments.get("days")
            if days is not None:
                args["days"] = int(days)
        return RemoteCall(tool=remote, arguments=args)

    def from_remote(
        self, tool: str, payload: dict[str, Any], arguments: dict[str, Any]
    ) -> dict[str, Any] | None:
        # The server returns this application's own schema, including the
        # source label, so nothing needs reshaping. The check is a guard
        # against a differently-configured server answering on this transport.
        if not isinstance(payload, dict):
            return None
        if "source" not in payload:
            return None
        return payload
