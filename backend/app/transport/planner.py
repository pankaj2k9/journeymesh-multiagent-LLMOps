"""Door-to-door route planning across modes.

Given two places it builds every option that makes sense - a flight, a train,
a bus, a hired car, a CNG or an auto-rickshaw for short hops, a ferry to an
island - including combinations: fly to the nearest airport and take a bus the
rest of the way, or ride to the jetty and take the boat.

"auto" picks the option with the lowest *generalised* cost: the fare for the
whole party plus the party's time, valued at a regional rate. That is what
makes a flight win over 20 hours on a bus, and a bus win over a flight for
three hours of road. A traveller who picks a mode gets that mode costed, or an
explanation of why it cannot work and the automatic choice instead.

Every number is an estimate from distance and typical regional fares, and is
labelled as one. There is no ground-transport booking provider behind this.
"""

from __future__ import annotations

import math
import string
from dataclasses import dataclass

from app.core.constants import SOURCE_ESTIMATE
from app.mcp.aviation import AIRPORTS
from app.schemas.transport import RoutePlan, TransportLeg, TransportOption
from app.transport.geo import (
    COORDINATES,
    FERRY_ACCESS,
    FLY_ONLY,
    GATEWAYS,
    HILL_EXTRA_FACTOR,
    HILL_STRETCH_KM,
    HILLY,
    ISLANDS,
    ROAD_FACTOR,
    normalise,
    straight_km,
)

# ---- regional economics ----------------------------------------------------------


@dataclass(frozen=True)
class Tier:
    """Typical fares (USD) and door-to-door speeds (km/h) for a region."""

    bus_km: float
    bus_min: float
    train_km: float
    train_min: float
    car_km: float  # per vehicle, driver and fuel included
    car_min: float
    local_km: float  # CNG / auto-rickshaw / tuk-tuk / taxi, per vehicle
    local_min: float
    ferry: float  # per person, one crossing
    flight_base: float
    flight_km: float
    speed: dict[str, float]
    # What an hour of a traveller's time is worth when comparing options.
    value_of_hour: float


TIERS: dict[str, Tier] = {
    "low": Tier(
        bus_km=0.03, bus_min=1.0, train_km=0.02, train_min=1.0,
        car_km=0.25, car_min=8.0, local_km=0.12, local_min=1.0,
        ferry=10.0, flight_base=35.0, flight_km=0.05,
        speed={"bus": 38, "train": 50, "car": 45, "local": 22, "ferry": 18},
        value_of_hour=3.0,
    ),
    "mid": Tier(
        bus_km=0.05, bus_min=3.0, train_km=0.06, train_min=3.0,
        car_km=0.35, car_min=15.0, local_km=0.5, local_min=3.0,
        ferry=15.0, flight_base=55.0, flight_km=0.07,
        speed={"bus": 55, "train": 80, "car": 60, "local": 30, "ferry": 22},
        value_of_hour=6.0,
    ),
    "high": Tier(
        bus_km=0.10, bus_min=8.0, train_km=0.20, train_min=10.0,
        car_km=0.60, car_min=40.0, local_km=2.0, local_min=10.0,
        ferry=30.0, flight_base=90.0, flight_km=0.10,
        speed={"bus": 70, "train": 130, "car": 80, "local": 35, "ferry": 28},
        value_of_hour=20.0,
    ),
}

_LOW = {"Bangladesh", "India", "Nepal", "Sri Lanka", "Pakistan"}
_MID = {
    "Thailand", "Vietnam", "Malaysia", "Indonesia", "Philippines", "China", "Turkiye",
    "Egypt", "Kenya", "South Africa", "Maldives", "Cambodia", "Laos", "Mongolia", "Bhutan",
}  # Bahrain and the rest fall to "high"


def tier_for(country: str | None) -> Tier:
    if country in _LOW:
        return TIERS["low"]
    if country in _MID:
        return TIERS["mid"]
    return TIERS["high"]


