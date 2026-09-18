"""Data access for accounts and traveller profiles."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import TravelerProfile, Trip, User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ---- accounts --------------------------------------------------------
    def create(self, **fields: Any) -> User:
        user = User(**fields)
        self.session.add(user)
        self.session.flush()
        return user

    def get(self, user_id: str) -> User | None:
        return self.session.get(User, user_id)

    def by_email(self, email: str) -> User | None:
        """Look up by normalised address.

        The comparison is on the stored value, which the service lower-cases
        before writing, so this stays an index seek rather than a scan over
        ``lower(email)``.
        """
        return self.session.scalar(select(User).where(User.email == email.strip().lower()))

    def touch_login(self, user: User) -> User:
        user.last_login_at = datetime.now(timezone.utc)
        self.session.flush()
        return user

    def update(self, user: User, **fields: Any) -> User:
        for key, value in fields.items():
            setattr(user, key, value)
        user.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return user

    def count(self) -> int:
        return int(self.session.scalar(select(func.count(User.id))) or 0)

    def list(self, *, limit: int = 50, offset: int = 0, role: str | None = None) -> list[User]:
        stmt = select(User)
        if role:
            stmt = stmt.where(User.role == role)
        stmt = stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    # ---- session adoption ------------------------------------------------
    def claim_session_trips(self, user_id: str, session_id: str) -> int:
        """Move anonymous trips from a browser session onto an account.

        Only unowned trips move. A trip that already belongs to someone is left
        alone, so knowing a session id can never transfer another account's
        journey.
        """
        trips = list(
            self.session.scalars(
                select(Trip).where(Trip.session_id == session_id, Trip.user_id.is_(None))
            )
        )
        for trip in trips:
            trip.user_id = user_id
        self.session.flush()
        return len(trips)

    # ---- traveller profiles ---------------------------------------------
    def add_traveler(self, user_id: str, **fields: Any) -> TravelerProfile:
        profile = TravelerProfile(user_id=user_id, **fields)
        self.session.add(profile)
        self.session.flush()
        return profile

    def travelers(self, user_id: str) -> list[TravelerProfile]:
        return list(
            self.session.scalars(
                select(TravelerProfile)
                .where(TravelerProfile.user_id == user_id)
                .order_by(TravelerProfile.created_at)
            )
        )

    def get_traveler(self, user_id: str, traveler_id: str) -> TravelerProfile | None:
        return self.session.scalar(
            select(TravelerProfile).where(
                TravelerProfile.id == traveler_id, TravelerProfile.user_id == user_id
            )
        )

    def delete_traveler(self, profile: TravelerProfile) -> None:
        self.session.delete(profile)
        self.session.flush()
