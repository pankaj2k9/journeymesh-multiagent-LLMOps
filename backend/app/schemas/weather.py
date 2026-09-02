"""Weather schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import DataSource, JourneyMeshModel


class DailyForecast(JourneyMeshModel):
    date: str
    condition: str | None = None
    temp_min_c: float | None = None
    temp_max_c: float | None = None
    humidity_pct: float | None = None
    precipitation_chance_pct: float | None = None


class CurrentWeather(JourneyMeshModel):
    temperature_c: float | None = None
    feels_like_c: float | None = None
    condition: str | None = None
    humidity_pct: float | None = None
    wind_kph: float | None = None


class WeatherInfo(JourneyMeshModel):
    location: str | None = None
    current: CurrentWeather | None = None
    forecast: list[DailyForecast] = Field(default_factory=list)
    packing_recommendations: list[str] = Field(default_factory=list)
    travel_suggestions: list[str] = Field(default_factory=list)
    # Phrase codes for the same advice, rendered by the Final Response Agent
    # in the traveller's language. See app/core/i18n.py.
    packing_codes: list[Any] = Field(default_factory=list)
    suggestion_codes: list[Any] = Field(default_factory=list)
    source: DataSource = "UNAVAILABLE"
    provider: str | None = None
    retrieved_at: datetime | None = None
    notes: list[str] = Field(default_factory=list)
