"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.review_service import ReviewService
from app.services.travel_service import TravelService


def db_session() -> Iterator[Session]:
    yield from get_db()


def travel_service(session: Session = Depends(db_session)) -> TravelService:
    return TravelService(session)


def review_service(session: Session = Depends(db_session)) -> ReviewService:
    return ReviewService(session)


def request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def session_header(
    x_journeymesh_session: str | None = Header(default=None),
) -> str | None:
    """Optional client-supplied session identifier used to scope history."""
    return x_journeymesh_session
