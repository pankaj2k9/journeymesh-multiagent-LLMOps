"""Audit logging.

Audit events are written to the structured log stream always, and to the
``audit_events`` table when a database session is available. Details are
passed through the PII redactor first - the audit trail records *what*
happened, never the traveller's personal data.
"""

from __future__ import annotations

from typing import Any

from app.guardrails import pii_guard
from app.observability.logging import get_logger
from app.observability.tracing import current_context

logger = get_logger("journeymesh.audit")

_SEVERITY = {
    "PROMPT_INJECTION_BLOCKED": "warning",
    "TOOL_CALL_BLOCKED": "warning",
    "INVALID_REQUEST": "info",
    "RATE_LIMIT_EXCEEDED": "warning",
    "OUTPUT_VALIDATION_FAILED": "error",
    "PROVIDER_FAILURE": "warning",
    "PII_REDACTED": "info",
    "HUMAN_REVIEW_APPROVED": "info",
    "HUMAN_REVIEW_CHANGES_REQUESTED": "info",
    "REVISION_LIMIT_REACHED": "warning",
    "TRIP_PLANNED": "info",
    "TRIP_DELETED": "info",
}


def severity_for(event_type: str) -> str:
    return _SEVERITY.get(event_type, "info")


def record(
    event_type: str,
    *,
    detail: dict[str, Any] | None = None,
    trip_id: str | None = None,
    actor: str | None = None,
    session: Any = None,
    link_trip: bool = True,
) -> None:
    """Record one audit event.

    ``link_trip=False`` writes the row without a foreign key to any trip, and
    ignores the ambient trip in the trace context. It exists for the one event
    recorded about a trip that no longer exists: its deletion.
    """
    context = current_context()
    safe_detail, redacted = pii_guard.sanitize_payload(detail or {})
    if redacted:
        safe_detail["_redacted_categories"] = redacted

    severity = severity_for(event_type)
    log = getattr(logger, severity if severity != "error" else "error", logger.info)
    log(
        event_type,
        extra={
            "event_type": event_type,
            "severity": severity,
            "actor": actor,
            "detail": safe_detail,
            **context,
            **({"trip_id": trip_id} if trip_id else {}),
        },
    )

    if session is None:
        return

    try:
        from app.db.repositories import AuditRepository

        # A SAVEPOINT, so that a failed audit insert rolls back only itself.
        # Without it a failure here - a foreign key that no longer resolves,
        # say - leaves the session in a rolled-back state, and the caller's
        # own work is lost at commit even though the `except` below swallowed
        # the error. Auditing must never break a request, and that promise is
        # only true if the failure is contained.
        with session.begin_nested():
            AuditRepository(session).record(
                event_type=event_type,
                severity=severity,
                trip_id=(trip_id or context.get("trip_id")) if link_trip else None,
                request_id=context.get("request_id"),
                actor=actor,
                detail=safe_detail,
            )
    except Exception:  # pragma: no cover - auditing must never break a request
        logger.exception("failed to persist audit event", extra={"event_type": event_type})
