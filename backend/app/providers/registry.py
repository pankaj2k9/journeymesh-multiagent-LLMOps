"""Which provider answers, and what happens when it does not.

This is the only module that knows a vendor's name. It resolves the configured
provider for each domain, calls it behind a circuit breaker and a timeout, and
falls back to the offline provider when the call fails.

The fallback is never silent. Every call returns a ``ProviderNote`` saying which
provider answered and with what kind of data, and that note travels with the
offers all the way to the result card. A traveller looking at mock prices is
always told they are looking at mock prices.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from app.core.config import get_settings
from app.core.constants import EVENT_PROVIDER_FAILURE, SOURCE_MOCK
from app.observability import metrics
from app.observability.logging import get_logger
from app.observability.tracing import span
from app.providers.activities.mock import MockActivityProvider
from app.providers.base import ProviderUnavailable, SearchOutcome
from app.providers.circuit import breaker_for
from app.providers.flights.mock import MockFlightProvider
from app.providers.hotels.mock import MockHotelProvider
from app.schemas.search import ProviderNote
from app.security import audit

logger = get_logger("journeymesh.providers")

T = TypeVar("T")

# The offline providers hold their offers in memory, so they are process-wide
# singletons: an offer found by a search must still be there when the traveller
# selects it a minute later.
_mock_flights = MockFlightProvider()
_mock_hotels = MockHotelProvider()
_mock_activities = MockActivityProvider()


def flight_provider() -> Any:
    """The configured flight provider.

    Phase 5 resolves a live adapter here when credentials are present. Until
    then this is the offline provider, and the rest of the application cannot
    tell the difference - which is the whole point of the Protocol.
    """
    return _mock_flights


def hotel_provider() -> Any:
    return _mock_hotels


def activity_provider() -> Any:
    return _mock_activities


def fallback_flight_provider() -> Any:
    return _mock_flights


def fallback_hotel_provider() -> Any:
    return _mock_hotels


def fallback_activity_provider() -> Any:
    return _mock_activities


async def call(
    provider: Any,
    operation: str,
    fn: Callable[[Any], Awaitable[T]],
    *,
    fallback: Any = None,
    kind: str = "flights",
) -> SearchOutcome:
    """Run one provider operation with a breaker, a timeout and a fallback.

    Returns a ``SearchOutcome`` rather than raising, because a search that
    reaches this function has already been validated - the remaining failure
    modes are somebody else's outage, and the right answer to those is a
    degraded result that says so, not a 502 in the traveller's face.
    """
    settings = get_settings()
    breaker = breaker_for(provider.name)

    if not breaker.allows():
        metrics.increment("provider.circuit_open", provider=provider.name)
        logger.warning(
            "provider circuit is open; using the fallback",
            extra={"provider": provider.name, "operation": operation},
        )
        return await _fallback(
            fallback,
            operation,
            fn,
            kind=kind,
            reason=f"{provider.name} is temporarily unavailable",
        )

    started = time.perf_counter()
    try:
        with span(f"provider:{provider.name}.{operation}", kind="tool", provider=provider.name):
            result = await asyncio.wait_for(
                fn(provider), timeout=settings.provider_timeout_seconds
            )
    except Exception as exc:  # noqa: BLE001 - converted into a note below
        latency = int((time.perf_counter() - started) * 1000)
        breaker.record_failure(type(exc).__name__)
        metrics.increment("provider.failed", provider=provider.name, operation=operation)
        metrics.observe("provider.latency_ms", latency, provider=provider.name)
        audit.record(
            EVENT_PROVIDER_FAILURE,
            detail={
                "provider": provider.name,
                "operation": operation,
                "error": type(exc).__name__,
            },
        )
        logger.warning(
            "provider call failed",
            extra={
                "provider": provider.name,
                "operation": operation,
                "error": type(exc).__name__,
            },
        )
        return await _fallback(
            fallback,
            operation,
            fn,
            kind=kind,
            reason=f"{provider.name} did not respond",
        )

    latency = int((time.perf_counter() - started) * 1000)
    breaker.record_success()
    metrics.increment("provider.ok", provider=provider.name, operation=operation)
    metrics.observe("provider.latency_ms", latency, provider=provider.name)

    offers = list(result or [])
    source = offers[0].meta.source if offers else SOURCE_MOCK
    return SearchOutcome(
        offers=offers,
        note=ProviderNote(
            provider=provider.name,
            ok=True,
            source=source,
            latency_ms=latency,
            message=None,
        ),
    )


async def _fallback(
    fallback: Any,
    operation: str,
    fn: Callable[[Any], Awaitable[Any]],
    *,
    kind: str,
    reason: str,
) -> SearchOutcome:
    if fallback is None:
        raise ProviderUnavailable(reason)

    started = time.perf_counter()
    try:
        result = await fn(fallback)
    except Exception as exc:  # noqa: BLE001 - the offline provider failing is a bug
        logger.error(
            "the fallback provider failed",
            extra={"provider": fallback.name, "operation": operation, "error": str(exc)},
        )
        raise ProviderUnavailable(reason) from exc

    latency = int((time.perf_counter() - started) * 1000)
    metrics.increment("provider.fallback_used", provider=fallback.name, kind=kind)
    offers = list(result or [])
    return SearchOutcome(
        offers=offers,
        note=ProviderNote(
            provider=fallback.name,
            ok=True,
            source=offers[0].meta.source if offers else SOURCE_MOCK,
            latency_ms=latency,
            # Surfaced on the result page. A traveller must never be shown
            # offline prices while believing they are live.
            message=f"{reason}; showing offline reference data instead",
        ),
    )


def health() -> list[dict[str, Any]]:
    """Per-provider health, for the operations dashboard."""
    from app.providers import circuit

    return circuit.snapshot()


def reset() -> None:
    """Drop every breaker and offer cache. Used by the test suite."""
    from app.providers import circuit

    circuit.reset_all()
    _mock_flights.__init__()  # type: ignore[misc]
    _mock_hotels.__init__()  # type: ignore[misc]
    _mock_activities.__init__()  # type: ignore[misc]


__all__ = [
    "activity_provider",
    "call",
    "fallback_activity_provider",
    "fallback_flight_provider",
    "fallback_hotel_provider",
    "flight_provider",
    "health",
    "hotel_provider",
    "reset",
]
