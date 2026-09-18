"""Small building blocks reused by the other schema modules."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# CACHED is a live price re-served from a recent provider response; MOCK is
# the deterministic offline provider. Both are distinguishable from ESTIMATE on
# purpose: an estimate is this application's own arithmetic, a mock is a stand-in
# for a provider, and neither may ever be presented as a price to pay.
DataSource = Literal[
    "LIVE", "CACHED", "SEARCH_DERIVED", "ESTIMATE", "MOCK", "UNAVAILABLE"
]
LanguageCode = Literal["en", "bn", "hi"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime | None) -> datetime | None:
    """Attach UTC to a naive datetime.

    PostgreSQL's ``timestamptz`` hands back an aware datetime; SQLite has no
    timezone type and hands back a naive one, and comparing the two raises
    ``TypeError``. Since the SQLite fallback is what the test suite and a
    credential-free local run both use, every datetime read from the database
    goes through here before it is compared to "now".

    Naive values are *assumed* to be UTC, which is true because everything in
    this application writes UTC.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class TravelCrewModel(BaseModel):
    """Base model with the conventions used across the project."""

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        extra="ignore",
    )


class Provenance(TravelCrewModel):
    """Where a piece of information came from and how much to trust it."""

    source: DataSource = "UNAVAILABLE"
    provider: str | None = None
    retrieved_at: datetime | None = None
    note: str | None = None


class ProviderStatus(TravelCrewModel):
    """Outcome of one provider or MCP call, surfaced to the user."""

    provider: str
    kind: Literal[
        "flights", "hotels", "activities", "weather", "search", "llm", "maps"
    ] = "search"
    ok: bool = False
    source: DataSource = "UNAVAILABLE"
    latency_ms: int | None = None
    message: str | None = None
    retrieved_at: datetime = Field(default_factory=utcnow)


class ErrorResponse(TravelCrewModel):
    error: str
    message: str
    detail: str | None = None
    details: dict[str, Any] | None = None
