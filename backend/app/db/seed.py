"""Start-up seed: the administrator account and an optional demo traveller.

Idempotent by design, because it runs on every start of every worker.

The administrator (``ADMIN_EMAIL``/``ADMIN_PASSWORD``):

  * not configured          -> nothing happens;
  * the address is unknown  -> the account is created as ADMIN;
  * the address exists      -> it is promoted to ADMIN and reactivated, and its
                               password is left alone.

The demo traveller (``DEMO_USER_EMAIL``/``DEMO_USER_PASSWORD``) is created as
an ordinary USER when unknown and otherwise left entirely alone - an admin who
suspended it must not see it reactivated by the next deploy.

Leaving passwords alone is deliberate: someone who changed theirs after the
first start must not have it silently reset by the next deploy.

Run by hand with ``python -m app.db.seed``.
"""

from __future__ import annotations

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.constants import ROLE_ADMIN, ROLE_USER, USER_ACTIVE
from app.db.database import session_scope
from app.db.repositories import UserRepository
from app.observability.logging import get_logger
from app.security import auth

logger = get_logger("journeymesh.db.seed")

# Values in the example files. Seeding one of them in production is allowed -
# it may be a first boot - but it is worth a loud line in the log.
_PLACEHOLDER_MARKERS = ("change-me", "changeme", "dummy")


def _seed_account(
    *,
    label: str,
    email: str | None,
    password: str | None,
    display_name: str,
    role: str,
    promote_existing: bool,
) -> str:
    settings = get_settings()
    email = (email or "").strip().lower()
    password = password or ""

    if not email or not password:
        return "skipped"

    # The sign-in form validates with EmailStr, which refuses special-use
    # domains such as `.local`; an account it cannot sign in to is no use.
    try:
        TypeAdapter(EmailStr).validate_python(email)
    except ValidationError:
        logger.error(f"{label}_EMAIL is not a valid sign-in address; it was not seeded")
        return "rejected"

    if len(password) < settings.password_min_length:
        logger.error(
            f"{label}_PASSWORD is shorter than the minimum; it was not seeded",
            extra={"minimum": settings.password_min_length},
        )
        return "rejected"

    if settings.is_production and any(m in password.lower() for m in _PLACEHOLDER_MARKERS):
        logger.warning(f"{label}_PASSWORD looks like a placeholder; change it after signing in")

    with session_scope() as session:
        users = UserRepository(session)
        existing = users.by_email(email)

        if existing is not None:
            if not promote_existing or (existing.role == role and existing.status == USER_ACTIVE):
                return "unchanged"
            users.update(existing, role=role, status=USER_ACTIVE)
            logger.info(f"existing account promoted to {role}", extra={"email": email})
            return "promoted"

        try:
            users.create(
                email=email,
                password_hash=auth.hash_password(password),
                display_name=display_name.strip() or None,
                role=role,
                status=USER_ACTIVE,
            )
        except IntegrityError:
            # Another worker seeded the same address a moment earlier.
            session.rollback()
            return "unchanged"

    logger.info(f"{role.lower()} account created", extra={"email": email})
    return "created"


def seed_admin() -> str:
    """Ensure the configured administrator exists. Returns what it did."""
    settings = get_settings()
    return _seed_account(
        label="ADMIN",
        email=settings.admin_email,
        password=settings.admin_password,
        display_name=settings.admin_display_name,
        role=ROLE_ADMIN,
        promote_existing=True,
    )


def seed_demo_user() -> str:
    """Ensure the configured demo traveller exists. Returns what it did.

    Run after `seed_admin`, so on a fresh database the administrator is still
    the first account.
    """
    settings = get_settings()
    return _seed_account(
        label="DEMO_USER",
        email=settings.demo_user_email,
        password=settings.demo_user_password,
        display_name=settings.demo_user_display_name,
        role=ROLE_USER,
        promote_existing=False,
    )


if __name__ == "__main__":  # pragma: no cover - manual entry point
    from app.db.database import init_db

    init_db()
    print(f"admin seed: {seed_admin()}")
    print(f"demo user seed: {seed_demo_user()}")
