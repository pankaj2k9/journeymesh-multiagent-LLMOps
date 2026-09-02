"""Conversation persistence.

Only safe execution summaries and the traveller's own (redacted) turns are
stored. Model reasoning is never written here.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.repositories import ConversationRepository
from app.graph.state import TravelState
from app.observability.logging import get_logger

logger = get_logger("journeymesh.services.conversation")

_STORED_ROLES = {"user", "agent", "supervisor", "system"}


class ConversationService:
    def __init__(self, session: Session) -> None:
        self.repo = ConversationRepository(session)

    def persist_state_messages(self, state: TravelState) -> int:
        """Write any message on the state that is not yet stored."""
        trip_id = state.get("trip_id")
        if not trip_id:
            return 0

        existing = {
            (message.role, message.content, message.revision_number)
            for message in self.repo.list_for_trip(trip_id)
        }
        written = 0
        for message in state.get("messages") or []:
            role = message.get("role", "system")
            if role not in _STORED_ROLES:
                continue
            key = (role, message.get("content", ""), int(message.get("revision", 1)))
            if key in existing:
                continue
            self.repo.add_message(
                trip_id=trip_id,
                role=role,
                content=message.get("content", ""),
                agent=message.get("agent"),
                session_id=state.get("session_id"),
                revision_number=int(message.get("revision", 1)),
            )
            existing.add(key)
            written += 1
        return written

    def history(self, trip_id: str) -> list[dict[str, Any]]:
        return [
            {
                "role": message.role,
                "agent": message.agent,
                "content": message.content,
                "revision": message.revision_number,
                "at": message.created_at.isoformat() if message.created_at else None,
            }
            for message in self.repo.list_for_trip(trip_id)
        ]

    def add(
        self,
        *,
        trip_id: str,
        role: str,
        content: str,
        agent: str | None = None,
        revision_number: int = 1,
        session_id: str | None = None,
    ) -> None:
        self.repo.add_message(
            trip_id=trip_id,
            role=role,
            content=content,
            agent=agent,
            revision_number=revision_number,
            session_id=session_id,
        )
