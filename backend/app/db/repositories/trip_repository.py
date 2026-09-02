"""Data access for trips and their agent results."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import TravelResult, Trip


class TripRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ---- writes ---------------------------------------------------------
    def create(self, **fields: Any) -> Trip:
        trip = Trip(**fields)
        self.session.add(trip)
        self.session.flush()
        return trip

    def update(self, trip: Trip, **fields: Any) -> Trip:
        for key, value in fields.items():
            setattr(trip, key, value)
        trip.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return trip

    def upsert_result(self, trip_id: str, **fields: Any) -> TravelResult:
        result = self.session.scalar(
            select(TravelResult).where(TravelResult.trip_id == trip_id)
        )
        if result is None:
            result = TravelResult(trip_id=trip_id, **fields)
            self.session.add(result)
        else:
            for key, value in fields.items():
                setattr(result, key, value)
            result.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return result

    def delete(self, trip: Trip) -> None:
        self.session.delete(trip)
        self.session.flush()

    # ---- reads ----------------------------------------------------------
    def get(self, trip_id: str) -> Trip | None:
        return self.session.scalar(
            select(Trip)
            .options(
                selectinload(Trip.result),
                selectinload(Trip.reviews),
                selectinload(Trip.messages),
            )
            .where(Trip.id == trip_id)
        )

    def get_result(self, trip_id: str) -> TravelResult | None:
        return self.session.scalar(select(TravelResult).where(TravelResult.trip_id == trip_id))

    def list(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        session_id: str | None = None,
        status: str | None = None,
    ) -> list[Trip]:
        stmt = select(Trip).options(selectinload(Trip.result))
        if session_id:
            stmt = stmt.where(Trip.session_id == session_id)
        if status:
            stmt = stmt.where(Trip.status == status)
        stmt = stmt.order_by(Trip.created_at.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def count(self, *, session_id: str | None = None, status: str | None = None) -> int:
        stmt = select(func.count(Trip.id))
        if session_id:
            stmt = stmt.where(Trip.session_id == session_id)
        if status:
            stmt = stmt.where(Trip.status == status)
        return int(self.session.scalar(stmt) or 0)
