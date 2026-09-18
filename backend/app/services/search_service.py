"""Search, rank, price against the budget, persist.

The order matters and is the same for all three domains:

    criteria -> provider (behind a breaker) -> normalised offers
             -> persist a snapshot of each
             -> ask the budget engine what each one would cost
             -> rank and badge across the whole set
             -> return

The budget step is deliberately not the interface's job. "46% of trip budget,
$2,164 remaining" is produced by ``BudgetEngine.impact_of`` - the same function
that runs when the traveller actually selects - so the number on the card and
the number after the click cannot disagree.

Selection is here too, because selecting is a search-result action with a
budget consequence, and doing it in one transaction is what keeps the ledger,
the selection row and the trip's planned cost in step.
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import (
    CATEGORY_ACCOMMODATION,
    CATEGORY_ACTIVITY,
    CATEGORY_FLIGHT,
    ITEM_SELECTED,
    SOURCE_MOCK,
)
from app.core.exceptions import TravelCrewError, TripNotFound
from app.db.models import Offer, Trip
from app.db.repositories import OfferRepository
from app.observability import metrics
from app.observability.logging import get_logger
from app.observability.tracing import span
from app.providers import registry
from app.providers.base import OfferExpired
from app.schemas.offers import (
    ActivityOffer,
    FlightOffer,
    HotelOffer,
    OfferKind,
    SortMode,
)
from app.schemas.search import (
    ActivitySearchCriteria,
    ActivitySearchResults,
    BudgetSnapshotForOffer,
    FlightSearchCriteria,
    FlightSearchResults,
    HotelSearchCriteria,
    HotelSearchResults,
    ProviderNote,
)
from app.services import ranking
from app.services.budget_engine import BudgetEngine
from app.services.currency_service import CurrencyService
from app.services.money import normalise_currency, to_decimal

logger = get_logger("journeymesh.services.search")

# Which budget category each kind of offer charges, and what it replaces when
# a traveller changes their mind.
_CATEGORY = {
    "flight": CATEGORY_FLIGHT,
    "hotel": CATEGORY_ACCOMMODATION,
    "activity": CATEGORY_ACTIVITY,
}

# An activity is additive - a trip has many - so choosing one does not displace
# another. A flight or a hotel does.
_REPLACES = {
    "flight": "flight_offer",
    "hotel": "hotel_offer",
    "activity": None,
}

_SOURCE_TYPE = {
    "flight": "flight_offer",
    "hotel": "hotel_offer",
    "activity": "activity_offer",
}


class SelectionNotFound(TravelCrewError):
    status_code = 404
    code = "selection_not_found"
    safe_message = "That selection could not be found."


class SearchService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.offers = OfferRepository(session)
        self.budgets = BudgetEngine(session)

    # ---- flights ---------------------------------------------------------
    async def search_flights(
        self,
        criteria: FlightSearchCriteria,
        *,
        trip_id: str | None = None,
        sort: SortMode = "cheapest",
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> FlightSearchResults:
        started = time.perf_counter()
        with span("search:flights", kind="tool", trip_id=trip_id):
            outcome = await registry.call(
                registry.flight_provider(),
                "search_flights",
                lambda provider: provider.search_flights(criteria),
                fallback=registry.fallback_flight_provider(),
                kind="flights",
            )

        offers: list[FlightOffer] = list(outcome.offers)
        note = outcome.note or ProviderNote(provider="unknown", ok=False)
        latency = int((time.perf_counter() - started) * 1000)

        run = self._record_run(
            kind="flight",
            criteria=criteria,
            note=note,
            trip_id=trip_id,
            user_id=user_id,
            session_id=session_id,
            count=len(offers),
            latency_ms=latency,
        )
        rows = [self._persist_offer(offer, "flight", run.id, trip_id) for offer in offers]
        budgets = await self._budget_snapshots(trip_id, offers, kind="flight")

        ranked = ranking.rank_flights(offers, sort=sort, budgets=budgets)
        metrics.increment("search.flights", provider=note.provider)

        return FlightSearchResults(
            search_id=run.id,
            trip_id=trip_id,
            criteria=criteria,
            sort=sort,
            results=ranked,
            total=len(ranked),
            currency=criteria.currency,
            providers=[note],
            notes=_notes_for(note, offers, rows),
        )

    # ---- hotels ----------------------------------------------------------
    async def search_hotels(
        self,
        criteria: HotelSearchCriteria,
        *,
        trip_id: str | None = None,
        sort: SortMode = "cheapest",
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> HotelSearchResults:
        started = time.perf_counter()
        with span("search:hotels", kind="tool", trip_id=trip_id):
            outcome = await registry.call(
                registry.hotel_provider(),
                "search_hotels",
                lambda provider: provider.search_hotels(criteria),
                fallback=registry.fallback_hotel_provider(),
                kind="hotels",
            )

        offers: list[HotelOffer] = list(outcome.offers)
        note = outcome.note or ProviderNote(provider="unknown", ok=False)
        latency = int((time.perf_counter() - started) * 1000)

        run = self._record_run(
            kind="hotel",
            criteria=criteria,
            note=note,
            trip_id=trip_id,
            user_id=user_id,
            session_id=session_id,
            count=len(offers),
            latency_ms=latency,
        )
        rows = [self._persist_offer(offer, "hotel", run.id, trip_id) for offer in offers]
        budgets = await self._budget_snapshots(trip_id, offers, kind="hotel")

        ranked = ranking.rank_hotels(offers, sort=sort, budgets=budgets)
        metrics.increment("search.hotels", provider=note.provider)

        return HotelSearchResults(
            search_id=run.id,
            trip_id=trip_id,
            criteria=criteria,
            sort=sort,
            results=ranked,
            total=len(ranked),
            currency=criteria.currency,
            providers=[note],
            notes=_notes_for(note, offers, rows),
        )

    # ---- activities ------------------------------------------------------
    async def search_activities(
        self,
        criteria: ActivitySearchCriteria,
        *,
        trip_id: str | None = None,
        sort: SortMode = "cheapest",
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> ActivitySearchResults:
        started = time.perf_counter()
        with span("search:activities", kind="tool", trip_id=trip_id):
            outcome = await registry.call(
                registry.activity_provider(),
                "search_activities",
                lambda provider: provider.search_activities(criteria),
                fallback=registry.fallback_activity_provider(),
                kind="activities",
            )

        offers: list[ActivityOffer] = list(outcome.offers)
        note = outcome.note or ProviderNote(provider="unknown", ok=False)
        latency = int((time.perf_counter() - started) * 1000)

        run = self._record_run(
            kind="activity",
            criteria=criteria,
            note=note,
            trip_id=trip_id,
            user_id=user_id,
            session_id=session_id,
            count=len(offers),
            latency_ms=latency,
        )
        rows = [self._persist_offer(offer, "activity", run.id, trip_id) for offer in offers]
        budgets = await self._budget_snapshots(trip_id, offers, kind="activity")

        ranked = ranking.rank_activities(offers, sort=sort, budgets=budgets)
        metrics.increment("search.activities", provider=note.provider)

        return ActivitySearchResults(
            search_id=run.id,
            trip_id=trip_id,
            criteria=criteria,
            sort=sort,
            results=ranked,
            total=len(ranked),
            currency=criteria.currency,
            providers=[note],
            notes=_notes_for(note, offers, rows),
        )

    # ---- selection -------------------------------------------------------
    async def select(
        self,
        trip_id: str,
        *,
        offer_ref: str,
        selected_by: str | None = None,
    ) -> tuple[Any, Any]:
        """Choose an offer for a trip and charge the budget for it.

        One transaction does four things: supersede the previous selection of
        this kind, reverse the budget line it created, write the new selection,
        and write the new budget line. Splitting them would leave a window in
        which a trip has two flights or none.

        An offer priced in another currency is converted here, once, and the
        rate is stored on the budget line. The offer row keeps the provider's
        own figure untouched - that is what will actually be charged.
        """
        trip = self.session.get(Trip, trip_id)
        if trip is None:
            raise TripNotFound(f"trip {trip_id} does not exist")

        row = self.offers.by_ref(offer_ref, trip_id=trip_id) or self.offers.by_ref(offer_ref)
        if row is None:
            from app.providers.base import OfferNotFound

            raise OfferNotFound(f"offer {offer_ref} is not known to this journey")

        if row.expires_at is not None:
            from app.schemas.common import ensure_utc, utcnow

            if ensure_utc(row.expires_at) <= utcnow():
                # A stale quote must not silently become a commitment. The
                # traveller is sent back to a fresh search rather than charged
                # a price that no longer exists.
                raise OfferExpired(
                    "this offer has expired; search again to see current prices"
                )

        kind = row.kind
        replaces = _REPLACES[kind]

        # Supersede whatever this displaces, and reverse its money.
        superseded: list[str] = []
        if replaces:
            for previous in self.offers.active_selections(trip_id, kind=kind):
                if previous.budget_item_id:
                    try:
                        self.budgets.reverse_item(
                            trip_id,
                            previous.budget_item_id,
                            actor=selected_by or "user",
                            reason="replaced_by_new_selection",
                        )
                    except TravelCrewError:
                        # Already reversed by another path; the selection row
                        # still has to be superseded.
                        logger.info(
                            "budget line was already reversed",
                            extra={"trip_id": trip_id, "item": previous.budget_item_id},
                        )
                superseded.append(previous.id)

        travelers = _travelers_for(row)

        # A dollar flight on a taka-budgeted trip needs a rate, and the rate is
        # fetched here rather than inside the budget engine: the engine must
        # stay deterministic, and a total that changes depending on when it was
        # recomputed is not a total.
        budget_record = self.budgets.ensure(trip_id)
        rate = None
        if normalise_currency(row.currency) != budget_record.currency:
            rate = await CurrencyService(self.session).get_exchange_rate(
                row.currency, budget_record.currency
            )

        item, budget = self.budgets.add_item(
            trip_id,
            category=_CATEGORY[kind],
            amount=row.total_amount,
            state=ITEM_SELECTED,
            label=row.title,
            currency=row.currency,
            source=row.source,
            source_type=_SOURCE_TYPE[kind],
            source_id=row.offer_ref,
            created_by=selected_by or "user",
            rate=rate,
            detail={"offer_id": row.id, "provider": row.provider},
        )

        selection = self.offers.add_selection(
            trip_id=trip_id,
            offer_id=row.id,
            kind=kind,
            budget_item_id=item.id,
            travelers=travelers,
            total_amount=row.total_amount,
            currency=row.currency,
            selected_by=selected_by,
        )
        for previous_id in superseded:
            previous = self.offers.get_selection(previous_id, trip_id)
            if previous is not None:
                self.offers.supersede(previous, by_id=selection.id)

        metrics.increment("selection.created", kind=kind)
        return selection, budget

    def deselect(
        self, trip_id: str, selection_id: str, *, actor: str | None = None
    ) -> Any:
        selection = self.offers.get_selection(selection_id, trip_id)
        if selection is None or selection.status != "SELECTED":
            raise SelectionNotFound(f"selection {selection_id} is not active on this journey")

        if selection.budget_item_id:
            self.budgets.reverse_item(
                trip_id,
                selection.budget_item_id,
                actor=actor or "user",
                reason="deselected",
            )
        self.offers.supersede(selection, by_id=None)
        metrics.increment("selection.removed", kind=selection.kind)
        return self.budgets.snapshot(trip_id)

    def selections(self, trip_id: str) -> list[Any]:
        return self.offers.active_selections(trip_id)

    # ---- internals -------------------------------------------------------
    def _record_run(
        self,
        *,
        kind: str,
        criteria: Any,
        note: ProviderNote,
        trip_id: str | None,
        user_id: str | None,
        session_id: str | None,
        count: int,
        latency_ms: int,
    ) -> Any:
        return self.offers.record_search(
            trip_id=trip_id,
            user_id=user_id,
            session_id=session_id,
            kind=kind,
            provider=note.provider,
            source=note.source,
            cache_key=criteria.cache_key()[:400],
            criteria=criteria.model_dump(mode="json"),
            result_count=count,
            latency_ms=latency_ms,
            ok=note.ok,
            notes=[note.model_dump(mode="json")],
        )

    def _persist_offer(
        self, offer: Any, kind: OfferKind, search_id: str, trip_id: str | None
    ) -> Offer:
        """Snapshot one offer exactly as it was shown."""
        return self.offers.add_offer(
            offer_ref=offer.offer_id,
            search_id=search_id,
            trip_id=trip_id,
            kind=kind,
            provider=offer.meta.provider,
            source=offer.meta.source,
            total_amount=_total_of(offer, kind),
            currency=offer.currency,
            title=_title_of(offer, kind),
            payload=offer.model_dump(mode="json"),
            retrieved_at=offer.meta.retrieved_at,
            expires_at=offer.meta.expires_at,
        )

    async def _budget_snapshots(
        self, trip_id: str | None, offers: list[Any], *, kind: OfferKind
    ) -> dict[str, BudgetSnapshotForOffer]:
        """What each offer would do to the budget, from the budget engine.

        Without a trip there is no budget, and the cards render without the
        budget lines rather than with invented ones.
        """
        if not trip_id or not offers:
            return {}

        replaces = _REPLACES[kind]
        record = self.budgets.ensure(trip_id)

        # One rate per currency for the whole result set, so every card on the
        # page is priced against the same moment.
        rates: dict[str, Any] = {}
        service = CurrencyService(self.session)
        for offer in offers:
            code = normalise_currency(offer.currency)
            if code != record.currency and code not in rates:
                rates[code] = await service.get_exchange_rate(code, record.currency)

        snapshots: dict[str, BudgetSnapshotForOffer] = {}
        for offer in offers:
            impact = self.budgets.impact_of(
                trip_id,
                amount=_total_of(offer, kind),
                currency=offer.currency,
                travelers=getattr(offer, "travelers", None)
                or getattr(offer, "participants", 1),
                label=_title_of(offer, kind),
                source=offer.meta.source,
                replaces_source_type=replaces,
                rate=rates.get(normalise_currency(offer.currency)),
            )
            snapshots[offer.offer_id] = BudgetSnapshotForOffer(
                total_budget=impact.total_budget,
                percentage_of_budget=impact.percentage_of_budget,
                remaining_after=impact.remaining_after,
                within_budget=impact.within_budget,
                currency=impact.currency,
            )
        return snapshots


# ---- module helpers -----------------------------------------------------
def _total_of(offer: Any, kind: str) -> Any:
    if kind == "hotel":
        return offer.total_stay
    return offer.total_price


def _title_of(offer: Any, kind: str) -> str:
    if kind == "flight":
        airlines = ", ".join(offer.airlines) or "Flight"
        route = ""
        outbound = offer.outbound
        if outbound and outbound.origin_iata and outbound.destination_iata:
            route = f" {outbound.origin_iata}-{outbound.destination_iata}"
        return f"{airlines}{route}"[:200]
    return str(getattr(offer, "name", "Offer"))[:200]


def _travelers_for(row: Offer) -> int:
    payload = row.payload or {}
    return int(payload.get("travelers") or payload.get("participants") or 1)


def _notes_for(note: ProviderNote, offers: list[Any], rows: list[Offer]) -> list[str]:
    notes: list[str] = []
    if note.message:
        notes.append(note.message)
    if offers and offers[0].meta.source == SOURCE_MOCK:
        notes.append(
            "These prices come from the offline reference provider and are labelled "
            "MOCK. They are not bookable and cannot be committed to a budget."
        )
    if not offers:
        notes.append("No option matched these criteria.")
    assert to_decimal  # the money helpers are the only arithmetic path here
    return notes


__all__ = ["SearchService", "SelectionNotFound"]
