"""How money crosses the API boundary.

Amounts are serialised as **strings**, not numbers. JSON has one numeric type
and it is a double: ``1836.35`` does not survive a round trip through
JavaScript intact, and a budget page that adds up rendered floats will
eventually disagree with the backend by a cent. A string is exact, sorts
correctly once parsed, and makes it obvious at the call site that the value
needs a decimal-aware parser rather than ``+value``.

``MoneyAmount`` accepts a number or a string on the way in - a provider payload
and a form field both arrive as one of those - and always leaves as a string.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from pydantic import BeforeValidator, Field, PlainSerializer

from app.schemas.common import TravelCrewModel


def _as_decimal(value: Any) -> Any:
    if value is None or isinstance(value, Decimal):
        return value
    from app.services.money import InvalidAmount, to_decimal

    try:
        return to_decimal(value)
    except InvalidAmount as exc:
        raise ValueError(str(exc)) from exc


def _as_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


MoneyAmount = Annotated[
    Decimal,
    BeforeValidator(_as_decimal),
    PlainSerializer(_as_text, return_type=str, when_used="json"),
]
"""An exact amount. Parsed from a number or a string, emitted as a string."""

OptionalMoney = Annotated[
    Decimal | None,
    BeforeValidator(_as_decimal),
    PlainSerializer(_as_text, return_type=str | None, when_used="json"),
]


class MoneyValue(TravelCrewModel):
    """An amount together with the currency it is denominated in."""

    amount: MoneyAmount = Field(default=Decimal(0))
    currency: str = "USD"

    @classmethod
    def from_money(cls, money: Any) -> MoneyValue:
        """Build from a ``services.money.Money``, at display precision."""
        return cls(amount=money.rounded_amount(), currency=money.currency)


__all__ = ["MoneyAmount", "OptionalMoney", "MoneyValue"]