# Countries with an intercity passenger railway worth planning on.
RAIL_COUNTRIES = frozenset({
    "India", "Bangladesh", "Sri Lanka", "Thailand", "Vietnam", "Malaysia", "Indonesia",
    "Singapore", "China", "Hong Kong", "Japan", "South Korea", "Turkiye", "Egypt",
    "United Kingdom", "France", "Italy", "Spain", "Netherlands", "Germany", "Switzerland",
    "United States", "Canada", "Australia", "South Africa", "Portugal", "Taiwan", "Laos",
})

# Places in those countries the railway does not reach.
NO_RAIL = frozenset({
    "leh", "port blair", "bandarban", "rangamati", "sajek valley", "kuakata",
    "saint martin's island", "st. martin's island", "teknaf", "bali", "phuket", "barisal",
    "manali", "gangtok", "darjeeling", "munnar", "ooty", "shillong", "sigiriya", "krabi",
    "pattaya", "langkawi", "malacca", "ha long", "hoi an", "lombok", "labuan bajo",
    "cappadocia", "antalya", "hurghada", "sharm el sheikh", "nagarkot", "lukla", "chitwan",
    "lumbini", "amalfi", "cinque terre", "siem reap", "paro", "thimphu",
})

# Countries one can cross between by road or rail.
LAND_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"India", "Bangladesh", "Nepal", "Bhutan"}),
    # Mainland South-East and East Asia; distance limits keep this sensible.
    frozenset({
        "Malaysia", "Singapore", "Thailand", "Cambodia", "Laos", "Vietnam", "China",
        "Hong Kong", "Macau", "Mongolia",
    }),
    frozenset({
        "United Kingdom", "France", "Netherlands", "Germany", "Switzerland", "Italy", "Spain",
        "Portugal",
    }),
    frozenset({"United States", "Canada"}),
    frozenset({"United Arab Emirates", "Qatar"}),
)

# The short-hop vehicle people actually take, by country.
LOCAL_MODE = {
    "Bangladesh": "cng",
    "India": "auto_rickshaw",
    "Sri Lanka": "tuk_tuk",
    "Thailand": "tuk_tuk",
}

CAPACITY = {"car": 4, "cng": 3, "auto_rickshaw": 3, "tuk_tuk": 3, "rickshaw": 2, "taxi": 4}

MODE_NAMES = {
    "flight": "flight",
    "train": "train",
    "bus": "bus",
    "car": "private car",
    "cng": "CNG auto-rickshaw",
    "auto_rickshaw": "auto-rickshaw",
    "tuk_tuk": "tuk-tuk",
    "rickshaw": "rickshaw",
    "taxi": "taxi",
    "ferry": "ferry",
}

MAX_GROUND_KM = {"car": 900.0, "bus": 1500.0, "train": 2500.0}
MIN_GROUND_KM = 30.0
MIN_FLIGHT_KM = 150.0
LOCAL_MAX_KM = 40.0
FLIGHT_SPEED = 780.0
FLIGHT_OVERHEAD_HOURS = 3.0  # getting to the airport, security, boarding
BOARDING_HOURS = {"bus": 0.5, "train": 0.75, "ferry": 0.5}


# ---- places ------------------------------------------------------------------------


@dataclass(frozen=True)
class Place:
    key: str
    name: str
    country: str | None
    coords: tuple[float, float]

    @property
    def has_airport(self) -> bool:
        return self.key in AIRPORTS and self.key not in GATEWAYS

    @property
    def has_rail(self) -> bool:
        return self.country in RAIL_COUNTRIES and self.key not in NO_RAIL


def _country(key: str) -> str | None:
    record = AIRPORTS.get(key)
    return record["country"] if record else None


def _place(key: str, name: str | None = None) -> Place | None:
    coords = COORDINATES.get(key)
    if coords is None:
        return None
    country = _country(key) or _country(GATEWAYS.get(key, ""))
    if country is None and key == "teknaf":
        country = "Bangladesh"
    display = "Malé" if key in {"male", "malé"} else string.capwords(key)
    return Place(key=key, name=name or display, country=country, coords=coords)


