"""Where the planner can take you.

One read, built from the airport reference table the flight agent and the
query parser already use, so a city offered as a button is always a city the
agents can resolve. Countries and cities are served, never hard-coded twice.
"""

from __future__ import annotations

import string
from functools import cache

from fastapi import APIRouter, Response

from app.mcp.aviation import AIRPORTS
from app.schemas.common import TravelCrewModel

router = APIRouter(prefix="/places", tags=["places"])

# Keys in the reference table that are alternative spellings of another key,
# kept there so free text resolves, but not offered as a second button.
_ALIASES = frozenset({"new delhi", "bangalore", "malé"})

# Where the table's lower-case key does not capitalise into the usual name.
_DISPLAY = {"male": "Malé"}


class CityOut(TravelCrewModel):
    name: str
    iata: str
    airport: str


class CountryOut(TravelCrewModel):
    name: str
    cities: list[CityOut]


class PlacesResponse(TravelCrewModel):
    countries: list[CountryOut]


@cache
def _places() -> PlacesResponse:
    by_country: dict[str, list[CityOut]] = {}
    for key, record in AIRPORTS.items():
        if key in _ALIASES:
            continue
        city = CityOut(
            name=_DISPLAY.get(key, string.capwords(key)),
            iata=record["iata"],
            airport=record["name"],
        )
        by_country.setdefault(record["country"], []).append(city)

    return PlacesResponse(
        countries=[
            CountryOut(name=country, cities=sorted(cities, key=lambda c: c.name))
            for country, cities in sorted(by_country.items())
        ]
    )


@router.get(
    "",
    response_model=PlacesResponse,
    summary="Countries and the cities the planner can resolve",
    description=(
        "Every city here has an airport the flight agent recognises. The list "
        "changes only with a deployment, so it is safe to cache for an hour."
    ),
)
def list_places(response: Response) -> PlacesResponse:
    response.headers["Cache-Control"] = "public, max-age=3600"
    return _places()
