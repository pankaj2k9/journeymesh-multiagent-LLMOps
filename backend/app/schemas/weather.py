"""Weather schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import Field

from app.schemas.common import DataSource, JourneyMeshModel


class DailyForecast(JourneyMeshModel):
    date: str
    condition: Optional[str] = None
    temp_min_c: Optional[float] = None
    temp_max_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    precipitation_chance_pct: Optional[float] = None


class CurrentWeather(JourneyMeshModel):
    temperature_c: Optional[float] = None
    feels_like_c: Optional[float] = None
    condition: Optional[str] = None
    humidity_pct: Optional[float] = None
    wind_kph: Optional[float] = None


class WeatherInfo(JourneyMeshModel):
    location: Optional[str] = None
    current: Optional[CurrentWeather] = None
    forecast: list[DailyForecast] = Field(default_factory=list)
    packing_recommendations: list[str] = Field(default_factory=list)
    travel_suggestions: list[str] = Field(default_factory=list)
    source: DataSource = "UNAVAILABLE"
    provider: Optional[str] = None
    retrieved_at: Optional[datetime] = None
    notes: list[str] = Field(default_factory=list)