def resolve(city: str | None) -> Place | None:
    """A named city, matched exactly and then leniently, like the airport lookup."""
    key = normalise(city or "")
    if not key:
        return None
    if key in COORDINATES:
        return _place(key, city.strip() if city else None)
    for candidate in COORDINATES:
        if key in candidate or candidate in key:
            return _place(candidate, city.strip() if city else None)
    return None


def _km(a: Place, b: Place) -> float:
    """Ground distance: the straight line stretched for roads, more in the hills."""
    straight = straight_km(a.coords, b.coords)
    km = straight * ROAD_FACTOR
    if a.key in HILLY or b.key in HILLY:
        km += min(straight, HILL_STRETCH_KM) * HILL_EXTRA_FACTOR
    return km


def _ground_connected(a: Place, b: Place) -> bool:
    if a.key in FLY_ONLY or b.key in FLY_ONLY:
        return False
    if a.key in ISLANDS or b.key in ISLANDS:
        return ISLANDS.get(a.key) == ISLANDS.get(b.key)
    if a.country == b.country:
        return True
    return any(a.country in group and b.country in group for group in LAND_GROUPS)


# ---- legs --------------------------------------------------------------------------


def _seat_leg(mode: str, a: Place, b: Place, km: float, tier: Tier, travelers: int) -> TransportLeg:
    if mode == "ferry":
        per_person = tier.ferry
    elif mode == "train":
        per_person = max(tier.train_min, tier.train_km * km)
    else:
        per_person = max(tier.bus_min, tier.bus_km * km)
    speed = tier.speed["ferry" if mode == "ferry" else mode]
    return TransportLeg(
        mode=mode,  # type: ignore[arg-type]
        from_place=a.name,
        to_place=b.name,
        distance_km=round(km),
        duration_hours=round(km / speed + BOARDING_HOURS.get(mode, 0), 1),
        cost_per_traveler=round(per_person, 2),
        cost_for_group=round(per_person * travelers, 2),
    )


def _vehicle_leg(
    mode: str, a: Place, b: Place, km: float, tier: Tier, travelers: int
) -> TransportLeg:
    vehicles = math.ceil(travelers / CAPACITY[mode])
    if mode == "car":
        per_vehicle = max(tier.car_min, tier.car_km * km)
        speed = tier.speed["car"]
    else:
        per_vehicle = max(tier.local_min, tier.local_km * km)
        speed = tier.speed["local"]
    group = per_vehicle * vehicles
    return TransportLeg(
        mode=mode,  # type: ignore[arg-type]
        from_place=a.name,
        to_place=b.name,
        distance_km=round(km),
        duration_hours=round(km / speed, 1),
        cost_per_traveler=round(group / travelers, 2),
        cost_for_group=round(group, 2),
        vehicles=vehicles,
        note=f"{vehicles} vehicle(s) for {travelers} traveller(s)" if vehicles > 1 else None,
    )


def _flight_leg(
    a: Place, b: Place, tier: Tier, travelers: int, live_price: float | None
) -> TransportLeg:
    km = straight_km(a.coords, b.coords)
    per_person = live_price if live_price else tier.flight_base + tier.flight_km * km
    return TransportLeg(
        mode="flight",
        from_place=a.name,
        to_place=b.name,
        distance_km=round(km),
        duration_hours=round(km / FLIGHT_SPEED + FLIGHT_OVERHEAD_HOURS, 1),
        cost_per_traveler=round(per_person, 2),
        cost_for_group=round(per_person * travelers, 2),
        note=None if live_price else "Fare estimated from distance.",
    )


def _local_mode(country: str | None) -> str:
    return LOCAL_MODE.get(country or "", "taxi")


