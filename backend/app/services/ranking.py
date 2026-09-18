"""Ordering offers, and saying why.

Two rules drive everything here.

**Cheapest means cheapest total payable.** Not the base fare, not the headline
nightly rate. A fare that excludes the checked bag this search asked for is not
cheaper than one that includes it, and a hotel at $82 a night is not cheaper
over five nights than one at $86 whose rate includes the city tax. Sorting on a
headline number is the single most common way a travel product misleads
somebody, and it is a one-line bug: pick the wrong field.

**Nothing is hidden, everything is labelled.** An offer over budget is ranked,
shown and badged ``OVER_BUDGET``. The system's job is to make the consequence
legible, not to decide for the traveller that they cannot afford it.

Badges are computed across the *whole* result set before sorting, so "CHEAPEST"
means cheapest of everything that matched - not cheapest of the current page,
and not whatever happens to be first under the chosen sort.

No model is involved in any of this.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import TypeVar

from app.schemas.offers import ActivityOffer, Badge, FlightOffer, HotelOffer, SortMode
from app.schemas.search import (
    BudgetSnapshotForOffer,
    RankedActivityOffer,
    RankedFlightOffer,
    RankedHotelOffer,
)
from app.services.money import to_decimal

T = TypeVar("T")

FLIGHT_SORTS: tuple[SortMode, ...] = (
    "cheapest",
    "best_value",
    "fastest",
    "fewest_stops",
    "recommended",
)
HOTEL_SORTS: tuple[SortMode, ...] = (
    "cheapest",
    "best_value",
    "rating",
    "distance",
    "recommended",
)
ACTIVITY_SORTS: tuple[SortMode, ...] = ("cheapest", "best_value", "rating", "recommended")

# How much a "best value" score weighs each axis. Price dominates, because a
# traveller sorting a travel search is mostly spending money; the rest exists
# so that a fare which is five dollars cheaper and nine hours longer does not
# win.
_FLIGHT_WEIGHTS = {"price": 0.60, "duration": 0.28, "stops": 0.12}
_HOTEL_WEIGHTS = {"price": 0.55, "review": 0.30, "distance": 0.15}


# ---- the one definition of "what this costs" ----------------------------
def flight_total(offer: FlightOffer) -> Decimal:
    """Total payable for the whole party: fare + taxes + fees + asked-for bags.

    ``PriceBreakdown.total`` is computed from its parts, and ``total_price``
    accounts for children being cheaper than adults, so this is the number a
    traveller would actually be charged - which is the only number "cheapest"
    can honestly mean.
    """
    return to_decimal(offer.total_price)


def hotel_total(offer: HotelOffer) -> Decimal:
    """Total for the whole stay, taxes and fees included."""
    return to_decimal(offer.total_stay)


def activity_total(offer: ActivityOffer) -> Decimal:
    return to_decimal(offer.total_price)


# ---- normalisation ------------------------------------------------------
def _normalise(values: Sequence[float], *, lower_is_better: bool) -> list[float]:
    """Map values onto 0..1 where 1 is always better.

    An all-equal set scores 1.0 rather than dividing by zero - when every
    option is the same on an axis, that axis should not penalise anybody.
    """
    if not values:
        return []
    low, high = min(values), max(values)
    if high == low:
        return [1.0] * len(values)
    span = high - low
    if lower_is_better:
        return [(high - value) / span for value in values]
    return [(value - low) / span for value in values]


@dataclass(frozen=True)
class _Scored:
    index: int
    score: float


def _weighted(axes: dict[str, tuple[list[float], float]]) -> list[float]:
    """Combine normalised axes by weight into one score per offer."""
    length = len(next(iter(axes.values()))[0]) if axes else 0
    scores = [0.0] * length
    for normalised, weight in axes.values():
        for index, value in enumerate(normalised):
            scores[index] += value * weight
    return scores


# ---- flights ------------------------------------------------------------
def rank_flights(
    offers: Sequence[FlightOffer],
    *,
    sort: SortMode = "cheapest",
    budgets: dict[str, BudgetSnapshotForOffer] | None = None,
) -> list[RankedFlightOffer]:
    """Badge, score and order a flight result set."""
    if not offers:
        return []

    totals = [float(flight_total(offer)) for offer in offers]
    durations = [float(offer.total_duration_minutes or 0) for offer in offers]
    stops = [float(offer.stops) for offer in offers]

    value_scores = _weighted(
        {
            "price": (_normalise(totals, lower_is_better=True), _FLIGHT_WEIGHTS["price"]),
            "duration": (
                _normalise(durations, lower_is_better=True),
                _FLIGHT_WEIGHTS["duration"],
            ),
            "stops": (_normalise(stops, lower_is_better=True), _FLIGHT_WEIGHTS["stops"]),
        }
    )

    cheapest_index = _argmin(totals)
    fastest_index = _argmin(durations)
    best_value_index = _argmax(value_scores)
    # Only badge FEWEST_STOPS when one offer is genuinely alone at the top. In
    # a list with four non-stops the badge says nothing, and handing it to
    # whichever happened to be first would make an expensive option look
    # distinguished.
    fewest_index = _unique_argmin(stops)

    ranked: list[RankedFlightOffer] = []
    for index, offer in enumerate(offers):
        badges: list[Badge] = []
        if index == cheapest_index:
            badges.append("CHEAPEST")
        if index == best_value_index and index != cheapest_index:
            badges.append("BEST_VALUE")
        if index == fastest_index:
            badges.append("FASTEST")
        if index == fewest_index and "FASTEST" not in badges:
            badges.append("FEWEST_STOPS")

        budget = (budgets or {}).get(offer.offer_id)
        if budget is not None and budget.within_budget is not None:
            badges.append("WITHIN_BUDGET" if budget.within_budget else "OVER_BUDGET")

        ranked.append(
            RankedFlightOffer(
                offer=offer,
                badges=badges,
                budget=budget,
                value_score=round(value_scores[index], 4),
                rank_reason=_flight_reason(offer, badges),
            )
        )

    return _order(ranked, sort=sort, key=_flight_sort_key)


def _flight_sort_key(sort: SortMode) -> Callable[[RankedFlightOffer], tuple]:
    def cheapest(item: RankedFlightOffer) -> tuple:
        # Ties break towards the shorter, less-connected itinerary: same money,
        # less of the traveller's day.
        return (
            flight_total(item.offer),
            item.offer.total_duration_minutes or 0,
            item.offer.stops,
        )

    def fastest(item: RankedFlightOffer) -> tuple:
        return (
            item.offer.total_duration_minutes or 0,
            flight_total(item.offer),
            item.offer.stops,
        )

    def fewest_stops(item: RankedFlightOffer) -> tuple:
        return (
            item.offer.stops,
            flight_total(item.offer),
            item.offer.total_duration_minutes or 0,
        )

    def best_value(item: RankedFlightOffer) -> tuple:
        return (-(item.value_score or 0.0), flight_total(item.offer))

    def recommended(item: RankedFlightOffer) -> tuple:
        # Recommended is best value with one extra rule: an option the
        # traveller cannot afford does not lead the list. It is still shown,
        # and still badged, just not put first.
        over = item.budget is not None and item.budget.within_budget is False
        return (1 if over else 0, -(item.value_score or 0.0), flight_total(item.offer))

    return {
        "cheapest": cheapest,
        "fastest": fastest,
        "fewest_stops": fewest_stops,
        "best_value": best_value,
        "recommended": recommended,
    }.get(sort, cheapest)


def _flight_reason(offer: FlightOffer, badges: list[Badge]) -> str:
    if "CHEAPEST" in badges:
        return "Lowest total price for your party, including taxes and the baggage you asked for."
    if "BEST_VALUE" in badges:
        return "The best balance of price, journey time and connections."
    if "FASTEST" in badges:
        return "The shortest total journey time."
    if offer.stops == 0:
        return "Non-stop."
    return f"{offer.stops} stop(s)."


# ---- hotels -------------------------------------------------------------
def rank_hotels(
    offers: Sequence[HotelOffer],
    *,
    sort: SortMode = "cheapest",
    budgets: dict[str, BudgetSnapshotForOffer] | None = None,
) -> list[RankedHotelOffer]:
    if not offers:
        return []

    totals = [float(hotel_total(offer)) for offer in offers]
    reviews = [float(offer.review_score or 0) for offer in offers]
    distances = [float(offer.distance_to_centre_km or 0) for offer in offers]

    value_scores = _weighted(
        {
            "price": (_normalise(totals, lower_is_better=True), _HOTEL_WEIGHTS["price"]),
            "review": (_normalise(reviews, lower_is_better=False), _HOTEL_WEIGHTS["review"]),
            "distance": (
                _normalise(distances, lower_is_better=True),
                _HOTEL_WEIGHTS["distance"],
            ),
        }
    )

    cheapest_index = _argmin(totals)
    best_value_index = _argmax(value_scores)

    ranked: list[RankedHotelOffer] = []
    for index, offer in enumerate(offers):
        badges: list[Badge] = []
        if index == cheapest_index:
            badges.append("CHEAPEST")
        if index == best_value_index and index != cheapest_index:
            badges.append("BEST_VALUE")

        budget = (budgets or {}).get(offer.offer_id)
        if budget is not None and budget.within_budget is not None:
            badges.append("WITHIN_BUDGET" if budget.within_budget else "OVER_BUDGET")

        ranked.append(
            RankedHotelOffer(
                offer=offer,
                badges=badges,
                budget=budget,
                value_score=round(value_scores[index], 4),
                rank_reason=_hotel_reason(offer, badges),
            )
        )

    return _order(ranked, sort=sort, key=_hotel_sort_key)


def _hotel_sort_key(sort: SortMode) -> Callable[[RankedHotelOffer], tuple]:
    def cheapest(item: RankedHotelOffer) -> tuple:
        return (hotel_total(item.offer), -(item.offer.review_score or 0))

    def rating(item: RankedHotelOffer) -> tuple:
        return (-(item.offer.review_score or 0), hotel_total(item.offer))

    def distance(item: RankedHotelOffer) -> tuple:
        # An unknown distance sorts last rather than first; treating "unknown"
        # as "zero km from the centre" would put it at the top of the list.
        km = item.offer.distance_to_centre_km
        return (km if km is not None else float("inf"), hotel_total(item.offer))

    def best_value(item: RankedHotelOffer) -> tuple:
        return (-(item.value_score or 0.0), hotel_total(item.offer))

    def recommended(item: RankedHotelOffer) -> tuple:
        over = item.budget is not None and item.budget.within_budget is False
        return (1 if over else 0, -(item.value_score or 0.0), hotel_total(item.offer))

    return {
        "cheapest": cheapest,
        "rating": rating,
        "distance": distance,
        "best_value": best_value,
        "recommended": recommended,
    }.get(sort, cheapest)


def _hotel_reason(offer: HotelOffer, badges: list[Badge]) -> str:
    if "CHEAPEST" in badges:
        return "Lowest total for the whole stay, taxes and fees included."
    if "BEST_VALUE" in badges:
        return "The best balance of stay cost, guest score and location."
    if offer.cancellation.free_cancellation:
        return "Free cancellation."
    return f"{offer.nights} night(s) in {offer.area or 'this area'}."


# ---- activities ---------------------------------------------------------
def rank_activities(
    offers: Sequence[ActivityOffer],
    *,
    sort: SortMode = "cheapest",
    budgets: dict[str, BudgetSnapshotForOffer] | None = None,
) -> list[RankedActivityOffer]:
    if not offers:
        return []

    totals = [float(activity_total(offer)) for offer in offers]
    ratings = [float(offer.rating or 0) for offer in offers]
    value_scores = _weighted(
        {
            "price": (_normalise(totals, lower_is_better=True), 0.6),
            "rating": (_normalise(ratings, lower_is_better=False), 0.4),
        }
    )

    cheapest_index = _argmin(totals)
    best_value_index = _argmax(value_scores)

    ranked: list[RankedActivityOffer] = []
    for index, offer in enumerate(offers):
        badges: list[Badge] = []
        if index == cheapest_index:
            badges.append("CHEAPEST")
        if index == best_value_index and index != cheapest_index:
            badges.append("BEST_VALUE")
        budget = (budgets or {}).get(offer.offer_id)
        if budget is not None and budget.within_budget is not None:
            badges.append("WITHIN_BUDGET" if budget.within_budget else "OVER_BUDGET")
        ranked.append(RankedActivityOffer(offer=offer, badges=badges, budget=budget))

    def key(item: RankedActivityOffer) -> tuple:
        if sort == "rating":
            return (-(item.offer.rating or 0), activity_total(item.offer))
        if sort in ("best_value", "recommended"):
            index = offers.index(item.offer)
            return (-value_scores[index], activity_total(item.offer))
        return (activity_total(item.offer), -(item.offer.rating or 0))

    return sorted(ranked, key=key)


# ---- helpers ------------------------------------------------------------
def _order(items: list[T], *, sort: SortMode, key: Callable[[SortMode], Callable[[T], tuple]]) -> list[T]:
    return sorted(items, key=key(sort))


def _argmin(values: Sequence[float]) -> int:
    return min(range(len(values)), key=lambda index: values[index])


def _argmax(values: Sequence[float]) -> int:
    return max(range(len(values)), key=lambda index: values[index])


def _unique_argmin(values: Sequence[float]) -> int | None:
    """The index of the minimum, or None when more than one offer shares it."""
    if not values:
        return None
    lowest = min(values)
    winners = [index for index, value in enumerate(values) if value == lowest]
    return winners[0] if len(winners) == 1 else None


def sorts_for(kind: str) -> tuple[SortMode, ...]:
    return {
        "flight": FLIGHT_SORTS,
        "hotel": HOTEL_SORTS,
        "activity": ACTIVITY_SORTS,
    }.get(kind, FLIGHT_SORTS)


__all__ = [
    "ACTIVITY_SORTS",
    "FLIGHT_SORTS",
    "HOTEL_SORTS",
    "activity_total",
    "flight_total",
    "hotel_total",
    "rank_activities",
    "rank_flights",
    "rank_hotels",
    "sorts_for",
]
