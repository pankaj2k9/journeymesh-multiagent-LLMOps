"""Column types shared by the models.

``MoneyColumn`` exists because the two databases this project runs against
disagree about decimals. PostgreSQL has a real ``NUMERIC`` and hands back a
``Decimal``; SQLite has no decimal type at all and SQLAlchemy's ``Numeric``
falls back to binding a float, which is exactly the drift the money module
exists to prevent - and it would only show up in the test suite, where the
SQLite fallback runs.

So the value is stored as ``NUMERIC(14, 4)`` on PostgreSQL and as text on
SQLite, and comes back as a ``Decimal`` either way. Application code never
sees the difference.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Dialect, Numeric, String, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB

# JSONB on PostgreSQL, plain JSON everywhere else (the SQLite fallback).
JSONType = JSON().with_variant(JSONB, "postgresql")

MONEY_PRECISION = 14
MONEY_SCALE = 4
_EXPONENT = Decimal(1).scaleb(-MONEY_SCALE)

# Wide enough for the widest amount NUMERIC(14, 4) can hold, sign included.
_TEXT_WIDTH = 24


class MoneyColumn(TypeDecorator[Decimal]):
    """An exact decimal amount. Always reads back as ``Decimal``."""

    impl = Numeric(MONEY_PRECISION, MONEY_SCALE, asdecimal=True)
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(
                Numeric(MONEY_PRECISION, MONEY_SCALE, asdecimal=True)
            )
        return dialect.type_descriptor(String(_TEXT_WIDTH))

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        from app.services.money import quantize, to_decimal

        amount = quantize(to_decimal(value), _EXPONENT)
        if dialect.name == "postgresql":
            return amount
        # Zero-padded plain text so lexical ordering is never mistaken for
        # numeric ordering by a hand-written query against the fallback.
        return format(amount, "f")

    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))


__all__ = ["JSONType", "MoneyColumn", "MONEY_PRECISION", "MONEY_SCALE"]
