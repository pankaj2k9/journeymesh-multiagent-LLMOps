"""Where the planner can take you.

One read, built from the airport reference table the flight agent and the
query parser already use, so a city offered as a button is always a city the
agents can resolve. Countries and cities are served, never hard-coded twice.
"""

from __future__ import annotations

import string
from functools import cache

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import db_session
from app.db.models import Attraction
from app.mcp.aviation import AIRPORTS
from app.media import storage
from app.schemas.common import TravelCrewModel

router = APIRouter(prefix="/places", tags=["places"])

# Keys in the reference table that are alternative spellings of another key,
# kept there so free text resolves, but not offered as a second button.
_ALIASES = frozenset(
    {"new delhi", "bangalore", "malé", "st. martin's island", "srimangal"}
)

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


# ---- attractions ---------------------------------------------------------------


class AttractionImageOut(TravelCrewModel):
    url: str
    # A smaller rendition for cards, when the media pipeline produced one.
    card_url: str
    width: int | None = None
    height: int | None = None
    # Free licences require the credit to travel with the picture.
    author: str = ""
    license: str = ""
    license_url: str = ""
    source_url: str = ""


class AttractionOut(TravelCrewModel):
    slug: str
    name: str
    city: str
    country: str
    description: str = ""
    summary: str = ""
    wikipedia_url: str = ""
    image: AttractionImageOut | None = None


class AttractionListResponse(TravelCrewModel):
    items: list[AttractionOut]
    total: int


def _attraction_out(row: Attraction) -> AttractionOut:
    image = None
    asset = row.image
    if asset is not None:
        files = storage.get_storage()
        derivatives = asset.derivatives or {}
        card = derivatives.get("small") or derivatives.get("medium") or {}
        image = AttractionImageOut(
            url=files.get_url(asset.relative_path),
            card_url=files.get_url(card["path"]) if card.get("path") else files.get_url(
                asset.relative_path
            ),
            width=asset.width,
            height=asset.height,
            author=row.image_author,
            license=row.image_license,
            license_url=row.image_license_url,
            source_url=row.image_source_url,
        )
    return AttractionOut(
        slug=row.slug,
        name=row.name,
        city=row.city,
        country=row.country,
        description=row.description,
        summary=row.summary,
        wikipedia_url=row.wikipedia_url,
        image=image,
    )


@router.get(
    "/attractions",
    response_model=AttractionListResponse,
    summary="Places worth visiting in a city or a country",
    description=(
        "Filter by `city`, by `country`, or both, or ask for specific `slug`s. "
        "Most notable first. Each photo "
        "carries its author and licence, which must be shown with it."
    ),
)
def list_attractions(
    response: Response,
    city: str | None = Query(default=None, max_length=120),
    country: str | None = Query(default=None, max_length=120),
    slug: list[str] | None = Query(default=None, max_length=24),
    limit: int = Query(default=6, ge=1, le=24),
    session: Session = Depends(db_session),
) -> AttractionListResponse:
    stmt = select(Attraction).where(Attraction.is_active.is_(True))
    if city:
        stmt = stmt.where(Attraction.city.ilike(city.strip()))
    if country:
        stmt = stmt.where(Attraction.country.ilike(country.strip()))
    if slug:
        stmt = stmt.where(Attraction.slug.in_(slug))
    stmt = stmt.order_by(Attraction.sort_order, Attraction.city, Attraction.name).limit(limit)
    items = [_attraction_out(row) for row in session.scalars(stmt).unique()]
    response.headers["Cache-Control"] = "public, max-age=300"
    return AttractionListResponse(items=items, total=len(items))
