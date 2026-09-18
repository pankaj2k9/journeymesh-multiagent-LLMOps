"""Deterministic pseudo-randomness for the offline providers.

The offline providers must produce the *same* offers for the same search,
every time, in every process. Not because realism demands it, but because
everything downstream is tested against them: a ranking test that sorts a
different list on each run proves nothing, and a budget that changes between
two renders of one search page looks like a bug in the budget.

So there is no ambient randomness anywhere in the mock providers. Every value
comes from a generator seeded with the search's own cache key.
"""

from __future__ import annotations

import hashlib
import random
from decimal import Decimal

from app.services.money import quantize, to_decimal


def generator(*parts: str) -> random.Random:
    """A generator seeded by the given strings, stable across processes.

    ``hash()`` is deliberately not used: Python salts string hashing per
    process, so the same search would produce different offers in the web
    worker and in a background job.
    """
    digest = hashlib.sha256("::".join(parts).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def jitter(rng: random.Random, base: Decimal | float | str, spread: float) -> Decimal:
    """Vary an amount by +/- ``spread`` proportionally, exactly.

    The arithmetic stays in Decimal, so an offline price is as exact as a live
    one and a test can assert on it to the cent.
    """
    amount = to_decimal(base)
    factor = to_decimal(1 + rng.uniform(-spread, spread))
    return quantize(amount * factor, Decimal("0.01"))


__all__ = ["generator", "jitter"]
