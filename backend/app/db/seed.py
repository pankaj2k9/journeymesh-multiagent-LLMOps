"""Start-up seed: the administrator, an optional demo traveller, attractions.

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

import json
from pathlib import Path
from typing import Any

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import ROLE_ADMIN, ROLE_USER, USER_ACTIVE
from app.db.database import session_scope
from app.db.models import Attraction, MediaAsset
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


# ---- attractions -------------------------------------------------------------

SEED_DATA = Path(__file__).parent / "seed_data"

# Any fixed number, shared by every worker: whoever holds it seeds, the others
# wait and then find nothing left to do.
_ATTRACTIONS_LOCK = 7_310_201


def _serialise(session: Session) -> None:
    """Take a transaction-scoped lock on PostgreSQL; a no-op elsewhere."""
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _ATTRACTIONS_LOCK})


def seed_attractions(records: list[dict[str, Any]] | None = None) -> dict[str, int]:
    """Insert the bundled attractions and attach their photographs.

    Insert-only: a row that exists is never touched, so an administrator's
    edits survive - including removing a photograph. One transaction, so an
    interrupted first boot leaves nothing half-seeded for the next to trip on.
    """
    from app.services.media_service import MediaService

    if records is None:
        records = json.loads((SEED_DATA / "attractions.json").read_text(encoding="utf-8"))

    counts = {"created": 0, "images": 0}
    with session_scope() as session:
        _serialise(session)
        existing = {row.slug: row for row in session.scalars(select(Attraction))}
        media = MediaService(session)

        for record in records:
            row = existing.get(record["slug"])
            if row is None:
                image = record.get("image") or {}
                row = Attraction(
                    slug=record["slug"],
                    name=record["name"],
                    city=record["city"],
                    country=record["country"],
                    description=record.get("description", ""),
                    summary=record.get("summary", ""),
                    sort_order=record.get("sort_order", 0),
                    wikipedia_url=record.get("wikipedia_url", ""),
                    image_author=image.get("author", ""),
                    image_license=image.get("license", ""),
                    image_license_url=image.get("license_url", ""),
                    image_source_url=image.get("source_url", ""),
                )
                session.add(row)
                counts["created"] += 1

                path = SEED_DATA / "attractions" / (record.get("image") or {}).get("file", "")
                if path.is_file():
                    asset = media.upload(
                        path.read_bytes(),
                        original_filename=path.name,
                        category="destinations",
                        declared_type="image/jpeg",
                        alt_text=record["name"],
                        title=record["name"],
                    )
                    row.image_media_id = asset.id
                    session.get(MediaAsset, asset.id).usage_count = 1
                    counts["images"] += 1

    if counts["created"] or counts["images"]:
        # Prefixed: `created` is a reserved LogRecord attribute and would raise.
        logger.info(
            "attractions seeded",
            extra={"attractions_created": counts["created"], "photos_attached": counts["images"]},
        )
    return counts


if __name__ == "__main__":  # pragma: no cover - manual entry point
    from app.db.database import init_db

    init_db()
    print(f"admin seed: {seed_admin()}")
    print(f"demo user seed: {seed_demo_user()}")
    print(f"attractions seed: {seed_attractions()}")
