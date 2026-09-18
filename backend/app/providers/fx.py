"""Foreign-exchange rate providers.

Same shape as every other provider in this project: a Protocol, a real adapter,
and an offline implementation that keeps the application working with no
credentials at all. The offline rates are labelled MOCK and the label travels
with them, so a converted figure never passes for a live one.

The default adapter is Frankfurter, which serves European Central Bank
reference rates with no API key and no rate limit. Daily granularity is the
right resolution here: this converts a budget, not a trade, and §46's
disclaimer already says the card rate will differ.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

import httpx

from app.core.config import get_settings
from app.observability.logging import get_logger
from app.services.money import to_decimal

logger = get_logger("journeymesh.providers.fx")


@runtime_checkable
class FxProvider(Protocol):
    """A source of exchange rates quoted against one base currency."""

    name: str

    async def fetch_rates(self, base: str, symbols: list[str]) -> RateTable:
        """Units of each symbol per one unit of ``base``."""
        ...


class RateTable:
    """One provider response: a base, a set of rates, and when they are for."""

    def __init__(
        self,
        *,
        base: str,
        rates: dict[str, Decimal],
        rate_date: date | None,
        provider: str,
        retrieved_at: datetime | None = None,
    ) -> None:
        self.base = base.upper()
        self.rates = rates
        self.rate_date = rate_date
        self.provider = provider
        self.retrieved_at = retrieved_at or datetime.now(timezone.utc)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"RateTable(base={self.base}, n={len(self.rates)}, provider={self.provider})"


class FrankfurterProvider:
    """European Central Bank reference rates, via Frankfurter.

    No key, no quota. The ECB publishes once per working day, so a weekend
    request returns Friday's rates with Friday's ``date`` - which is why
    ``rate_date`` is carried separately from ``retrieved_at`` rather than
    conflated with it.

    **It does not cover every currency this application supports.** The ECB
    publishes around thirty reference rates, and BDT and AED are not among
    them - which matters, because taka is the headline currency of this
    product. A missing symbol is simply absent from the response, so the
    service treats coverage as per-currency: pairs the provider quotes are
    LIVE, and the rest fall back to the indicative table and are labelled
    MOCK. Set ``FX_PROVIDER=erapi`` for a keyless source that does cover them.
    """

    name = "frankfurter"

    #: Currencies this application supports that the ECB does not publish.
    NOT_COVERED = frozenset({"BDT", "AED"})

    async def fetch_rates(self, base: str, symbols: list[str]) -> RateTable:
        settings = get_settings()
        wanted = [code for code in symbols if code.upper() != base.upper()]
        params: dict[str, Any] = {"base": base.upper()}
        if wanted:
            params["symbols"] = ",".join(sorted(code.upper() for code in wanted))

        # Frankfurter has moved host once already and answers 301 on the old
        # one. Following redirects keeps a working deployment working through
        # that kind of move rather than failing over to indicative rates.
        async with httpx.AsyncClient(
            timeout=settings.fx_timeout_seconds, follow_redirects=True
        ) as client:
            response = await client.get(
                f"{settings.fx_base_url.rstrip('/')}/latest", params=params
            )
            response.raise_for_status()

            # A captive portal or corporate proxy answers 200 with an HTML
            # block page, and `.json()` then fails with a parse error that
            # says nothing useful. Checking the content type turns that into
            # a diagnosable message before anything tries to read a rate out
            # of a login form.
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type.lower():
                raise ValueError(
                    f"the FX provider returned {content_type or 'an unknown type'} "
                    "rather than JSON; a proxy or captive portal may have "
                    "intercepted the request"
                )
            payload = response.json()

        raw = payload.get("rates") or {}
        if not raw:
            raise ValueError("the FX provider returned no rates")

        rates = {code.upper(): to_decimal(value) for code, value in raw.items()}
        # The base is not included in its own response, and every consumer
        # needs it present to compute a cross rate.
        rates.setdefault(base.upper(), Decimal(1))

        published: date | None = None
        if isinstance(payload.get("date"), str):
            try:
                published = date.fromisoformat(payload["date"])
            except ValueError:
                published = None

        return RateTable(
            base=base, rates=rates, rate_date=published, provider=self.name
        )


class ExchangeRateApiProvider:
    """open.er-api.com - keyless, and covers every currency this app supports.

    Broader coverage than the ECB set, including BDT and AED, at the cost of
    being an aggregate of sources rather than a central bank's published
    reference. For converting a travel budget that is the better trade; for
    anything settling money it would not be, and nothing here settles money.
    """

    name = "erapi"

    async def fetch_rates(self, base: str, symbols: list[str]) -> RateTable:
        settings = get_settings()
        base_upper = base.upper()

        async with httpx.AsyncClient(
            timeout=settings.fx_timeout_seconds, follow_redirects=True
        ) as client:
            response = await client.get(
                f"{settings.fx_erapi_base_url.rstrip('/')}/{base_upper}"
            )
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type.lower():
                raise ValueError(
                    f"the FX provider returned {content_type or 'an unknown type'} "
                    "rather than JSON; a proxy or captive portal may have "
                    "intercepted the request"
                )
            payload = response.json()

        if payload.get("result") != "success":
            raise ValueError(f"the FX provider reported {payload.get('result')!r}")

        raw = payload.get("rates") or {}
        wanted = {code.upper() for code in symbols} | {base_upper}
        rates = {
            code.upper(): to_decimal(value)
            for code, value in raw.items()
            if code.upper() in wanted
        }
        if not rates:
            raise ValueError("the FX provider returned no usable rates")
        rates.setdefault(base_upper, Decimal(1))

        published: date | None = None
        stamp = payload.get("time_last_update_utc")
        if isinstance(stamp, str):
            try:
                from email.utils import parsedate_to_datetime

                published = parsedate_to_datetime(stamp).date()
            except (TypeError, ValueError):
                published = None

        return RateTable(
            base=base_upper, rates=rates, rate_date=published, provider=self.name
        )


class OfflineFxProvider:
    """The credential-free fallback. Its rates are indicative and labelled MOCK."""

    name = "offline_table"

    async def fetch_rates(self, base: str, symbols: list[str]) -> RateTable:
        from app.services.currency import _OFFLINE_PER_EUR

        per_eur = {code: to_decimal(value) for code, value in _OFFLINE_PER_EUR.items()}
        base_upper = base.upper()
        if base_upper not in per_eur:
            raise ValueError(f"no offline rate for {base_upper}")

        divisor = per_eur[base_upper]
        return RateTable(
            base=base_upper,
            rates={code: value / divisor for code, value in per_eur.items()},
            rate_date=None,
            provider=self.name,
        )


_offline = OfflineFxProvider()
_frankfurter = FrankfurterProvider()
_erapi = ExchangeRateApiProvider()

_BY_NAME = {
    "frankfurter": _frankfurter,
    "erapi": _erapi,
    "offline": _offline,
}


def fx_provider() -> Any:
    """The configured provider, or the offline table when FX is switched off."""
    settings = get_settings()
    if not settings.fx_enabled:
        return _offline
    return _BY_NAME.get(settings.fx_provider, _frankfurter)


def offline_provider() -> Any:
    return _offline


__all__ = [
    "ExchangeRateApiProvider",
    "FrankfurterProvider",
    "FxProvider",
    "OfflineFxProvider",
    "RateTable",
    "fx_provider",
    "offline_provider",
]
