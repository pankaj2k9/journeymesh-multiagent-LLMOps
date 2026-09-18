"""Account endpoints.

Anonymous use is unchanged by anything here: an account is what makes a trip
ownable, which matters once money, bookings and an admin view exist, and is
optional before that.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import auth_service, current_user
from app.db.models import User
from app.schemas.auth import (
    AuthResponse,
    ClaimSessionRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TravelerListResponse,
    TravelerProfileIn,
    TravelerProfileOut,
    UserOut,
)
from app.services.auth_service import AuthService, user_out

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
    description=(
        "Creates an account and signs it in. When a `session_id` is supplied, the "
        "journeys already planned anonymously in that browser session are adopted by "
        "the new account, so signing up never loses work."
    ),
)
def register(
    payload: RegisterRequest,
    service: AuthService = Depends(auth_service),
) -> AuthResponse:
    return service.register(payload)


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Sign in",
    description=(
        "Returns a short-lived access token and a longer-lived refresh token. An "
        "unknown address and a wrong password give the same answer on purpose."
    ),
)
def login(
    payload: LoginRequest,
    service: AuthService = Depends(auth_service),
) -> AuthResponse:
    return service.login(payload)


@router.post(
    "/refresh",
    response_model=AuthResponse,
    summary="Exchange a refresh token for a new pair",
)
def refresh(
    payload: RefreshRequest,
    service: AuthService = Depends(auth_service),
) -> AuthResponse:
    return service.refresh(payload.refresh_token)


@router.get("/me", response_model=UserOut, summary="The signed-in account")
def me(user: User = Depends(current_user)) -> UserOut:
    return user_out(user)


@router.post(
    "/sign-out-everywhere",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Invalidate every token issued to this account",
)
def sign_out_everywhere(
    user: User = Depends(current_user),
    service: AuthService = Depends(auth_service),
) -> None:
    service.sign_out_everywhere(user)


@router.post(
    "/claim-session",
    summary="Adopt the journeys planned anonymously in a browser session",
)
def claim_session(
    payload: ClaimSessionRequest,
    user: User = Depends(current_user),
    service: AuthService = Depends(auth_service),
) -> dict[str, int]:
    return {"claimed_trips": service.claim_session(user, payload.session_id)}


@router.get(
    "/travelers",
    response_model=TravelerListResponse,
    summary="Saved traveller profiles",
)
def list_travelers(
    user: User = Depends(current_user),
    service: AuthService = Depends(auth_service),
) -> TravelerListResponse:
    items = service.travelers(user)
    return TravelerListResponse(items=items, total=len(items))


@router.post(
    "/travelers",
    response_model=TravelerProfileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Save a traveller profile",
)
def add_traveler(
    payload: TravelerProfileIn,
    user: User = Depends(current_user),
    service: AuthService = Depends(auth_service),
) -> TravelerProfileOut:
    return service.add_traveler(user, payload)
