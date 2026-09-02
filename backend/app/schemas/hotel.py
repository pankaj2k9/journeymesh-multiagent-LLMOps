"""Hotel schemas."""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import DataSource, JourneyMeshModel, Provenance


class HotelOption(JourneyMeshModel):
    name: str
    area: str | None = None
    category: str | None = None
    rating: float | None = None
    review_summary: str | None = None
    price_per_night: float | None = None
    currency: str | None = None
    price_source: DataSource = "ESTIMATE"
    amenities: list[str] = Field(default_factory=list)
    family_friendly: bool = False
    distance_to_centre_km: float | None = None
    why_recommended: str | None = None
    reference_url: str | None = None
    provenance: Provenance = Field(default_factory=Provenance)


class HotelResults(JourneyMeshModel):
    destination: str | None = None
    nights: int | None = None
    price_ceiling_per_night: float | None = None
    options: list[HotelOption] = Field(default_factory=list)
    recommended_index: int = 0
    currency: str | None = None
    source: DataSource = "UNAVAILABLE"
    notes: list[str] = Field(default_factory=list)

    @property
    def recommended(self) -> HotelOption | None:
        if not self.options:
            return None
        index = min(self.recommended_index, len(self.options) - 1)
        return self.options[index]