def _connector(a: Place, b: Place, tier: Tier, travelers: int) -> TransportLeg:
    """The short ground link between an airport or station and the destination."""
    km = _km(a, b)
    if km <= LOCAL_MAX_KM:
        return _vehicle_leg(_local_mode(b.country), a, b, km, tier, travelers)
    bus = _seat_leg("bus", a, b, km, tier, travelers)
    car = _vehicle_leg("car", a, b, km, tier, travelers)
    return min((bus, car), key=lambda leg: _generalised([leg], tier, travelers))


def _generalised(legs: list[TransportLeg], tier: Tier, travelers: int) -> float:
    fare = sum(leg.cost_for_group for leg in legs)
    hours = sum(leg.duration_hours for leg in legs)
    return fare + tier.value_of_hour * hours * travelers


# ---- options -----------------------------------------------------------------------


def _label(legs: list[TransportLeg]) -> str:
    first, rest = legs[0], legs[1:]
    text = f"{MODE_NAMES[first.mode].capitalize()} to {first.to_place}"
    for leg in rest:
        text += f", then {MODE_NAMES[leg.mode]} to {leg.to_place}"
    return text


def _option(main: str, legs: list[TransportLeg], round_trip: bool) -> TransportOption:
    group = round(sum(leg.cost_for_group for leg in legs), 2)
    per = round(sum(leg.cost_per_traveler for leg in legs), 2)
    return TransportOption(
        main_mode=main,  # type: ignore[arg-type]
        label=_label(legs),
        legs=legs,
        distance_km=round(sum(leg.distance_km for leg in legs)),
        duration_hours=round(sum(leg.duration_hours for leg in legs), 1),
        one_way_per_traveler=per,
        one_way_for_group=group,
        trip_total_for_group=round(group * (2 if round_trip else 1), 2),
    )


def _destination_tail(
    arrive: Place, destination: Place, tier: Tier, travelers: int
) -> list[TransportLeg] | None:
    """Legs from where the main mode stops to the destination itself."""
    legs: list[TransportLeg] = []
    target = destination
    ferry = FERRY_ACCESS.get(destination.key)
    if ferry:
        jetty = _place(ferry[0])
        if jetty is None:
            return None
        target = jetty
    if arrive.key != target.key:
        legs.append(_connector(arrive, target, tier, travelers))
    if ferry:
        crossing = straight_km(target.coords, destination.coords)
        legs.append(_seat_leg("ferry", target, destination, crossing, tier, travelers))
    return legs


def _flight_option(
    origin: Place, destination: Place, travelers: int, round_trip: bool, live_price: float | None
) -> TransportOption | None:
    depart = origin if origin.has_airport else _place(GATEWAYS.get(origin.key, ""))
    arrive = destination if destination.has_airport else _place(GATEWAYS.get(destination.key, ""))
    if depart is None or arrive is None:
        return None
    if AIRPORTS[depart.key]["iata"] == AIRPORTS[arrive.key]["iata"]:
        return None
    # A short hop is not worth flying - unless the air is the only way in.
    fly_only = origin.key in FLY_ONLY or destination.key in FLY_ONLY
    if straight_km(depart.coords, arrive.coords) < MIN_FLIGHT_KM and not fly_only:
        return None

    tier = tier_for(origin.country)
    legs: list[TransportLeg] = []
    if depart.key != origin.key:
        legs.append(_connector(origin, depart, tier, travelers))
    legs.append(_flight_leg(depart, arrive, tier, travelers, live_price))
    tail = _destination_tail(arrive, destination, tier_for(destination.country), travelers)
    if tail is None:
        return None
    return _option("flight", legs + tail, round_trip)


