"""Human-in-the-loop review schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.schemas.common import LanguageCode, TravelCrewModel

ReviewStatus = Literal[
    "pending",
    "awaiting_review",
    "approved",
    "changes_requested",
    "revision_in_progress",
    "revision_limit_reached",
]


class ApproveRequest(TravelCrewModel):
    response_language: LanguageCode = "en"
    reviewer_note: str | None = Field(default=None, max_length=1000)


class ChangeRequest(TravelCrewModel):
    requested_changes: str = Field(min_length=3, max_length=2000)
    response_language: LanguageCode = "en"

    @field_validator("requested_changes")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("requested_changes cannot be blank")
        return value.strip()


class ReviewRecord(TravelCrewModel):
    revision_number: int = 1
    review_status: ReviewStatus = "pending"
    requested_changes: str | None = None
    selected_agents: list[str] = Field(default_factory=list)
    change_scope: list[str] = Field(default_factory=list)
    reviewed_at: datetime | None = None


class ApproveResponse(TravelCrewModel):
    trip_id: str
    status: str
    revision: int
    final_summary: dict | None = None


class ChangeResponse(TravelCrewModel):
    trip_id: str
    revision: int
    selected_agents: list[str] = Field(default_factory=list)
    change_scope: list[str] = Field(default_factory=list)
    status: str = "awaiting_review"
