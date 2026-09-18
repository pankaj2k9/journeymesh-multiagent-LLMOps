"""Account and session schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import EmailStr, Field, StringConstraints, field_validator

from app.core.constants import (
    ROLES,
    SUPPORTED_CURRENCIES,
    TRAVELER_TYPES,
    USER_STATUSES,
)
from app.schemas.common import LanguageCode, TravelCrewModel

Role = Literal["USER", "SUPPORT", "ADMIN"]
UserStatus = Literal["active", "suspended"]
TravelerType = Literal["ADULT", "CHILD", "INFANT"]

assert set(ROLES) == set(Role.__args__)  # type: ignore[attr-defined]
assert set(USER_STATUSES) == set(UserStatus.__args__)  # type: ignore[attr-defined]
assert set(TRAVELER_TYPES) == set(TravelerType.__args__)  # type: ignore[attr-defined]

# Long rather than complex. A length floor plus a breached-password check would
# be better still; character-class rules mostly produce "Password1!".
PASSWORD_MAX_LENGTH = 200

# The base model strips whitespace from every string, which is right for a city
# name and wrong for a password: " open sesame " would be stored trimmed, and a
# passphrase built from padded words would be quietly altered. This opts the
# one field out, so what the traveller typed is what is hashed.
Password = Annotated[
    str,
    StringConstraints(strip_whitespace=False, min_length=10, max_length=PASSWORD_MAX_LENGTH),
]


class RegisterRequest(TravelCrewModel):
    email: EmailStr
    password: Password
    display_name: str | None = Field(default=None, max_length=120)
    preferred_language: LanguageCode = "en"
    preferred_currency: str = Field(default="USD", max_length=3)
    # When present, the anonymous trips planned under this browser session are
    # adopted by the new account.
    session_id: str | None = Field(default=None, max_length=64)

    @field_validator("preferred_currency")
    @classmethod
    def _known_currency(cls, value: str) -> str:
        upper = value.upper()
        if upper not in SUPPORTED_CURRENCIES:
            raise ValueError(f"currency must be one of {', '.join(SUPPORTED_CURRENCIES)}")
        return upper

    @field_validator("password")
    @classmethod
    def _not_obviously_weak(cls, value: str) -> str:
        # A length floor alone passes "aaaaaaaaaaaa". Counting distinct
        # characters is a cheap way to refuse the degenerate cases without
        # pretending to be a strength meter.
        if len(set(value)) < 5:
            raise ValueError("password is too repetitive")
        return value


class LoginRequest(TravelCrewModel):
    email: EmailStr
    password: Annotated[
        str, StringConstraints(strip_whitespace=False, min_length=1, max_length=PASSWORD_MAX_LENGTH)
    ]
    session_id: str | None = Field(default=None, max_length=64)


class RefreshRequest(TravelCrewModel):
    refresh_token: str = Field(min_length=10, max_length=4096)


class ClaimSessionRequest(TravelCrewModel):
    session_id: str = Field(min_length=1, max_length=64)


class UserOut(TravelCrewModel):
    id: str
    email: str
    display_name: str | None = None
    role: Role = "USER"
    status: UserStatus = "active"
    preferred_language: LanguageCode = "en"
    preferred_currency: str = "USD"
    last_login_at: datetime | None = None
    created_at: datetime | None = None


class TokenPair(TravelCrewModel):
    """What a successful sign-in returns.

    ``expires_in`` is seconds on the access token, so a client can refresh
    ahead of expiry instead of discovering it through a 401 mid-booking.
    """

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserOut


class AuthResponse(TokenPair):
    """A sign-in or registration, plus what it did to anonymous history."""

    claimed_trips: int = 0


class TravelerProfileIn(TravelCrewModel):
    full_name: str = Field(min_length=1, max_length=160)
    traveler_type: TravelerType = "ADULT"
    date_of_birth: str | None = None
    passport_country: str | None = Field(default=None, max_length=2)
    dietary_requirements: str | None = Field(default=None, max_length=500)
    accessibility_requirements: str | None = Field(default=None, max_length=500)


class TravelerProfileOut(TravelCrewModel):
    id: str
    full_name: str
    traveler_type: TravelerType = "ADULT"
    date_of_birth: str | None = None
    passport_country: str | None = None
    dietary_requirements: str | None = None
    accessibility_requirements: str | None = None
    created_at: datetime | None = None


class TravelerListResponse(TravelCrewModel):
    items: list[TravelerProfileOut] = Field(default_factory=list)
    total: int = 0
