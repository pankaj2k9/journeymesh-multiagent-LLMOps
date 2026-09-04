"""Tavily MCP adapter.

Tavily's hosted server exposes ``tavily_search``. JourneyMesh has two search
tools - a general one and a hotel-shaped one - and both become the same remote
call with a different query. The response is reshaped into the structure
``app.mcp.search.web_search`` returns, so an agent cannot tell which transport
answered.

``search_hotels`` deliberately declines. Its in-process implementation does
more than search: it bands prices by travel style and builds candidate records
the budget agent reads. A raw list of web results cannot substitute for that
without inventing prices, so the hotel path uses the local implementation -
which itself calls the search tool - and the traveller gets an honest
`SEARCH_DERIVED` label rather than a fabricated nightly rate.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.constants import SOURCE_SEARCH_DERIVED
from app.mcp.providers.base import RemoteCall

REMOTE_SEARCH_TOOL = "tavily_search"


class SearchAdapter:
    def to_remote(self, tool: str, arguments: dict[str, Any]) -> RemoteCall | None:
        if tool != "web_search":
            # search_hotels: see the module docstring.
            return None

        query = (arguments.get("query") or "").strip()
        if not query:
            return None

        max_results = arguments.get("max_results", 5)
        try:
            max_results = max(1, min(int(max_results), 10))
        except (TypeError, ValueError):
            max_results = 5

        return RemoteCall(
            tool=REMOTE_SEARCH_TOOL,
            arguments={"query": query, "max_results": max_results},
        )

    def from_remote(
        self, tool: str, payload: dict[str, Any], arguments: dict[str, Any]
    ) -> dict[str, Any] | None:
        items = _results_from(payload)
        if items is None:
            return None

        return {
            "query": arguments.get("query", ""),
            "results": [
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "snippet": item.get("content") or item.get("snippet"),
                    "score": item.get("score"),
                }
                for item in items
                if isinstance(item, dict)
            ],
            "source": SOURCE_SEARCH_DERIVED,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "transport": "mcp",
        }


def _results_from(payload: Any) -> list[Any] | None:
    """Find the result list in whatever shape the server replied with.

    Tavily has returned results under a couple of different keys across
    versions, and an MCP server may wrap them again. Rather than pin one
    shape, look for the plausible ones and decline if none is present.
    """
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return None
    for key in ("results", "data", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return None