def _ground_option(
    mode: str, origin: Place, destination: Place, travelers: int, round_trip: bool
) -> TransportOption | None:
    if not _ground_connected(origin, destination):
        return None
    tier = tier_for(origin.country)
    ferry = FERRY_ACCESS.get(destination.key)
    road_end = _place(ferry[0]) if ferry else destination
    if road_end is None:
        return None

    main_end = road_end
    if mode == "train":
        if not origin.has_rail:
            return None
        if not road_end.has_rail:
            # Ride the train as far as it goes: the destination's gateway city.
            gateway = _place(GATEWAYS.get(destination.key, ""))
            if gateway is None or not gateway.has_rail:
                return None
            main_end = gateway

    km = _km(origin, main_end)
    if km < MIN_GROUND_KM or km > MAX_GROUND_KM[mode]:
        return None

    if mode == "car":
        main_leg = _vehicle_leg("car", origin, main_end, km, tier, travelers)
    else:
        main_leg = _seat_leg(mode, origin, main_end, km, tier, travelers)
    tail = _destination_tail(main_end, destination, tier, travelers)
    if tail is None:
        return None
    return _option(mode, [main_leg, *tail], round_trip)


def _local_option(
    origin: Place, destination: Place, travelers: int, round_trip: bool
) -> TransportOption | None:
    if origin.country != destination.country or destination.key in FERRY_ACCESS:
        return None
    km = _km(origin, destination)
    if km > LOCAL_MAX_KM:
        return None
    mode = _local_mode(destination.country)
    leg = _vehicle_leg(mode, origin, destination, km, tier_for(origin.country), travelers)
    return _option(mode, [leg], round_trip)


# ---- the plan ----------------------------------------------------------------------

ESTIMATE_NOTE = (
    "Travel times and fares are estimates from distance and typical regional prices - "
    "confirm schedules and fares with the operator before booking."
)


def plan_route(
    origin: str | None,
    destination: str | None,
    *,
    travelers: int = 1,
    preference: str | None = "auto",
    round_trip: bool = False,
    live_flight_price: float | None = None,
) -> RoutePlan:
    """Every sensible way from `origin` to `destination`, best first."""
    preference = preference or "auto"
    travelers = max(int(travelers or 1), 1)
    plan = RoutePlan(
        origin=origin,
        destination=destination,
        preference=preference,  # type: ignore[arg-type]
        round_trip=round_trip,
        travelers=travelers,
        source=SOURCE_ESTIMATE,
    )

    start, end = resolve(origin), resolve(destination)
    if start is None or end is None:
        missing = origin if start is None else destination
        plan.notes.append(
            f"{missing} is not in Travel Crew AI's map yet, so ground routes could not be "
            "planned. Flights are still researched."
        )
        return plan
    if start.key == end.key:
        plan.notes.append("Origin and destination are the same place.")
        return plan

    plan.straight_line_km = round(straight_km(start.coords, end.coords))
    candidates = [
        _flight_option(start, end, travelers, round_trip, live_flight_price),
        _ground_option("train", start, end, travelers, round_trip),
        _ground_option("bus", start, end, travelers, round_trip),
        _ground_option("car", start, end, travelers, round_trip),
        _local_option(start, end, travelers, round_trip),
    ]
    tier = tier_for(start.country)
    options = sorted(
        (option for option in candidates if option is not None),
        key=lambda option: _generalised(option.legs, tier, travelers),
    )
    if not options:
        plan.notes.append(f"No practical route was found between {start.name} and {end.name}.")
        return plan

    chosen = 0
    if preference != "auto":
        matching = [i for i, option in enumerate(options) if option.main_mode == preference]
        if matching:
            chosen = matching[0]
            options[chosen].reason = f"Your choice: {MODE_NAMES[preference]}."
        else:
            plan.notes.append(
                f"Travelling by {MODE_NAMES[preference]} is not practical between "
                f"{start.name} and {end.name}, so the best available option is shown instead."
            )
    if options[chosen].reason is None:
        options[chosen].reason = (
            f"Best balance of cost and travel time for {travelers} traveller(s)."
        )
    options[chosen].recommended = True
    plan.options = options
    plan.recommended_index = chosen
    plan.notes.append(ESTIMATE_NOTE)
    return plan
