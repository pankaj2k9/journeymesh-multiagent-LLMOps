"""Data access for the human-in-the-loop review trail."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import HumanReview


class ReviewRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, trip_id: str, **fields: Any) -> HumanReview:
        review = HumanReview(trip_id=trip_id, **fields)
        self.session.add(review)
        self.session.flush()
        return review

    def list_for_trip(self, trip_id: str) -> list[HumanReview]:
        stmt = (
            select(HumanReview)
            .where(HumanReview.trip_id == trip_id)
            .order_by(HumanReview.revision_number, HumanReview.reviewed_at)
        )
        return list(self.session.scalars(stmt))

    def latest(self, trip_id: str) -> HumanReview | None:
        stmt = (
            select(HumanReview)
            .where(HumanReview.trip_id == trip_id)
            .order_by(HumanReview.revision_number.desc(), HumanReview.reviewed_at.desc())
            .limit(1)
        )
        return self.session.scalar(stmt)

    def max_revision(self, trip_id: str) -> int:
        value = self.session.scalar(
            select(func.max(HumanReview.revision_number)).where(HumanReview.trip_id == trip_id)
        )
        return int(value or 0)
