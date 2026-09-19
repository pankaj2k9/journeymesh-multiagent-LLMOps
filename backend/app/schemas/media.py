"""Media library schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.media.storage import CATEGORIES
from app.schemas.common import TravelCrewModel

MediaCategory = Literal["blog", "destinations", "marketing", "users", "trips"]

assert set(CATEGORIES) == set(MediaCategory.__args__)  # type: ignore[attr-defined]


class DerivativeOut(TravelCrewModel):
    path: str
    url: str
    width: int
    height: int


class MediaAssetOut(TravelCrewModel):
    id: str
    relative_path: str
    url: str
    filename: str
    original_filename: str = ""
    category: MediaCategory = "blog"
    mime_type: str = "image/webp"
    file_size: int = 0
    width: int | None = None
    height: int | None = None
    alt_text: str = ""
    title: str | None = None
    # Keyed by size name: thumbnail, small, medium, large.
    derivatives: dict[str, DerivativeOut] = Field(default_factory=dict)
    uploaded_by: str | None = None
    usage_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def in_use(self) -> bool:
        return self.usage_count > 0


class MediaListResponse(TravelCrewModel):
    items: list[MediaAssetOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0


class MediaUpdate(TravelCrewModel):
    """What an administrator may change after an upload.

    The path, the bytes and the dimensions are not editable: they describe a
    file that already exists. Replacing an image is a new upload.
    """

    alt_text: str | None = Field(default=None, max_length=300)
    title: str | None = Field(default=None, max_length=200)
