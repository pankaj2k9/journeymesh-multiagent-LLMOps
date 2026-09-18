"""Decimal-safe currency arithmetic.

Every amount in Travel Crew AI that a traveller could be asked to pay passes
through this module. The rules it enforces are the ones that separate a
planning tool from a booking platform:

  * money is ``Decimal``, never ``float`` - ``0.1 + 0.2`` is not ``0.3`` and a
    total assembled from floats drifts by cents that a provider will not honour;
  * money carries its currency, and two different currencies never add - there
    is no ambient exchange rate in this system, so a cross-currency sum would
    be a fabricated number;
  * rounding happens once, at the currency's own precision, using
    ``ROUND_HALF_UP`` - bankers' rounding is the Python default and is not what
    a fare quote uses.

Nothing here talks to a model, a provider or the database. It is the bottom of
the budget engine and is meant to stay that way.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.core.constants import SUPPORTED_CURRENCIES

__all__ = [
    "Money",
    "CurrencyMismatch",
    "InvalidAmount",
    "to_decimal",
    "quantize",
    "minor_units",
    "percentage_of",
]


class CurrencyMismatch(ValueError):
    """Raised when two amounts in different currencies are combined."""


class InvalidAmount(ValueError):
    """Raised when a value cannot be read as an amount of money."""


# ISO 4217 minor units for the currencies this application supports. Most are
# two; the zero-decimal ones are the reason this table exists at all, because
# quantizing JPY to two places invents a precision the currency does not have.
_MINOR_UNITS: dict[str, int] = {
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "INR": 2,
    "BDT": 2,
    "AED": 2,
    "SGD": 2,
    "AUD": 2,
    "JPY": 0,
}

# The precision amounts are stored at. Wider than any currency's own precision
# so that a per-traveller division is exact until it is presented.
STORAGE_EXPONENT = Decimal("0.0001")


def minor_units(currency: str) -> int:
    """Decimal places this currency is actually denominated in."""
    return _MINOR_UNITS.get(normalise_currency(currency), 2)


def normalise_currency(currency: str) -> str:
    code = (currency or "").strip().upper()
    if code not in SUPPORTED_CURRENCIES:
        raise InvalidAmount(f"unsupported currency: {currency!r}")
    return code


def to_decimal(value: Any) -> Decimal:
    """Read a number, a string or a Decimal as an exact Decimal.

    ``float`` is accepted but converted through ``repr`` rather than directly,
    because ``Decimal(0.1)`` is ``0.1000000000000000055511151231257827``. The
    conversion is here so that legacy float columns and provider payloads can
    cross the boundary exactly once, at a place that is tested.
    """
    if isinstance(value, Decimal):
        candidate = value
    elif isinstance(value, bool):
        raise InvalidAmount("a boolean is not an amount")
    elif isinstance(value, int):
        candidate = Decimal(value)
    elif isinstance(value, float):
        candidate = Decimal(repr(value))
    elif isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            raise InvalidAmount("empty string is not an amount")
        try:
            candidate = Decimal(text)
        except InvalidOperation as exc:
            raise InvalidAmount(f"{value!r} is not an amount") from exc
    else:
        raise InvalidAmount(f"{type(value).__name__} is not an amount")

    if not candidate.is_finite():
        raise InvalidAmount("an amount must be finite")
    return candidate


def quantize(value: Decimal, exponent: Decimal = STORAGE_EXPONENT) -> Decimal:
    """Round to a fixed precision, half-up, the way a fare quote rounds."""
    return value.quantize(exponent, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, order=False)
class Money:
    """An exact amount in one currency.

    Immutable, so an amount cannot be mutated after it has been checked, and
    every operator returns a new ``Money`` at storage precision.
    """

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", normalise_currency(self.currency))
        object.__setattr__(self, "amount", quantize(to_decimal(self.amount)))

    # ---- construction ----------------------------------------------------
    @classmethod
    def of(cls, value: Any, currency: str) -> Money:
        return cls(to_decimal(value), currency)

    @classmethod
    def zero(cls, currency: str) -> Money:
        return cls(Decimal(0), currency)

    # ---- arithmetic ------------------------------------------------------
    def _check(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatch(
                f"cannot combine {self.currency} and {other.currency}: "
                "Travel Crew AI does not convert currencies"
            )

    def __add__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount - other.amount, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount, self.currency)

    def times(self, factor: Any) -> Money:
        """Multiply by a count or a ratio. Money times money is meaningless."""
        return Money(self.amount * to_decimal(factor), self.currency)

    def divided_by(self, divisor: Any) -> Money:
        """Split into equal parts.

        The result keeps storage precision, so dividing a fare across three
        travellers and multiplying back gives the fare again. Presentation
        rounding happens in ``rounded``, once, at the end.
        """
        value = to_decimal(divisor)
        if value == 0:
            raise InvalidAmount("cannot divide an amount by zero")
        return Money(self.amount / value, self.currency)

    # ---- comparison ------------------------------------------------------
    def __lt__(self, other: Money) -> bool:
        self._check(other)
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        self._check(other)
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        self._check(other)
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        self._check(other)
        return self.amount >= other.amount

    # ---- inspection ------------------------------------------------------
    @property
    def is_zero(self) -> bool:
        return self.amount == 0

    @property
    def is_negative(self) -> bool:
        return self.amount < 0

    def rounded_amount(self) -> Decimal:
        """The bare Decimal at this currency's own precision.

        Kept separate from ``rounded`` because constructing a ``Money`` widens
        the value back to storage precision - correct for arithmetic, wrong for
        display, and the reason ``as_str`` does not route through it.
        """
        places = minor_units(self.currency)
        return quantize(self.amount, Decimal(1).scaleb(-places))

    def rounded(self) -> Money:
        """The amount at its currency's own precision - what a user is shown."""
        return Money(self.rounded_amount(), self.currency)

    def as_str(self) -> str:
        """Plain decimal text, never scientific notation. The wire format."""
        return format(self.rounded_amount(), "f")

    def __str__(self) -> str:
        return f"{self.as_str()} {self.currency}"


def percentage_of(part: Money, whole: Money) -> Decimal | None:
    """``part`` as a percentage of ``whole``, or None when there is no whole.

    Returns a Decimal rounded to one place. A zero or negative total budget has
    no meaningful percentage, and returning ``0`` there would read as "this
    costs nothing" on a budget bar.
    """
    part._check(whole)
    if whole.amount <= 0:
        return None
    ratio = (part.amount / whole.amount) * Decimal(100)
    return quantize(ratio, Decimal("0.1"))


def total(amounts: list[Money], currency: str) -> Money:
    """Sum a list that may be empty, in a known currency."""
    result = Money.zero(currency)
    for item in amounts:
        result = result + item
    return result
