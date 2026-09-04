"""AviationStack MCP adapter.

The server exposes twelve tools, none of which is shaped like JourneyMesh's
two. ``list_airports`` returns a paginated catalogue rather than a lookup by
city; ``list_routes`` returns scheduled routes with no fares at all.

So only the airport lookup is adapted, and it is adapted defensively: the
remote catalogue is searched for a matching IATA code or city name, and the
result is labelled with the confidence that search actually earned.

``search_flights`` declines on purpose. Its in-process implementation produces
priced options, and AviationStack's route endpoint has no prices - assembling
one from the other would mean inventing the number a traveller is most likely
to act on. The local implementation already calls AviationStack's REST API for
the parts it can verify and labels everything else an ESTIMATE, so declining
here keeps the honest labelling rather than replacing it with a confident
guess.
"""

from __future__ import annotations

from typing import Any

from app.core.constants import SOURCE_LIVE, SOURCE_UNAVAILABLE
from app.mcp.providers.base import RemoteCall

REMOTE_AIRPORTS_TOOL = "list_airports"

# The catalogue is large and paginated. One page is enough to resolve a major
# city, and asking for more would make a cheap lookup expensive.
_AIRPORT_PAGE_SIZE = 100


class AviationAdapter:
    def to_remote(self, tool: str, arguments: dict[str, Any]) -> RemoteCall | None:
        if tool != "lookup_airport":
            # search_flights: see the module docstring.
            return None

        city = (arguments.get("city") or "").strip()
        if not city:
            return None

        return RemoteCall(
            tool=REMOTE_AIRPORTS_TOOL,
            arguments={"limit": _AIRPORT_PAGE_SIZE, "search": city},
        )

    def from_remote(
        self, tool: str, payload: dict[str, Any], arguments: dict[str, Any]
    ) -> dict[str, Any] | None:
        city = (arguments.get("city") or "").strip()
        records = _records_from(payload)
        if records is None:
            return None

        match = _best_match(records, city)
        if match is None:
            return {
                "city": city,
                "iata": None,
                "name": None,
                "country": None,
                "confidence": 0.0,
                "source": SOURCE_UNAVAILABLE,
                "match": "not_in_catalogue",
                "transport": "mcp",
            }

        record, confidence = match
        return {
            "city": city,
            "iata": _first(record, "iata_code", "iataCode", "iata"),
            "name": _first(record, "airport_name", "airportName", "name"),
            "country": _first(record, "country_name", "countryName", "country"),
            "confidence": confidence,
            # A real catalogue entry, not our reference table.
            "source": SOURCE_LIVE,
            "match": "aviationstack_catalogue",
            "transport": "mcp",
        }


def _first(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value:
            return value
    return None


def _records_from(payload: Any) -> list[dict[str, Any]] | None:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return None
    for key in ("data", "airports", "results", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return None


def _best_match(
    records: list[dict[str, Any]], city: str
) -> tuple[dict[str, Any], float] | None:
    """Pick the airport a city name most plausibly means.

    Exact beats partial, and the confidence reported is the confidence the
    match earned - it is read downstream, so inflating it here would quietly
    turn a guess into a fact.
    """
    if not city:
        return None
    needle = city.casefold().strip()

    partial: tuple[dict[str, Any], float] | None = None
    for record in records:
        haystacks = [
            str(_first(record, "city_name", "cityName") or "").casefold(),
            str(_first(record, "airport_name", "airportName", "name") or "").casefold(),
        ]
        if needle in haystacks:
            return record, 1.0
        if partial is None and any(needle and needle in value for value in haystacks):
            partial = (record, 0.6)
    return partial
