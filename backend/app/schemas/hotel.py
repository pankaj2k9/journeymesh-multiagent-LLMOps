"""Hotel schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from app.schemas.common import DataSource, JourneyMeshModel, Provenance


class HotelOption(JourneyMeshModel):
    name: str
    area: Optional[str] = None
    category: Optional[str] = None
    rating: Optional[float] = None
    review_summary: Optional[str] = None
    price_per_night: Optional[float] = None
    currency: Optional[str] = None
    price_source: DataSource = "ESTIMATE"
    amenities: list[str] = Field(default_factory=list)
    family_friendly: bool = False
    distance_to_centre_km: Optional[float] = None
    why_recommended: Optional[str] = None
    reference_url: Optional[str] = None
    provenance: Provenance = Field(default_factory=Provenance)


class HotelResults(JourneyMeshModel):
    destination: Optional[str] = None
    nights: Optional[int] = None
    price_ceiling_per_night: Optional[float] = None
    options: list[HotelOption] = Field(default_factory=list)
    recommended_index: int = 0
    currency: Optional[str] = None
    source: DataSource = "UNAVAILABLE"
    notes: list[str] = Field(default_factory=list)

    @property
    def recommended(self) -> Optional[HotelOption]:
        if not self.options:
            return None
        index = min(self.recommended_index, len(self.options) - 1)
        return self.options[index]
