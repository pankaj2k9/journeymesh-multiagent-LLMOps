"""Travel provider adapters.

    service -> registry.flight_provider() -> FlightProvider -> [Amadeus | mock]
            <- list[FlightOffer]         <-

Everything above the registry is written against the Protocols in ``base`` and
never against a vendor. That is what makes "swap Amadeus for Duffel" a
configuration change and a new adapter, rather than a rewrite of ranking, the
budget engine and the interface.
"""

from __future__ import annotations

from app.providers.base import (
    ActivityProvider,
    FlightProvider,
    HotelProvider,
    OfferExpired,
    OfferNotFound,
    PriceCheck,
    ProviderUnavailable,
)

__all__ = [
    "ActivityProvider",
    "FlightProvider",
    "HotelProvider",
    "OfferExpired",
    "OfferNotFound",
    "PriceCheck",
    "ProviderUnavailable",
]
