"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Callable, Iterator

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.constants import EVENT_FORBIDDEN, ROLE_RANK, USER_ACTIVE
from app.core.exceptions import (
    AccountSuspended,
    AuthenticationRequired,
    PermissionDenied,
)
from app.db.database import get_db
from app.db.models import User
from app.db.repositories import UserRepository
from app.security import audit, auth
from app.services.auth_service import AuthService
from app.services.budget_engine import BudgetEngine
from app.services.review_service import ReviewService
from app.services.travel_service import TravelService


def db_session() -> Iterator[Session]:
    yield from get_db()


def travel_service(session: Session = Depends(db_session)) -> TravelService:
    return TravelService(session)


def review_service(session: Session = Depends(db_session)) -> ReviewService:
    return ReviewService(session)


def auth_service(session: Session = Depends(db_session)) -> AuthService:
    return AuthService(session)


def budget_engine(session: Session = Depends(db_session)) -> BudgetEngine:
    return BudgetEngine(session)


def request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def session_header(
    x_journeymesh_session: str | None = Header(default=None),
) -> str | None:
    """Optional client-supplied session identifier used to scope history."""
    return x_journeymesh_session


# ---- identity -----------------------------------------------------------
def optional_user(
    authorization: str | None = Header(default=None),
    session: Session = Depends(db_session),
) -> User | None:
    """The signed-in account, or None.

    Anonymous planning is still a supported way to use this application, so
    most endpoints take this rather than ``current_user``. A malformed or
    expired token is treated as "not signed in" here; endpoints that actually
    require an account get the 401 from ``current_user`` instead.
    """
    token = auth.bearer_token(authorization)
    if not token:
        return None
    try:
        claims = auth.read_token(token, expected_type=auth.ACCESS)
    except auth.TokenError:
        return None

    user = UserRepository(session).get(claims.user_id)
    if user is None:
        return None
    # A password change or a forced sign-out bumps this, stranding older tokens
    # without a blocklist to sweep.
    if claims.token_version != user.token_version:
        return None
    if user.status != USER_ACTIVE:
        return None
    return user


def current_user(user: User | None = Depends(optional_user)) -> User:
    """The signed-in account. 401 when there is none."""
    if user is None:
        raise AuthenticationRequired()
    if user.status != USER_ACTIVE:
        raise AccountSuspended()
    return user


def require_role(minimum: str) -> Callable[..., User]:
    """Dependency factory gating an endpoint on a minimum role.

    Roles are ranked rather than matched, so an ADMIN satisfies a SUPPORT
    requirement without every admin route having to list both. A refusal is
    audited: an account probing an endpoint above its level is worth seeing.
    """

    def _dependency(
        user: User = Depends(current_user),
        session: Session = Depends(db_session),
    ) -> User:
        if ROLE_RANK.get(user.role, -1) < ROLE_RANK.get(minimum, 99):
            audit.record(
                EVENT_FORBIDDEN,
                detail={"required_role": minimum, "actual_role": user.role},
                actor=user.id,
                session=session,
            )
            raise PermissionDenied()
        return user

    return _dependency
