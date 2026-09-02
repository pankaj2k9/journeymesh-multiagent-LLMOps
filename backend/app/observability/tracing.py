"""Lightweight in-process tracing.

JourneyMesh does not depend on an external tracing backend. Instead every
agent, tool call and provider call is recorded as a span on a context-local
trace, which is then attached to the response and to the audit trail.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from app.observability.logging import get_logger

logger = get_logger("journeymesh.trace")

_request_id: ContextVar[str | None] = ContextVar("journeymesh_request_id", default=None)
_trip_id: ContextVar[str | None] = ContextVar("journeymesh_trip_id", default=None)
_session_id: ContextVar[str | None] = ContextVar("journeymesh_session_id", default=None)
_spans: ContextVar[list[Span] | None] = ContextVar("journeymesh_spans", default=None)


@dataclass
class Span:
    name: str
    kind: str = "internal"
    started_at: float = field(default_factory=time.perf_counter)
    latency_ms: int | None = None
    success: bool = True
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "latency_ms": self.latency_ms,
            "success": self.success,
            **self.attributes,
        }


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def set_request_context(
    *,
    request_id: str | None = None,
    trip_id: str | None = None,
    session_id: str | None = None,
) -> str:
    rid = request_id or new_request_id()
    _request_id.set(rid)
    if trip_id is not None:
        _trip_id.set(trip_id)
    if session_id is not None:
        _session_id.set(session_id)
    if _spans.get() is None:
        _spans.set([])
    return rid


def set_trip_id(trip_id: str) -> None:
    _trip_id.set(trip_id)


def current_context() -> dict[str, str | None]:
    return {
        "request_id": _request_id.get(),
        "trip_id": _trip_id.get(),
        "session_id": _session_id.get(),
    }


def start_trace() -> None:
    _spans.set([])


def collected_spans() -> list[dict[str, Any]]:
    spans = _spans.get() or []
    return [span.to_dict() for span in spans]


def record_span(span: Span) -> None:
    spans = _spans.get()
    if spans is None:
        spans = []
        _spans.set(spans)
    spans.append(span)


@contextmanager
def span(name: str, kind: str = "internal", **attributes: Any) -> Iterator[Span]:
    """Time a unit of work and record it on the current trace."""
    current = Span(name=name, kind=kind, attributes=dict(attributes))
    try:
        yield current
    except Exception as exc:  # noqa: BLE001 - re-raised below
        current.success = False
        current.attributes.setdefault("error", type(exc).__name__)
        raise
    finally:
        current.latency_ms = int((time.perf_counter() - current.started_at) * 1000)
        record_span(current)
        logger.debug(
            "span completed",
            extra={
                "span": current.name,
                "kind": current.kind,
                "latency_ms": current.latency_ms,
                "success": current.success,
                **current_context(),
            },
        )
