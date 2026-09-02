"""Travel request/response schemas - the public contract of the API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.core.constants import (
    HOTEL_PREFERENCES,
    INTERESTS,
    SUPPORTED_CURRENCIES,
    TRAVEL_STYLES,
)
from app.schemas.budget import BudgetAnalysis
from app.schemas.common import JourneyMeshModel, LanguageCode, ProviderStatus
from app.schemas.evaluation import EvaluationResult
from app.schemas.flight import FlightResults
from app.schemas.hotel import HotelResults
from app.schemas.itinerary import ItineraryPlan
from app.schemas.review import ReviewRecord, ReviewStatus
from app.schemas.weather import WeatherInfo

MAX_TRAVELERS = 20
MAX_TRIP_DAYS = 60


class TripConstraints(JourneyMeshModel):
    """Normalised planning constraints shared by every agent."""

    origin: str | None = None
    destination: str | None = None
    departure_date: date | None = None
    return_date: date | None = None
    travelers: int = 1
    budget: float | None = None
    currency: str = "USD"
    travel_style: str | None = None
    hotel_preference: str | None = None
    interests: list[str] = Field(default_factory=list)
    special_requirements: str | None = None
    additional_instructions: str | None = None
    response_language: LanguageCode = "en"
    nights: int | None = None
    trip_days: int | None = None
    max_hotel_price_per_night: float | None = None

    @model_validator(mode="after")
    def _derive_duration(self) -> TripConstraints:
        if self.departure_date and self.return_date:
            delta = (self.return_date - self.departure_date).days
            if delta >= 0:
                object.__setattr__(self, "nights", delta)
                object.__setattr__(self, "trip_days", max(delta + 1, 1))
        return self


class TripPlanRequest(JourneyMeshModel):
    """Body of ``POST /api/v1/trips/plan``."""

    query: str = Field(min_length=3, max_length=4000)
    origin: str | None = Field(default=None, max_length=120)
    destination: str | None = Field(default=None, max_length=120)
    departure_date: date | None = None
    return_date: date | None = None
    travelers: int = Field(default=1, ge=1, le=MAX_TRAVELERS)
    budget: float | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", max_length=3)
    travel_style: str | None = None
    hotel_preference: str | None = None
    interests: list[str] = Field(default_factory=list, max_length=len(INTERESTS))
    special_requirements: str | None = Field(default=None, max_length=1000)
    additional_instructions: str | None = Field(default=None, max_length=2000)
    response_language: LanguageCode = "en"
    session_id: str | None = Field(default=None, max_length=64)

    @field_validator("currency")
    @classmethod
    def _known_currency(cls, value: str) -> str:
        upper = value.upper()
        if upper not in SUPPORTED_CURRENCIES:
            raise ValueError(f"currency must be one of {', '.join(SUPPORTED_CURRENCIES)}")
        return upper

    @field_validator("travel_style")
    @classmethod
    def _known_style(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        normalised = value.strip().lower().replace(" ", "_")
        if normalised not in TRAVEL_STYLES:
            raise ValueError(f"travel_style must be one of {', '.join(TRAVEL_STYLES)}")
        return normalised

    @field_validator("hotel_preference")
    @classmethod
    def _known_hotel_preference(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        normalised = value.strip().lower().replace(" ", "_")
        if normalised not in HOTEL_PREFERENCES:
            raise ValueError(f"hotel_preference must be one of {', '.join(HOTEL_PREFERENCES)}")
        return normalised

    @field_validator("interests")
    @classmethod
    def _known_interests(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            normalised = item.strip().lower().replace(" ", "_")
            if normalised not in INTERESTS:
                raise ValueError(f"unsupported interest: {item}")
            if normalised not in cleaned:
                cleaned.append(normalised)
        return cleaned

    @model_validator(mode="after")
    def _semantic_checks(self) -> TripPlanRequest:
        if self.departure_date and self.return_date:
            if self.return_date < self.departure_date:
                raise ValueError("return_date must not be earlier than departure_date")
            if (self.return_date - self.departure_date).days > MAX_TRIP_DAYS:
                raise ValueError(f"trip length must not exceed {MAX_TRIP_DAYS} days")
        if self.origin and self.destination:
            if self.origin.strip().lower() == self.destination.strip().lower():
                raise ValueError("origin and destination must be different")
        return self

    def to_constraints(self) -> TripConstraints:
        return TripConstraints(
            origin=self.origin,
            destination=self.destination,
            departure_date=self.departure_date,
            return_date=self.return_date,
            travelers=self.travelers,
            budget=self.budget,
            currency=self.currency,
            travel_style=self.travel_style,
            hotel_preference=self.hotel_preference,
            interests=list(self.interests),
            special_requirements=self.special_requirements,
            additional_instructions=self.additional_instructions,
            response_language=self.response_language,
        )


class JourneyOverview(JourneyMeshModel):
    title: str
    headline: str | None = None
    origin: str | None = None
    destination: str | None = None
    departure_date: str | None = None
    return_date: str | None = None
    travelers: int = 1
    nights: int | None = None
    travel_style: str | None = None
    language: LanguageCode = "en"


class FinalJourney(JourneyMeshModel):
    """Structured output produced by the Final Response Agent."""

    trip_id: str
    language: LanguageCode = "en"
    overview: JourneyOverview
    flights: FlightResults = Field(default_factory=FlightResults)
    hotels: HotelResults = Field(default_factory=HotelResults)
    weather: WeatherInfo = Field(default_factory=WeatherInfo)
    budget: BudgetAnalysis = Field(default_factory=BudgetAnalysis)
    itinerary: ItineraryPlan = Field(default_factory=ItineraryPlan)
    travel_tips: list[str] = Field(default_factory=list)
    provider_status: list[ProviderStatus] = Field(default_factory=list)
    closing_note: str | None = None


class TripPlanResponse(JourneyMeshModel):
    """Body returned by ``POST /api/v1/trips/plan``."""

    trip_id: str
    session_id: str | None = None
    status: str
    review_status: ReviewStatus = "awaiting_review"
    revision: int = 1
    selected_agents: list[str] = Field(default_factory=list)
    execution_reason: str | None = None
    constraints: TripConstraints = Field(default_factory=TripConstraints)
    flights: FlightResults = Field(default_factory=FlightResults)
    hotels: HotelResults = Field(default_factory=HotelResults)
    weather: WeatherInfo = Field(default_factory=WeatherInfo)
    budget: BudgetAnalysis = Field(default_factory=BudgetAnalysis)
    itinerary: ItineraryPlan = Field(default_factory=ItineraryPlan)
    provider_status: list[ProviderStatus] = Field(default_factory=list)
    evaluation: EvaluationResult | None = None
    guardrails: list[dict[str, Any]] = Field(default_factory=list)
    final_journey: FinalJourney | None = None
    messages: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TripSummary(JourneyMeshModel):
    """Compact row used by the history page."""

    trip_id: str
    session_id: str | None = None
    origin: str | None = None
    destination: str | None = None
    departure_date: date | None = None
    return_date: date | None = None
    travelers: int = 1
    budget: float | None = None
    currency: str = "USD"
    travel_style: str | None = None
    status: str = "draft"
    review_status: ReviewStatus = "pending"
    revision_count: int = 1
    preferred_language: LanguageCode = "en"
    evaluation_score: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TripListResponse(JourneyMeshModel):
    items: list[TripSummary] = Field(default_factory=list)
    total: int = 0
    limit: int = 20
    offset: int = 0


class TripDetailResponse(TripPlanResponse):
    reviews: list[ReviewRecord] = Field(default_factory=list)


class GuardrailBlockedResponse(JourneyMeshModel):
    trip_id: str | None = None
    status: Literal["blocked"] = "blocked"
    reason_code: str
    message: str
    guidance: str | None = None


class DeleteResponse(JourneyMeshModel):
    trip_id: str
    deleted: bool = True


class HealthResponse(JourneyMeshModel):
    status: str = "ok"
    service: str = "JourneyMesh API"
    app: str = "JourneyMesh"
    tagline: str = "Every journey, intelligently connected."
    version: str = "1.0.0"
    environment: str = "development"
    database: str = "not_configured"
    llm: str = "mock"
    checks: dict[str, Any] = Field(default_factory=dict)
    time: datetime | None = None
