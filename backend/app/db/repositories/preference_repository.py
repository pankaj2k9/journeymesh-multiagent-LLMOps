"""Data access for a trip's structured search brief."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import TripPreference


class PreferenceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, trip_id: str) -> TripPreference | None:
        return self.session.scalar(
            select(TripPreference).where(TripPreference.trip_id == trip_id)
        )

    def upsert(self, trip_id: str, **fields: Any) -> TripPreference:
        record = self.get(trip_id)
        if record is None:
            record = TripPreference(trip_id=trip_id, **fields)
            self.session.add(record)
        else:
            for key, value in fields.items():
                setattr(record, key, value)
            record.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return record
