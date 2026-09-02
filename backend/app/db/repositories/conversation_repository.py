"""Data access for conversation messages and audit events."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, ConversationMessage


class ConversationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_message(
        self,
        *,
        trip_id: str,
        role: str,
        content: str,
        agent: Optional[str] = None,
        session_id: Optional[str] = None,
        revision_number: int = 1,
    ) -> ConversationMessage:
        message = ConversationMessage(
            trip_id=trip_id,
            role=role,
            content=content,
            agent=agent,
            session_id=session_id,
            revision_number=revision_number,
        )
        self.session.add(message)
        self.session.flush()
        return message

    def list_for_trip(self, trip_id: str) -> list[ConversationMessage]:
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.trip_id == trip_id)
            .order_by(ConversationMessage.created_at)
        )
        return list(self.session.scalars(stmt))


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        *,
        event_type: str,
        severity: str = "info",
        trip_id: Optional[str] = None,
        request_id: Optional[str] = None,
        actor: Optional[str] = None,
        detail: Optional[dict[str, Any]] = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            trip_id=trip_id,
            request_id=request_id,
            actor=actor,
            detail=detail or {},
        )
        self.session.add(event)
        self.session.flush()
        return event

    def list_for_trip(self, trip_id: str) -> list[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.trip_id == trip_id)
            .order_by(AuditEvent.created_at)
        )
        return list(self.session.scalars(stmt))
