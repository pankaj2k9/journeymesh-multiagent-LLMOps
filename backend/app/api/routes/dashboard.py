"""The traveller dashboard endpoint."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import db_session, optional_user, session_header
from app.db.models import User
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/me", tags=["dashboard"])


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Everything the traveller dashboard shows",
    description=(
        "One aggregate rather than eight requests. Signed in, it returns that "
        "account's journeys; signed out, it returns the ones planned in this browser "
        "session, so anonymous planning still has a home screen. Budget and "
        "arrangement progress come from the services that own them, never from a "
        "second implementation."
    ),
)
def dashboard(
    limit: int = Query(default=50, ge=1, le=100),
    today: date | None = Query(default=None),
    session: Session = Depends(db_session),
    user: User | None = Depends(optional_user),
    session_id: str | None = Depends(session_header),
) -> DashboardResponse:
    return DashboardService(session).build(
        user=user, session_id=session_id, today=today, limit=limit
    )
