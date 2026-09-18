"""The offline flight provider.

Travel Crew AI has always run end to end with no credentials, and that does not
stop being true now that there is a booking flow. This adapter implements the
full ``FlightProvider`` contract - search, re-price, book, cancel - against
deterministic data derived from the project's own airport reference table and
route fare bands.

Three things it is careful about:

  * **Everything it returns is labelled ``MOCK``.** The budget engine refuses
    to mark a MOCK amount as committed, so a mock price physically cannot
    become a booked obligation. The label is load-bearing, not cosmetic.
  * **It is deterministic.** The same search yields the same offers in every
    process, so ranking, budget impact and the interface are all testable.
  * **Its cheapest base fare is often not its cheapest total.** Real fares
    behave this way - a headline price without a bag beats one with a bag until
    you need the bag - and a mock that hid that would let a "cheapest first"
    bug pass every test.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.core.constants import SOURCE_MOCK
from app.mcp.aviation import _BAND_FARE, AIRPORTS, _band_for, lookup_airport
from app.providers.base import OfferNotFound, PriceCheck
from app.providers.seeding import generator, jitter
from app.schemas.offers import (
    DEFAULT_OFFER_TTL,
    BaggageAllowance,
    FareConditions,
    FlightOffer,
    FlightSegment,
    FlightSlice,
    Layover,
    OfferMeta,
    PriceBreakdown,
)
from app.schemas.search import FlightSearchCriteria
from app.services.money import quantize, to_decimal

PROVIDER_NAME = "mock_flights"

# Carriers with a plausible hub each, so a one-stop itinerary connects
# somewhere a traveller would recognise rather than at a random airport.
_CARRIERS: tuple[tuple[str, str, str], ...] = (
    ("Turkish Airlines", "TK", "IST"),
    ("Emirates", "EK", "DXB"),
    ("Qatar Airways", "QR", "DOH"),
    ("Singapore Airlines", "SQ", "SIN"),
    ("Etihad Airways", "EY", "AUH"),
    ("Biman Bangladesh Airlines", "BG", "DAC"),
    ("IndiGo", "6E", "DEL"),
    ("Malaysia Airlines", "MH", "KUL"),
)

# Cabin multipliers over the economy band fare.
_CABIN_MULTIPLIER = {
    "economy": Decimal("1.00"),
    "premium_economy": Decimal("1.65"),
    "business": Decimal("3.10"),
    "first": Decimal("5.40"),
}

# What a checked bag costs when the fare does not include one.
_CHECKED_BAG_FEE = {
    "economy": Decimal("45.00"),
    "premium_economy": Decimal("30.00"),
    "business": Decimal("0.00"),
    "first": Decimal("0.00"),
}

# A child pays this share of the adult fare; infants are not modelled here.
_CHILD_FARE_RATIO = Decimal("0.75")

_TAX_RATE = Decimal("0.14")
_CARRIER_FEE = Decimal("9.00")

_AIRPORT_BY_IATA = {record["iata"]: record for record in AIRPORTS.values()}


class MockFlightProvider:
    """A complete, offline ``FlightProvider``."""

    name = PROVIDER_NAME

    def __init__(self) -> None:
        # Offers are kept for the lifetime of the process so that get_offer,
        # revalidate_price and create_booking can act on the exact itinerary a
        # traveller chose, rather than re-deriving something similar.
        self._offers: dict[str, FlightOffer] = {}
        self._bookings: dict[str, dict[str, Any]] = {}
        self._idempotency: dict[str, str] = {}

    # ---- search ----------------------------------------------------------
    async def search_flights(self, criteria: FlightSearchCriteria) -> list[FlightOffer]:
        origin = _resolve(criteria.origin)
        destination = _resolve(criteria.destination)
        band = _band_for(origin["iata"], destination["iata"])
        base = to_decimal(_BAND_FARE[band])

        rng = generator(PROVIDER_NAME, criteria.cache_key())
        carriers = _eligible_carriers(criteria, rng)
        if not carriers:
            # Every airline the traveller would accept has been excluded. That
            # is an empty result, not a provider failure.
            return []

        offers: list[FlightOffer] = []
        # A spread of shapes: non-stop, one-stop, and a cheap long connection.
        shapes = _shapes_for(criteria)

        for index, (stops, price_factor, speed_factor) in enumerate(shapes):
            carrier = carriers[index % len(carriers)]
            offer = self._build_offer(
                criteria=criteria,
                origin=origin,
                destination=destination,
                carrier=carrier,
                stops=stops,
                base_fare=base,
                price_factor=price_factor,
                speed_factor=speed_factor,
                rng=rng,
                index=index,
            )
            if _matches(offer, criteria):
                offers.append(offer)
                self._offers[offer.offer_id] = offer

        return offers

    # ---- single offer ----------------------------------------------------
    async def get_offer(self, offer_id: str) -> FlightOffer:
        offer = self._offers.get(offer_id)
        if offer is None:
            raise OfferNotFound(f"offer {offer_id} is not held by {self.name}")
        return offer

    async def revalidate_price(self, offer_id: str) -> PriceCheck:
        """Re-price an offer, the way a real provider would.

        The offline provider mostly confirms the price, and deterministically
        moves it for a minority of offers. That minority is the point: the
        price-change branch of the booking flow needs to be reachable without
        credentials, or it only ever gets exercised in production.
        """
        offer = await self.get_offer(offer_id)
        rng = generator(PROVIDER_NAME, "revalidate", offer_id)
        roll = rng.random()

        old_total = to_decimal(offer.total_price)
        if roll < 0.15:
            new_total = quantize(old_total * to_decimal("1.06"), Decimal("0.01"))
            note = "the fare has increased since this offer was retrieved"
        elif roll < 0.20:
            return PriceCheck(
                offer_id=offer_id,
                still_available=False,
                old_total=old_total,
                new_total=old_total,
                currency=offer.currency,
                checked_at=datetime.now(timezone.utc),
                note="this fare is no longer available",
            )
        else:
            new_total = old_total
            note = None

        return PriceCheck(
            offer_id=offer_id,
            still_available=True,
            old_total=old_total,
            new_total=new_total,
            currency=offer.currency,
            checked_at=datetime.now(timezone.utc),
            note=note,
        )

    # ---- booking ---------------------------------------------------------
    async def create_booking(
        self, offer_id: str, *, travelers: list[dict[str, Any]], idempotency_key: str
    ) -> dict[str, Any]:
        """Create a booking, or return the one this key already created.

        The idempotency map is what makes a retried request safe. A real
        provider offers the same guarantee; modelling it here means the
        double-booking tests exercise the same path in both.
        """
        if idempotency_key in self._idempotency:
            return self._bookings[self._idempotency[idempotency_key]]

        offer = await self.get_offer(offer_id)
        rng = generator(PROVIDER_NAME, "booking", idempotency_key)
        reference = "".join(rng.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=6))

        booking = {
            "booking_reference": reference,
            "provider": self.name,
            "offer_id": offer_id,
            "status": "CONFIRMED",
            "total_amount": str(offer.total_price),
            "currency": offer.currency,
            "traveler_count": len(travelers),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": SOURCE_MOCK,
        }
        self._bookings[reference] = booking
        self._idempotency[idempotency_key] = reference
        return booking

    async def get_booking(self, booking_reference: str) -> dict[str, Any]:
        booking = self._bookings.get(booking_reference)
        if booking is None:
            raise OfferNotFound(f"booking {booking_reference} is not held by {self.name}")
        return booking

    async def cancel_booking(self, booking_reference: str) -> dict[str, Any]:
        booking = await self.get_booking(booking_reference)
        booking["status"] = "CANCELLED"
        booking["cancelled_at"] = datetime.now(timezone.utc).isoformat()
        return booking

    # ---- construction ----------------------------------------------------
    def _build_offer(
        self,
        *,
        criteria: FlightSearchCriteria,
        origin: dict[str, Any],
        destination: dict[str, Any],
        carrier: tuple[str, str, str],
        stops: int,
        base_fare: Decimal,
        price_factor: Decimal,
        speed_factor: Decimal,
        rng: Any,
        index: int,
    ) -> FlightOffer:
        name, code, hub = carrier
        cabin_multiplier = _CABIN_MULTIPLIER[criteria.cabin_class]

        adult_fare = quantize(
            jitter(rng, base_fare * price_factor * cabin_multiplier, 0.06),
            Decimal("0.01"),
        )
        taxes = quantize(adult_fare * _TAX_RATE, Decimal("0.01"))

        # Whether a checked bag is in the fare varies by offer. When the search
        # asked for one and the fare lacks it, the fee joins the total - which
        # is exactly how a cheap-looking fare stops being the cheapest.
        checked_included = bool(rng.random() < 0.5) or criteria.cabin_class in (
            "business",
            "first",
        )
        baggage_fee = Decimal(0)
        if criteria.baggage == "checked" and not checked_included:
            baggage_fee = _CHECKED_BAG_FEE[criteria.cabin_class]

        price = PriceBreakdown(
            base_fare=adult_fare,
            taxes=taxes,
            fees=_CARRIER_FEE,
            baggage_fee=baggage_fee,
            currency=criteria.currency,
        )

        # Children are cheaper, so the group total is not per-head x heads.
        adult_total = price.total * criteria.adults
        child_total = quantize(price.total * _CHILD_FARE_RATIO, Decimal("0.01")) * criteria.children
        total = adult_total + child_total

        outbound = _build_slice(
            origin=origin,
            destination=destination,
            carrier=carrier,
            stops=stops,
            travel_date=criteria.departure_date,
            cabin=criteria.cabin_class,
            speed_factor=speed_factor,
            rng=rng,
            leg=0,
        )
        slices = [outbound]
        if criteria.return_date:
            slices.append(
                _build_slice(
                    origin=destination,
                    destination=origin,
                    carrier=carrier,
                    stops=stops,
                    travel_date=criteria.return_date,
                    cabin=criteria.cabin_class,
                    speed_factor=speed_factor,
                    rng=rng,
                    leg=1,
                )
            )

        refundable = bool(rng.random() < 0.3) or criteria.cabin_class in ("business", "first")
        retrieved = datetime.now(timezone.utc)

        return FlightOffer(
            offer_id=f"{PROVIDER_NAME}:{uuid.uuid5(uuid.NAMESPACE_URL, criteria.cache_key() + str(index))}",
            meta=OfferMeta(
                provider=self.name,
                source=SOURCE_MOCK,
                retrieved_at=retrieved,
                expires_at=retrieved + DEFAULT_OFFER_TTL,
                provider_offer_id=f"{code}-{index}",
                booking_url=None,
            ),
            slices=slices,
            cabin=criteria.cabin_class,
            baggage=BaggageAllowance(
                cabin_bags=1,
                checked_bags=1 if (checked_included or baggage_fee > 0) else 0,
                checked_weight_kg=23 if (checked_included or baggage_fee > 0) else None,
                checked_included=checked_included,
                note=(
                    "Checked bag included"
                    if checked_included
                    else ("Checked bag added at " + str(baggage_fee) if baggage_fee else "Cabin bag only")
                ),
            ),
            conditions=FareConditions(
                refundable=refundable,
                changeable=True,
                change_fee=Decimal(0) if refundable else Decimal("75.00"),
                note=None if refundable else "Non-refundable fare",
            ),
            price_per_traveler=price,
            travelers=criteria.travelers,
            total_price=total,
            currency=criteria.currency,
            seats_remaining=rng.randint(2, 9),
        )


# ---- helpers ------------------------------------------------------------
def _resolve(city: str) -> dict[str, Any]:
    record = lookup_airport(city)
    if not record.get("iata"):
        # Unknown city: derive a stable pseudo-code rather than failing, so an
        # offline demo works for any destination a traveller types.
        rng = generator("airport", city.strip().lower())
        record = {
            "city": city.strip(),
            "iata": "".join(rng.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=3)),
            "name": f"{city.strip()} International",
            "country": None,
        }
    return record


def _eligible_carriers(
    criteria: FlightSearchCriteria, rng: Any
) -> list[tuple[str, str, str]]:
    excluded = set(criteria.excluded_airlines)
    preferred = set(criteria.preferred_airlines)

    pool = [carrier for carrier in _CARRIERS if carrier[1] not in excluded]
    if preferred:
        narrowed = [carrier for carrier in pool if carrier[1] in preferred]
        # A preference that matches nothing is a preference, not a filter: the
        # traveller still gets results, and the interface can say so.
        if narrowed:
            pool = narrowed

    ordered = list(pool)
    rng.shuffle(ordered)
    return ordered


def _shapes_for(criteria: FlightSearchCriteria) -> list[tuple[int, Decimal, Decimal]]:
    """Offer shapes: (stops, price factor, speed factor).

    A non-stop costs more and is faster; connections are cheaper and slower.
    That tension is what makes "cheapest" and "fastest" different sorts, and
    what makes "best value" a question worth asking.
    """
    shapes: list[tuple[int, Decimal, Decimal]] = [
        (0, Decimal("1.24"), Decimal("1.00")),
        (0, Decimal("1.16"), Decimal("1.05")),
        (1, Decimal("0.95"), Decimal("1.45")),
        (1, Decimal("0.88"), Decimal("1.60")),
        (1, Decimal("0.83"), Decimal("1.85")),
        (2, Decimal("0.74"), Decimal("2.30")),
    ]
    if criteria.max_stops is not None:
        shapes = [shape for shape in shapes if shape[0] <= criteria.max_stops]
    return shapes


def _build_slice(
    *,
    origin: dict[str, Any],
    destination: dict[str, Any],
    carrier: tuple[str, str, str],
    stops: int,
    travel_date: date,
    cabin: str,
    speed_factor: Decimal,
    rng: Any,
    leg: int,
) -> FlightSlice:
    name, code, hub = carrier
    base_minutes = int(180 + rng.randint(0, 240))
    total_minutes = int(base_minutes * float(speed_factor)) + stops * rng.randint(70, 260)

    depart_hour = rng.randint(5, 22)
    depart = datetime.combine(
        travel_date, time(hour=depart_hour, minute=rng.choice((0, 5, 10, 20, 35, 45, 55)))
    ).replace(tzinfo=timezone.utc)

    segments: list[FlightSegment] = []
    layovers: list[Layover] = []

    waypoints = [origin]
    for stop_index in range(stops):
        hub_record = _AIRPORT_BY_IATA.get(hub)
        if stops > 1 and stop_index > 0:
            # A second connection goes somewhere other than the carrier's hub.
            hub_record = None
        waypoints.append(
            hub_record
            or {
                "iata": hub if stop_index == 0 else "XXX",
                "name": f"{hub} Hub" if stop_index == 0 else "Connecting airport",
            }
        )
    waypoints.append(destination)

    leg_count = len(waypoints) - 1
    flying_minutes = max(total_minutes - stops * 90, 60)
    per_leg = max(flying_minutes // leg_count, 45)

    cursor = depart
    for leg_index in range(leg_count):
        start = waypoints[leg_index]
        end = waypoints[leg_index + 1]
        arrival = cursor + timedelta(minutes=per_leg)
        segments.append(
            FlightSegment(
                marketing_airline=name,
                marketing_airline_code=code,
                operating_airline=name,
                flight_number=f"{code}{rng.randint(100, 989)}",
                departure_iata=start.get("iata"),
                departure_airport=start.get("name"),
                departure_time=cursor,
                arrival_iata=end.get("iata"),
                arrival_airport=end.get("name"),
                arrival_time=arrival,
                duration_minutes=per_leg,
                cabin=cabin,  # type: ignore[arg-type]
            )
        )
        if leg_index < leg_count - 1:
            wait = rng.randint(55, 320)
            layovers.append(
                Layover(
                    airport_iata=end.get("iata"),
                    airport_name=end.get("name"),
                    duration_minutes=wait,
                    overnight=wait > 240,
                    changes_airport=False,
                )
            )
            cursor = arrival + timedelta(minutes=wait)
        else:
            cursor = arrival

    duration = int((cursor - depart).total_seconds() // 60)
    return FlightSlice(segments=segments, layovers=layovers, duration_minutes=duration)


def _matches(offer: FlightOffer, criteria: FlightSearchCriteria) -> bool:
    """Apply the constraints a provider would apply server-side.

    Filtering here rather than after ranking matters: an excluded airline that
    reached the ranker could still be badged CHEAPEST and shown.
    """
    if criteria.max_stops is not None and offer.stops > criteria.max_stops:
        return False
    if set(offer.airline_codes) & set(criteria.excluded_airlines):
        return False

    outbound = offer.outbound
    if outbound and outbound.departure_time:
        hour = outbound.departure_time.hour
        if criteria.earliest_departure_hour is not None and hour < criteria.earliest_departure_hour:
            return False
        if criteria.latest_departure_hour is not None and hour > criteria.latest_departure_hour:
            return False
    if outbound and outbound.arrival_time:
        hour = outbound.arrival_time.hour
        if criteria.earliest_arrival_hour is not None and hour < criteria.earliest_arrival_hour:
            return False
        if criteria.latest_arrival_hour is not None and hour > criteria.latest_arrival_hour:
            return False

    if criteria.max_total_price is not None:
        if to_decimal(offer.total_price) > to_decimal(criteria.max_total_price):
            return False
    return True
