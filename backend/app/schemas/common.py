"""Small building blocks reused by the other schema modules."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DataSource = Literal["LIVE", "SEARCH_DERIVED", "ESTIMATE", "UNAVAILABLE"]
LanguageCode = Literal["en", "bn", "hi"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JourneyMeshModel(BaseModel):
    """Base model with the conventions used across the project."""

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        extra="ignore",
    )


class Provenance(JourneyMeshModel):
    """Where a piece of information came from and how much to trust it."""

    source: DataSource = "UNAVAILABLE"
    provider: str | None = None
    retrieved_at: datetime | None = None
    note: str | None = None


class ProviderStatus(JourneyMeshModel):
    """Outcome of one provider or MCP call, surfaced to the user."""

    provider: str
    kind: Literal["flights", "hotels", "weather", "search", "llm"] = "search"
    ok: bool = False
    source: DataSource = "UNAVAILABLE"
    latency_ms: int | None = None
    message: str | None = None
    retrieved_at: datetime = Field(default_factory=utcnow)


class ErrorResponse(JourneyMeshModel):
    error: str
    message: str
    detail: str | None = None
    details: dict[str, Any] | None = None
