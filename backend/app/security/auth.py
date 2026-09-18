"""Password hashing and token minting.

Two responsibilities, both deliberately narrow:

  * hash and verify passwords with Argon2id, and say when a stored hash needs
    re-hashing because the parameters have moved on;
  * mint and read JSON Web Tokens for the access/refresh pair.

There is no session table and no token blocklist. Instead every token carries
the user's ``token_version``, and bumping that column on the user row
invalidates every token issued before it - one integer instead of a store that
has to be swept. Logout is therefore client-side by default, and
"sign out everywhere" is a version bump.

This module knows nothing about HTTP or the database. ``AuthService`` does.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

TokenType = Literal["access", "refresh"]

ACCESS = "access"
REFRESH = "refresh"

# OWASP's second recommended Argon2id configuration (19 MiB, t=2, p=1). It is
# the cheapest of the recommended sets, which matters because this application
# is expected to run on a single small VPS where a login must not evict the
# page cache.
_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=19 * 1024,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)


class TokenError(Exception):
    """A token was absent, malformed, expired or not the type expected."""


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    """Check a password against a stored hash.

    Every failure mode returns ``False`` rather than raising, so a corrupted
    hash in the database reads as a failed login rather than a 500 that tells
    an attacker their guess was interesting.
    """
    try:
        return _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    """Whether this hash was made with weaker parameters than current."""
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return True


# A constant-time-ish dummy verification, run when no account matches, so that
# "unknown email" and "wrong password" take comparable time and the login
# endpoint does not become a user-enumeration oracle.
_DUMMY_HASH = _hasher.hash("travel-crew-ai-timing-equaliser")


def burn_time() -> None:
    """Spend roughly one verification's worth of time on nothing."""
    try:
        _hasher.verify(_DUMMY_HASH, "not-the-password")
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        pass


@dataclass(frozen=True)
class TokenClaims:
    """What a validated token asserts."""

    subject: str
    token_type: TokenType
    role: str
    token_version: int
    expires_at: datetime

    @property
    def user_id(self) -> str:
        return self.subject


def _ttl(token_type: TokenType) -> timedelta:
    settings = get_settings()
    if token_type == REFRESH:
        return timedelta(days=settings.refresh_token_ttl_days)
    return timedelta(minutes=settings.access_token_ttl_minutes)


def create_token(
    *,
    user_id: str,
    role: str,
    token_version: int,
    token_type: TokenType = ACCESS,
    issued_at: datetime | None = None,
) -> str:
    settings = get_settings()
    now = issued_at or datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "typ": token_type,
        "role": role,
        "ver": token_version,
        "iat": int(now.timestamp()),
        "exp": int((now + _ttl(token_type)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_signing_key, algorithm=settings.jwt_algorithm)


def read_token(token: str, *, expected_type: TokenType = ACCESS) -> TokenClaims:
    """Validate a token's signature, expiry and type, or raise ``TokenError``.

    The type check is the point of this function. Without it a refresh token -
    which is long-lived by design - would be accepted as an access token, and a
    fourteen-day credential would sit in front of every endpoint.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_signing_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("token_invalid") from exc

    if payload.get("typ") != expected_type:
        raise TokenError("token_wrong_type")

    return TokenClaims(
        subject=str(payload["sub"]),
        token_type=expected_type,
        role=str(payload.get("role") or "USER"),
        token_version=int(payload.get("ver") or 1),
        expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc),
    )


def bearer_token(header_value: str | None) -> str | None:
    """Pull the credential out of an ``Authorization: Bearer <token>`` header."""
    if not header_value:
        return None
    scheme, _, token = header_value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()
