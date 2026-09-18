"""Search and selection endpoints.

Search is separate from planning on purpose. ``POST /trips/plan`` runs the
agent graph and takes as long as that takes; a search is a provider round trip
and has to feel like one, so it has its own endpoints, its own timeout budget
and its own persistence.

Every response says which provider answered and with what kind of data. A
result set built from the offline provider is labelled MOCK on every card and
in the response notes, because the one thing this system must never do is let
offline prices pass for live ones.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import db_session, optional_user, session_header
from app.core.exceptions import TripNotFound
from app.db.models import Trip, User
from app.schemas.common import TravelCrewModel
from app.schemas.offers import SortMode
from app.schemas.search import (
    ActivitySearchCriteria,
    ActivitySearchResults,
    FlightSearchCriteria,
    FlightSearchResults,
    HotelSearchCriteria,
    HotelSearchResults,
)
from app.services import ranking
from app.services.budget_engine import BudgetEngine
from app.services.preference_service import PreferenceService
from app.services.search_service import SearchService

router = APIRouter(tags=["search"])


def search_service(session: Session = Depends(db_session)) -> SearchService:
    return SearchService(session)


def _trip_or_404(session: Session, trip_id: str) -> Trip:
    trip = session.get(Trip, trip_id)
    if trip is None:
        raise TripNotFound(f"trip {trip_id} does not exist")
    return trip


# ---- request bodies -----------------------------------------------------
class NaturalSearchRequest(TravelCrewModel):
    """A search stated in a sentence.

    ``execute`` defaults to false: the parsed criteria come back first so the
    traveller can see what was understood - and correct an assumption such as a
    guessed child age - before a provider is called.
    """

    query: str
    execute: bool = False
    sort: SortMode = "cheapest"
    today: date | None = None


class ParsedSearchResponse(TravelCrewModel):
    understood: dict[str, Any]
    criteria: FlightSearchCriteria | None = None
    missing: list[str] = []
    assumptions: list[str] = []
    used_model: bool = False
    results: FlightSearchResults | None = None


class SelectRequest(TravelCrewModel):
    offer_ref: str


class SelectionOut(TravelCrewModel):
    id: str
    trip_id: str
    offer_ref: str
    kind: str
    title: str
    travelers: int
    total_amount: str
    currency: str
    status: str
    source: str


class SelectionResponse(TravelCrewModel):
    selection: SelectionOut
    budget: Any


class SelectionListResponse(TravelCrewModel):
    items: list[SelectionOut] = []
    total: int = 0
    budget: Any = None


# ---- flights ------------------------------------------------------------
@router.post(
    "/trips/{trip_id}/flights/search",
    response_model=FlightSearchResults,
    summary="Search flights for a journey",
    description=(
        "Default order is cheapest first, by **total payable** for the whole party - "
        "fare plus taxes plus mandatory fees plus the baggage this search asked for, "
        "never the headline base fare. Each result carries what choosing it would do "
        "to the journey's budget, computed by the budget engine rather than the "
        "interface."
    ),
)
async def search_flights_for_trip(
    trip_id: str,
    criteria: FlightSearchCriteria,
    sort: SortMode = Query(default="cheapest"),
    service: SearchService = Depends(search_service),
    session: Session = Depends(db_session),
    user: User | None = Depends(optional_user),
    session_id: str | None = Depends(session_header),
) -> FlightSearchResults:
    _trip_or_404(session, trip_id)
    _validate_sort(sort, "flight")
    return await service.search_flights(
        criteria,
        trip_id=trip_id,
        sort=sort,
        user_id=user.id if user else None,
        session_id=session_id,
    )


@router.post(
    "/flights/search",
    response_model=FlightSearchResults,
    summary="Search flights without a journey",
    description="The same search, with no budget context attached to the results.",
)
async def search_flights(
    criteria: FlightSearchCriteria,
    sort: SortMode = Query(default="cheapest"),
    service: SearchService = Depends(search_service),
    user: User | None = Depends(optional_user),
    session_id: str | None = Depends(session_header),
) -> FlightSearchResults:
    _validate_sort(sort, "flight")
    return await service.search_flights(
        criteria, sort=sort, user_id=user.id if user else None, session_id=session_id
    )


@router.post(
    "/flights/search/natural",
    response_model=ParsedSearchResponse,
    summary="Turn a sentence into a flight search",
    description=(
        "Reads a request such as *\"cheapest flights from Dhaka to Rome for two adults "
        "and one child around June 10, flexible by three days, under $2,000 total, max "
        "one stop\"* into structured criteria. Any amount comes from the traveller's own "
        "words, never from a model. Set `execute` to run the search in the same call."
    ),
)
async def search_flights_natural(
    payload: NaturalSearchRequest,
    trip_id: str | None = Query(default=None),
    service: SearchService = Depends(search_service),
    session: Session = Depends(db_session),
    user: User | None = Depends(optional_user),
    session_id: str | None = Depends(session_header),
) -> ParsedSearchResponse:
    from app.agents import search_parser

    defaults: dict[str, Any] = {}
    if trip_id:
        trip = _trip_or_404(session, trip_id)
        brief = PreferenceService(session).get_or_default(trip)
        defaults = {
            "origin": trip.origin,
            "destination": trip.destination,
            "adults": brief.adults,
            "children": brief.children,
            "child_ages": brief.child_ages or None,
            "cabin_class": brief.cabin_class,
            "max_stops": brief.max_stops,
            "baggage": brief.baggage,
            "currency": trip.currency,
        }

    parsed = await search_parser.parse(
        payload.query, today=payload.today, defaults=defaults
    )

    results = None
    if payload.execute and parsed.criteria is not None:
        _validate_sort(payload.sort, "flight")
        results = await service.search_flights(
            parsed.criteria,
            trip_id=trip_id,
            sort=payload.sort,
            user_id=user.id if user else None,
            session_id=session_id,
        )

    return ParsedSearchResponse(
        understood={
            key: (value.isoformat() if hasattr(value, "isoformat") else value)
            for key, value in parsed.fields.items()
            if not key.startswith("_")
        },
        criteria=parsed.criteria,
        missing=parsed.missing,
        assumptions=parsed.assumptions,
        used_model=parsed.used_model,
        results=results,
    )


# ---- hotels -------------------------------------------------------------
@router.post(
    "/trips/{trip_id}/hotels/search",
    response_model=HotelSearchResults,
    summary="Search accommodation for a journey",
    description=(
        "Ordered by **total stay cost** by default, taxes and fees included - not by "
        "nightly rate. A hotel that looks cheap per night and is not cheap for the "
        "stay must not win a cheapest sort."
    ),
)
async def search_hotels_for_trip(
    trip_id: str,
    criteria: HotelSearchCriteria,
    sort: SortMode = Query(default="cheapest"),
    service: SearchService = Depends(search_service),
    session: Session = Depends(db_session),
    user: User | None = Depends(optional_user),
    session_id: str | None = Depends(session_header),
) -> HotelSearchResults:
    _trip_or_404(session, trip_id)
    _validate_sort(sort, "hotel")
    return await service.search_hotels(
        criteria,
        trip_id=trip_id,
        sort=sort,
        user_id=user.id if user else None,
        session_id=session_id,
    )


@router.post("/hotels/search", response_model=HotelSearchResults, summary="Search accommodation")
async def search_hotels(
    criteria: HotelSearchCriteria,
    sort: SortMode = Query(default="cheapest"),
    service: SearchService = Depends(search_service),
    user: User | None = Depends(optional_user),
    session_id: str | None = Depends(session_header),
) -> HotelSearchResults:
    _validate_sort(sort, "hotel")
    return await service.search_hotels(
        criteria, sort=sort, user_id=user.id if user else None, session_id=session_id
    )


# ---- activities ---------------------------------------------------------
@router.post(
    "/trips/{trip_id}/activities/search",
    response_model=ActivitySearchResults,
    summary="Search activities for a journey",
)
async def search_activities_for_trip(
    trip_id: str,
    criteria: ActivitySearchCriteria,
    sort: SortMode = Query(default="cheapest"),
    service: SearchService = Depends(search_service),
    session: Session = Depends(db_session),
    user: User | None = Depends(optional_user),
    session_id: str | None = Depends(session_header),
) -> ActivitySearchResults:
    _trip_or_404(session, trip_id)
    _validate_sort(sort, "activity")
    return await service.search_activities(
        criteria,
        trip_id=trip_id,
        sort=sort,
        user_id=user.id if user else None,
        session_id=session_id,
    )


# ---- selection ----------------------------------------------------------
@router.post(
    "/trips/{trip_id}/selections",
    response_model=SelectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Choose an offer for a journey",
    description=(
        "Charges the journey's budget for the offer and returns the budget that "
        "results. Choosing a second flight supersedes the first and reverses its "
        "budget line rather than adding to it. An expired offer is refused: a stale "
        "quote must never become a commitment."
    ),
)
async def select_offer(
    trip_id: str,
    payload: SelectRequest,
    service: SearchService = Depends(search_service),
    session: Session = Depends(db_session),
    user: User | None = Depends(optional_user),
) -> SelectionResponse:
    _trip_or_404(session, trip_id)
    selection, budget = await service.select(
        trip_id, offer_ref=payload.offer_ref, selected_by=user.id if user else None
    )
    return SelectionResponse(selection=_selection_out(selection), budget=budget)


@router.get(
    "/trips/{trip_id}/selections",
    response_model=SelectionListResponse,
    summary="What has been chosen for this journey",
)
def list_selections(
    trip_id: str,
    service: SearchService = Depends(search_service),
    session: Session = Depends(db_session),
) -> SelectionListResponse:
    _trip_or_404(session, trip_id)
    items = [_selection_out(selection) for selection in service.selections(trip_id)]
    return SelectionListResponse(
        items=items, total=len(items), budget=BudgetEngine(session).snapshot(trip_id)
    )


@router.delete(
    "/trips/{trip_id}/selections/{selection_id}",
    response_model=SelectionListResponse,
    summary="Unchoose an offer",
    description="Reverses the budget line the selection created. Nothing is deleted.",
)
def remove_selection(
    trip_id: str,
    selection_id: str,
    service: SearchService = Depends(search_service),
    session: Session = Depends(db_session),
    user: User | None = Depends(optional_user),
) -> SelectionListResponse:
    _trip_or_404(session, trip_id)
    budget = service.deselect(trip_id, selection_id, actor=user.id if user else None)
    items = [_selection_out(selection) for selection in service.selections(trip_id)]
    return SelectionListResponse(items=items, total=len(items), budget=budget)


# ---- helpers ------------------------------------------------------------
def _validate_sort(sort: SortMode, kind: str) -> None:
    allowed = ranking.sorts_for(kind)
    if sort not in allowed:
        from app.core.exceptions import ValidationRejection

        raise ValidationRejection(
            f"sort must be one of {', '.join(allowed)} for a {kind} search"
        )


def _selection_out(selection: Any) -> SelectionOut:
    offer = selection.offer
    return SelectionOut(
        id=selection.id,
        trip_id=selection.trip_id,
        offer_ref=offer.offer_ref if offer else "",
        kind=selection.kind,
        title=offer.title if offer else "",
        travelers=selection.travelers,
        total_amount=str(selection.total_amount),
        currency=selection.currency,
        status=selection.status,
        source=offer.source if offer else "MOCK",
    )
