"""Foreign exchange.

A trip is budgeted in one currency. Its providers are not: a Dhaka family
budgeting in taka books a flight priced in dollars and a hotel priced in
euros. Something has to convert, and this is the only thing allowed to.

Three rules shape the module.

**Conversion is explicit and recorded.** ``Money`` still refuses to add two
currencies - that guard from the budget engine is not relaxed here. Instead a
foreign amount is converted *once*, at the moment it is written, and the rate
and its timestamp are stored on the row. "Why is this line ৳79,950?" is then
answerable years later, which a silently converted number never is.

**A converted amount is an estimate, and says so.** The provider bills in its
own currency; the traveller's bank applies its own rate and its own spread.
``ConvertedAmount.is_estimate`` is always true and travels with the figure to
the interface, so nothing ever implies that ৳79,950 is the guaranteed card
charge.

**A rate has provenance like any other number.** LIVE from the FX provider,
CACHED from a recent one, or MOCK from the offline table that keeps this
project runnable with no credentials at all. The offline rates are stale by
construction and are labelled as such wherever they are used.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.core.constants import (
    CURRENCY_BY_COUNTRY,
    DEFAULT_CURRENCY,
    SOURCE_CACHED,
    SOURCE_LIVE,
    SOURCE_MOCK,
    SUPPORTED_CURRENCIES,
)
from app.observability.logging import get_logger
from app.services.money import Money, normalise_currency, quantize, to_decimal

logger = get_logger("journeymesh.services.currency")

# Rates are quoted against one base so that N currencies need N rates rather
# than N squared. The euro is the base because the ECB publishes against it,
# which is what the default provider serves.
RATE_BASE = "EUR"

# Rates are stored at higher precision than money. A BDT amount converted from
# USD at four decimal places would round the rate before it multiplies, and the
# error lands in the traveller's total rather than in the rate.
RATE_EXPONENT = Decimal("0.00000001")


class UnsupportedCurrency(ValueError):
    """Raised for a currency this application does not handle."""


@dataclass(frozen=True)
class ExchangeRate:
    """One rate, with where it came from and when."""

    source_currency: str
    target_currency: str
    rate: Decimal
    retrieved_at: datetime
    source: str = SOURCE_MOCK
    provider: str = "offline"

    @property
    def is_live(self) -> bool:
        return self.source == SOURCE_LIVE

    def age(self, *, now: datetime | None = None) -> timedelta:
        return (now or datetime.now(timezone.utc)) - self.retrieved_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_currency": self.source_currency,
            "target_currency": self.target_currency,
            "rate": format(self.rate, "f"),
            "retrieved_at": self.retrieved_at.isoformat(),
            "source": self.source,
            "provider": self.provider,
        }


@dataclass(frozen=True)
class ConvertedAmount:
    """A provider's price, and what it approximately costs the traveller.

    Both halves are kept. ``original`` is what will actually be charged and is
    never overwritten; ``converted`` is for reading a budget in one currency.
    """

    original: Money
    converted: Money
    rate: ExchangeRate
    # Always true. A conversion is an estimate of a future card charge, and no
    # combination of inputs makes it a guarantee.
    is_estimate: bool = True

    @property
    def unchanged(self) -> bool:
        """True when no conversion happened - the currencies already matched."""
        return self.original.currency == self.converted.currency

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_amount": self.original.as_str(),
            "original_currency": self.original.currency,
            "amount": self.converted.as_str(),
            "currency": self.converted.currency,
            "exchange_rate": format(self.rate.rate, "f"),
            "exchange_rate_source": self.rate.source,
            "exchange_rate_retrieved_at": self.rate.retrieved_at.isoformat(),
            "is_estimate": self.is_estimate and not self.unchanged,
        }


# ---- the offline table --------------------------------------------------
#
# Indicative units of each currency per euro. Deliberately round: these are a
# stand-in for an FX provider, they are labelled MOCK wherever they surface,
# and pretending to four decimal places would dress a guess up as a quote.
_OFFLINE_PER_EUR: dict[str, str] = {
    "EUR": "1",
    "USD": "1.09",
    "GBP": "0.85",
    "INR": "91.00",
    "BDT": "119.00",
    "AED": "4.00",
    "SGD": "1.47",
    "JPY": "158.00",
    "AUD": "1.65",
    "CAD": "1.48",
}

# Sanity: the offline table must cover everything the application accepts, or a
# supported currency would silently have no fallback rate at all.
assert set(_OFFLINE_PER_EUR) == set(SUPPORTED_CURRENCIES)


def offline_rate(source: str, target: str) -> ExchangeRate:
    """A rate from the offline table. Always labelled MOCK."""
    source = normalise_currency(source)
    target = normalise_currency(target)
    per_eur_source = to_decimal(_OFFLINE_PER_EUR[source])
    per_eur_target = to_decimal(_OFFLINE_PER_EUR[target])
    return ExchangeRate(
        source_currency=source,
        target_currency=target,
        rate=quantize(per_eur_target / per_eur_source, RATE_EXPONENT),
        retrieved_at=datetime.now(timezone.utc),
        source=SOURCE_MOCK,
        provider="offline_table",
    )


def cross_rate(
    per_base: dict[str, Decimal],
    source: str,
    target: str,
    *,
    retrieved_at: datetime,
    provider: str,
    cached: bool = False,
) -> ExchangeRate:
    """Derive one currency pair from a table quoted against a single base.

    USD→BDT is (BDT per EUR) / (USD per EUR). Doing it here rather than asking
    the provider per pair is what keeps one daily fetch serving every pair.
    """
    source = normalise_currency(source)
    target = normalise_currency(target)
    if source not in per_base or target not in per_base:
        raise UnsupportedCurrency(f"no rate available for {source}->{target}")
    return ExchangeRate(
        source_currency=source,
        target_currency=target,
        rate=quantize(per_base[target] / per_base[source], RATE_EXPONENT),
        retrieved_at=retrieved_at,
        source=SOURCE_CACHED if cached else SOURCE_LIVE,
        provider=provider,
    )


def apply(amount: Money, rate: ExchangeRate) -> ConvertedAmount:
    """Convert one amount using a specific rate.

    Separate from fetching so that a whole budget can be converted against a
    single rate - one timestamp for the page, rather than a dozen rows each
    quietly converted at a slightly different moment.
    """
    if amount.currency != rate.source_currency:
        raise UnsupportedCurrency(
            f"rate is {rate.source_currency}->{rate.target_currency}, "
            f"but the amount is in {amount.currency}"
        )
    converted = Money(
        quantize(amount.amount * rate.rate), rate.target_currency
    )
    return ConvertedAmount(original=amount, converted=converted, rate=rate)


def identity_rate(currency: str) -> ExchangeRate:
    """The rate from a currency to itself: one, always, from nowhere."""
    currency = normalise_currency(currency)
    return ExchangeRate(
        source_currency=currency,
        target_currency=currency,
        rate=Decimal(1),
        retrieved_at=datetime.now(timezone.utc),
        source=SOURCE_LIVE,
        provider="identity",
    )


# ---- which currency to show ---------------------------------------------
def currency_for_country(country_code: str | None) -> str | None:
    if not country_code:
        return None
    return CURRENCY_BY_COUNTRY.get(country_code.strip().upper())


def currency_from_locale(accept_language: str | None) -> str | None:
    """Read a currency out of a browser's ``Accept-Language`` header.

    The *region* names the currency, not the language: an ``en-IN`` traveller
    spends rupees and a ``bn-GB`` one spends pounds. A bare ``en`` names no
    region and therefore no currency, which is correct - guessing dollars from
    it is how an application decides a Bangladeshi user is American.
    """
    if not accept_language:
        return None
    for part in accept_language.split(","):
        tag = part.split(";")[0].strip()
        if "-" not in tag:
            continue
        region = tag.rsplit("-", 1)[-1]
        if len(region) != 2:
            continue
        currency = currency_for_country(region)
        if currency:
            return currency
    return None


def resolve_currency(
    *,
    user_preference: str | None = None,
    trip_currency: str | None = None,
    home_country: str | None = None,
    accept_language: str | None = None,
    default: str = DEFAULT_CURRENCY,
) -> str:
    """Decide which currency to show, in the order the specification sets.

    Account preference, then the trip's own currency, then a stated home
    country, then the browser's locale, then the application default.

    IP geolocation is deliberately absent. It is wrong for anyone travelling,
    on a VPN, or on a corporate network, and being silently re-denominated by
    an invisible signal is worse than being shown the default and changing it.
    Every step here is something the traveller either chose or sent.
    """
    for candidate in (
        user_preference,
        trip_currency,
        currency_for_country(home_country),
        currency_from_locale(accept_language),
        default,
    ):
        if not candidate:
            continue
        code = str(candidate).strip().upper()
        if code in SUPPORTED_CURRENCIES:
            return code
    return DEFAULT_CURRENCY


__all__ = [
    "ConvertedAmount",
    "ExchangeRate",
    "RATE_BASE",
    "UnsupportedCurrency",
    "apply",
    "cross_rate",
    "currency_for_country",
    "currency_from_locale",
    "identity_rate",
    "offline_rate",
    "resolve_currency",
]
