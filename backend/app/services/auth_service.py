"""Registration, sign-in and account reads.

The rules that are easy to get wrong and are therefore enforced here rather
than at the route:

  * an unknown email and a wrong password are the same answer, and take
    roughly the same time, so this endpoint is not a user-enumeration oracle;
  * a role is never taken from a request body - the first account may become
    an administrator by configuration, and nothing else promotes anyone;
  * signing in adopts the browser session's anonymous trips, but only the ones
    that belong to nobody, so a guessed session id transfers nothing.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import (
    EVENT_SESSION_CLAIMED,
    EVENT_USER_LOGIN,
    EVENT_USER_LOGIN_FAILED,
    EVENT_USER_REGISTERED,
    ROLE_ADMIN,
    ROLE_USER,
    USER_ACTIVE,
)
from app.core.exceptions import (
    AccountSuspended,
    AuthenticationRequired,
    EmailAlreadyRegistered,
    InvalidCredentials,
    RegistrationDisabled,
)
from app.db.models import User
from app.db.repositories import UserRepository
from app.observability import metrics
from app.observability.logging import get_logger
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    TravelerProfileIn,
    TravelerProfileOut,
    UserOut,
)
from app.security import audit, auth

logger = get_logger("journeymesh.services.auth")


class AuthService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)

    # ---- registration ----------------------------------------------------
    def register(self, request: RegisterRequest) -> AuthResponse:
        settings = get_settings()
        if not settings.registration_enabled:
            raise RegistrationDisabled()

        email = _normalise_email(request.email)
        if self.users.by_email(email) is not None:
            raise EmailAlreadyRegistered()

        # The very first account on a fresh deployment becomes the
        # administrator. Every later one is an ordinary user, and promotion is
        # an administrative action rather than something a signup can ask for.
        role = ROLE_ADMIN if self.users.count() == 0 else ROLE_USER

        try:
            user = self.users.create(
                email=email,
                password_hash=auth.hash_password(request.password),
                display_name=(request.display_name or "").strip() or None,
                role=role,
                status=USER_ACTIVE,
                preferred_language=request.preferred_language,
                preferred_currency=request.preferred_currency,
            )
        except IntegrityError as exc:
            # Two registrations for one address raced; the unique index won.
            self.session.rollback()
            raise EmailAlreadyRegistered() from exc

        claimed = self._claim(user, request.session_id)
        audit.record(
            EVENT_USER_REGISTERED,
            detail={"role": role, "claimed_trips": claimed},
            actor=user.id,
            session=self.session,
        )
        metrics.increment("auth.registered", role=role)
        return self._issue(user, claimed_trips=claimed)

    # ---- sign in ---------------------------------------------------------
    def login(self, request: LoginRequest) -> AuthResponse:
        email = _normalise_email(request.email)
        user = self.users.by_email(email)

        if user is None:
            # Spend a verification's worth of time anyway, so the response time
            # does not reveal whether the address exists.
            auth.burn_time()
            self._record_failure(reason="unknown_email")
            raise InvalidCredentials()

        if not auth.verify_password(request.password, user.password_hash):
            self._record_failure(reason="bad_password", actor=user.id)
            raise InvalidCredentials()

        if user.status != USER_ACTIVE:
            raise AccountSuspended()

        # Argon2's parameters may have been raised since this hash was made.
        if auth.needs_rehash(user.password_hash):
            user.password_hash = auth.hash_password(request.password)
            self.session.flush()

        self.users.touch_login(user)
        claimed = self._claim(user, request.session_id)
        audit.record(
            EVENT_USER_LOGIN,
            detail={"claimed_trips": claimed},
            actor=user.id,
            session=self.session,
        )
        metrics.increment("auth.login")
        return self._issue(user, claimed_trips=claimed)

    # ---- refresh ---------------------------------------------------------
    def refresh(self, refresh_token: str) -> AuthResponse:
        try:
            claims = auth.read_token(refresh_token, expected_type=auth.REFRESH)
        except auth.TokenError as exc:
            raise AuthenticationRequired(str(exc)) from exc

        user = self.users.get(claims.user_id)
        if user is None or user.status != USER_ACTIVE:
            raise AuthenticationRequired("account_unavailable")

        # The version check is what makes "sign out everywhere" possible with
        # no token store: bumping the column strands every token minted before.
        if claims.token_version != user.token_version:
            raise AuthenticationRequired("token_revoked")

        metrics.increment("auth.refreshed")
        return self._issue(user, claimed_trips=0)

    def sign_out_everywhere(self, user: User) -> None:
        self.users.update(user, token_version=user.token_version + 1)

    # ---- session adoption ------------------------------------------------
    def claim_session(self, user: User, session_id: str) -> int:
        return self._claim(user, session_id)

    def _claim(self, user: User, session_id: str | None) -> int:
        if not session_id:
            return 0
        count = self.users.claim_session_trips(user.id, session_id)
        if count:
            audit.record(
                EVENT_SESSION_CLAIMED,
                detail={"trips": count},
                actor=user.id,
                session=self.session,
            )
        return count

    # ---- traveller profiles ---------------------------------------------
    def add_traveler(self, user: User, payload: TravelerProfileIn) -> TravelerProfileOut:
        profile = self.users.add_traveler(
            user.id,
            full_name=payload.full_name,
            traveler_type=payload.traveler_type,
            date_of_birth=_as_date(payload.date_of_birth),
            passport_country=(payload.passport_country or "").upper() or None,
            dietary_requirements=payload.dietary_requirements,
            accessibility_requirements=payload.accessibility_requirements,
        )
        return _traveler_out(profile)

    def travelers(self, user: User) -> list[TravelerProfileOut]:
        return [_traveler_out(profile) for profile in self.users.travelers(user.id)]

    # ---- internals -------------------------------------------------------
    def _record_failure(self, *, reason: str, actor: str | None = None) -> None:
        audit.record(
            EVENT_USER_LOGIN_FAILED,
            detail={"reason": reason},
            actor=actor,
            session=self.session,
        )
        metrics.increment("auth.login_failed", reason=reason)

    def _issue(self, user: User, *, claimed_trips: int) -> AuthResponse:
        settings = get_settings()
        common: dict[str, Any] = {
            "user_id": user.id,
            "role": user.role,
            "token_version": user.token_version,
        }
        return AuthResponse(
            access_token=auth.create_token(token_type=auth.ACCESS, **common),
            refresh_token=auth.create_token(token_type=auth.REFRESH, **common),
            expires_in=settings.access_token_ttl_minutes * 60,
            user=user_out(user),
            claimed_trips=claimed_trips,
        )


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        status=user.status,
        preferred_language=user.preferred_language,
        preferred_currency=user.preferred_currency,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


def _traveler_out(profile: Any) -> TravelerProfileOut:
    return TravelerProfileOut(
        id=profile.id,
        full_name=profile.full_name,
        traveler_type=profile.traveler_type,
        date_of_birth=profile.date_of_birth.isoformat() if profile.date_of_birth else None,
        passport_country=profile.passport_country,
        dietary_requirements=profile.dietary_requirements,
        accessibility_requirements=profile.accessibility_requirements,
        created_at=profile.created_at,
    )


def _normalise_email(email: str) -> str:
    return str(email).strip().lower()


def _as_date(value: str | None) -> Any:
    if not value:
        return None
    from datetime import date

    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
