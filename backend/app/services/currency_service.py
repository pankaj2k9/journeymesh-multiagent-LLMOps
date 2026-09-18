"""The currency service.

Wraps the pure helpers in ``services.currency`` with a rate cache and a
provider, and is the single entry point anything else uses to convert money.

The lookup order is cache, then provider, then the offline table:

  * a **cached** rate younger than ``FX_CACHE_HOURS`` is used as is and
    reported as ``CACHED`` - the ECB publishes once a working day, so
    refetching more often spends a request to receive the same numbers;
  * otherwise the provider is asked, and the whole table it returns is stored,
    so one fetch serves every pair by cross-rate;
  * if the provider fails, an **expired** cached rate is preferred to the
    offline table - a rate from this morning beats an indicative constant - and
    only when there is nothing at all does the offline table answer, labelled
    ``MOCK``.

A rate is never invented and never silently defaulted to 1.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import (
    EVENT_FX_RATE_FALLBACK,
    EVENT_FX_RATE_FETCHED,
    SOURCE_CACHED,
    SOURCE_LIVE,
    SOURCE_MOCK,
    SUPPORTED_CURRENCIES,
)
from app.db.models import FxRate
from app.observability import metrics
from app.observability.logging import get_logger
from app.providers import fx as fx_providers
from app.schemas.common import ensure_utc
from app.security import audit
from app.services.currency import (
    RATE_BASE,
    ConvertedAmount,
    ExchangeRate,
    UnsupportedCurrency,
    apply,
    identity_rate,
    offline_rate,
)
from app.services.money import Money, normalise_currency, quantize, to_decimal

logger = get_logger("journeymesh.services.currency")


class CurrencyService:
    def __init__(self, session: Session | None = None) -> None:
        self.session = session

    # ---- public API ------------------------------------------------------
    def supported_currencies(self) -> list[dict[str, Any]]:
        from app.core.constants import CURRENCY_SYMBOLS
        from app.services.money import minor_units

        return [
            {
                "code": code,
                "symbol": CURRENCY_SYMBOLS.get(code, code),
                "decimal_places": minor_units(code),
            }
            for code in SUPPORTED_CURRENCIES
        ]

    async def get_exchange_rate(self, source: str, target: str) -> ExchangeRate:
        """The rate from one currency to another, with its provenance."""
        source = normalise_currency(source)
        target = normalise_currency(target)
        if source == target:
            return identity_rate(source)

        cached = self._cached_pair(source, target)
        if cached is not None and not self._is_stale(cached):
            metrics.increment("fx.cache_hit")
            return cached

        try:
            refreshed = await self._refresh(source, target)
            if refreshed is not None:
                return refreshed
            # The provider answered and its table was stored, but it does not
            # publish this pair - the ECB set, for instance, has no BDT or AED.
            # Only this pair degrades; every currency the provider does cover
            # is now cached and live.
            logger.info(
                "fx provider does not cover this pair",
                extra={"pair": f"{source}->{target}"},
            )
            metrics.increment("fx.pair_not_covered", pair=f"{source}{target}")
        except Exception as exc:  # noqa: BLE001 - degraded below, never fatal
            logger.warning(
                "fx provider failed", extra={"error": type(exc).__name__}
            )
            metrics.increment("fx.provider_failed")

        # A stale real rate beats an indicative constant.
        if cached is not None:
            audit.record(
                EVENT_FX_RATE_FALLBACK,
                detail={"pair": f"{source}->{target}", "used": "stale_cache"},
                session=self.session,
            )
            return ExchangeRate(
                source_currency=source,
                target_currency=target,
                rate=cached.rate,
                retrieved_at=cached.retrieved_at,
                source=SOURCE_CACHED,
                provider=cached.provider,
            )

        metrics.increment("fx.offline_used")
        audit.record(
            EVENT_FX_RATE_FALLBACK,
            detail={"pair": f"{source}->{target}", "used": "offline_table"},
            session=self.session,
        )
        return offline_rate(source, target)

    async def convert(
        self, amount: Money | Any, target: str, *, source: str | None = None
    ) -> ConvertedAmount:
        """Convert one amount, keeping the original beside the result."""
        money = (
            amount
            if isinstance(amount, Money)
            else Money(to_decimal(amount), normalise_currency(source or target))
        )
        rate = await self.get_exchange_rate(money.currency, target)
        return apply(money, rate)

    async def convert_many(
        self, amounts: list[Money], target: str
    ) -> list[ConvertedAmount]:
        """Convert several amounts against one rate per pair.

        One rate per pair for the whole call, so a page of converted figures
        carries a single timestamp rather than a dozen that differ by
        milliseconds and invite the question of which one applied.
        """
        rates: dict[str, ExchangeRate] = {}
        results: list[ConvertedAmount] = []
        for money in amounts:
            if money.currency not in rates:
                rates[money.currency] = await self.get_exchange_rate(
                    money.currency, target
                )
            results.append(apply(money, rates[money.currency]))
        return results

    def format_currency(self, amount: Money, *, locale: str = "en") -> str:
        """A plain, unambiguous rendering. Locale-aware formatting is the UI's job.

        The interface formats with ``Intl.NumberFormat`` in the traveller's
        language, which places the symbol where that language places it. This
        exists for logs, notifications and anywhere a string has to be built
        server-side.
        """
        from app.core.constants import CURRENCY_SYMBOLS

        symbol = CURRENCY_SYMBOLS.get(amount.currency, "")
        return f"{symbol}{amount.as_str()} {amount.currency}".strip()

    # ---- cache -----------------------------------------------------------
    def _cached_pair(self, source: str, target: str) -> ExchangeRate | None:
        """A stored rate for this pair, derived from the base table if needed."""
        if self.session is None:
            return None

        direct = self._row(source, target)
        if direct is not None:
            return self._as_rate(direct, source, target, direct.rate)

        # Cross the two base-quoted rows: BDT per EUR / USD per EUR.
        base_source = self._row(RATE_BASE, source)
        base_target = self._row(RATE_BASE, target)
        if base_source is None or base_target is None:
            return None
        if base_source.rate == 0:
            return None

        rate = quantize(
            to_decimal(base_target.rate) / to_decimal(base_source.rate),
            Decimal("0.00000001"),
        )
        # The pair is only as fresh as its older half.
        older = min(
            ensure_utc(base_source.retrieved_at), ensure_utc(base_target.retrieved_at)
        )
        return ExchangeRate(
            source_currency=source,
            target_currency=target,
            rate=rate,
            retrieved_at=older,
            source=SOURCE_CACHED,
            provider=base_target.provider,
        )

    def _row(self, base: str, quote: str) -> FxRate | None:
        if self.session is None:
            return None
        return self.session.scalar(
            select(FxRate).where(
                FxRate.base_currency == base, FxRate.quote_currency == quote
            )
        )

    def _as_rate(
        self, row: FxRate, source: str, target: str, rate: Decimal
    ) -> ExchangeRate:
        return ExchangeRate(
            source_currency=source,
            target_currency=target,
            rate=to_decimal(rate),
            retrieved_at=ensure_utc(row.retrieved_at) or datetime.now(timezone.utc),
            source=SOURCE_CACHED,
            provider=row.provider,
        )

    def _is_stale(self, rate: ExchangeRate) -> bool:
        ttl = timedelta(hours=get_settings().fx_cache_hours)
        return rate.age() > ttl

    async def _refresh(self, source: str, target: str) -> ExchangeRate | None:
        """Fetch the whole base table, store it, and answer this pair from it."""
        provider = fx_providers.fx_provider()
        table = await provider.fetch_rates(RATE_BASE, list(SUPPORTED_CURRENCIES))

        live = provider.name != "offline_table"
        self._store(table, live=live)

        per_base = table.rates
        # Not an error: a provider legitimately covers a subset. The caller
        # falls back for this pair alone, and everything the provider did
        # return has already been stored above.
        if source not in per_base or target not in per_base:
            return None
        if per_base[source] == 0:
            raise UnsupportedCurrency(f"provider returned a zero rate for {source}")

        audit.record(
            EVENT_FX_RATE_FETCHED,
            detail={"provider": provider.name, "base": table.base, "pairs": len(per_base)},
            session=self.session,
        )
        metrics.increment("fx.fetched", provider=provider.name)

        return ExchangeRate(
            source_currency=source,
            target_currency=target,
            rate=quantize(
                to_decimal(per_base[target]) / to_decimal(per_base[source]),
                Decimal("0.00000001"),
            ),
            retrieved_at=table.retrieved_at,
            source=SOURCE_LIVE if live else SOURCE_MOCK,
            provider=provider.name,
        )

    def _store(self, table: Any, *, live: bool) -> None:
        """Replace the cached table. One row per pair, refreshed in place."""
        if self.session is None:
            return
        for quote, value in table.rates.items():
            if quote not in SUPPORTED_CURRENCIES:
                continue
            row = self._row(table.base, quote)
            if row is None:
                row = FxRate(base_currency=table.base, quote_currency=quote)
                self.session.add(row)
            row.rate = to_decimal(value)
            row.provider = table.provider
            row.source = SOURCE_LIVE if live else SOURCE_MOCK
            row.rate_date = table.rate_date
            row.retrieved_at = table.retrieved_at
        self.session.flush()


__all__ = ["CurrencyService"]
