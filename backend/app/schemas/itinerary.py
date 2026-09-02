"""Itinerary schemas."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from app.schemas.common import JourneyMeshModel

TimeSlot = Literal["morning", "afternoon", "evening"]


class Activity(JourneyMeshModel):
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    duration_minutes: Optional[int] = None
    estimated_cost: Optional[float] = None
    currency: Optional[str] = None
    indoor: bool = False
    family_friendly: bool = True
    tags: list[str] = Field(default_factory=list)


class DaySlot(JourneyMeshModel):
    slot: TimeSlot
    activities: list[Activity] = Field(default_factory=list)
    travel_time_minutes: Optional[int] = None
    notes: Optional[str] = None


class ItineraryDay(JourneyMeshModel):
    day: int
    date: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    slots: list[DaySlot] = Field(default_factory=list)
    estimated_day_cost: Optional[float] = None
    weather_note: Optional[str] = None
    rest_note: Optional[str] = None


class ItineraryPlan(JourneyMeshModel):
    destination: Optional[str] = None
    days: list[ItineraryDay] = Field(default_factory=list)
    total_days: int = 0
    pacing: Literal["relaxed", "balanced", "packed"] = "balanced"
    estimated_activity_cost: float = 0.0
    currency: Optional[str] = None
    travel_tips: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
