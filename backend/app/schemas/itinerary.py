"""Itinerary schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.schemas.common import JourneyMeshModel

TimeSlot = Literal["morning", "afternoon", "evening"]


class Activity(JourneyMeshModel):
    title: str
    description: str | None = None
    location: str | None = None
    duration_minutes: int | None = None
    estimated_cost: float | None = None
    currency: str | None = None
    indoor: bool = False
    family_friendly: bool = True
    tags: list[str] = Field(default_factory=list)


class DaySlot(JourneyMeshModel):
    slot: TimeSlot
    activities: list[Activity] = Field(default_factory=list)
    travel_time_minutes: int | None = None
    notes: str | None = None


class ItineraryDay(JourneyMeshModel):
    day: int
    date: str | None = None
    title: str | None = None
    summary: str | None = None
    slots: list[DaySlot] = Field(default_factory=list)
    estimated_day_cost: float | None = None
    weather_note: str | None = None
    rest_note: str | None = None


class ItineraryPlan(JourneyMeshModel):
    destination: str | None = None
    days: list[ItineraryDay] = Field(default_factory=list)
    total_days: int = 0
    pacing: Literal["relaxed", "balanced", "packed"] = "balanced"
    estimated_activity_cost: float = 0.0
    currency: str | None = None
    travel_tips: list[str] = Field(default_factory=list)
    # Phrase codes for the same tips, rendered in the traveller's language.
    travel_tip_codes: list[Any] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
