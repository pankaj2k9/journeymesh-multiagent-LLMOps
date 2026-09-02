"""LangSmith integration.

LangSmith is JourneyMesh's AI observability layer: it records the LangGraph
run, the agents, the model calls and the MCP tool calls as one nested trace so
a journey - and every revision of it - can be inspected after the fact.

Three properties matter more than the feature itself:

* **It is optional.** With no API key, or with tracing switched off, every
  function here degrades to a no-op.
* **It never breaks a journey.** Every call into the SDK is wrapped; an
  exception from the tracer is logged once and swallowed. Planning a trip does
  not depend on observability being healthy.
* **It never carries secrets.** Metadata is passed through an allowlist and
  then through the PII redactor before it leaves the process.

Wiring is done in one place - :func:`app.observability.tracing.span` opens a
LangSmith child run for every span JourneyMesh already records - so agents and
tools need no tracing code of their own.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.observability.logging import get_logger

logger = get_logger("journeymesh.langsmith")

# Metadata that may be attached to a trace. Anything not on this list is
# dropped rather than guessed about.
SAFE_METADATA_KEYS = frozenset(
    {
        "trip_id",
        "session_id",
        "request_id",
        "agent",
        "agent_name",
        "selected_agents",
        "change_scope",
        "revision",
        "revision_number",
        "provider",
        "provider_name",
        "tool",
        "tool_name",
        "transport",
        "server",
        "operation",
        "risk",
        "response_language",
        "human_review_status",
        "evaluation_status",
        "evaluation_score",
        "budget_status",
        "destination",
        "origin",
        "travelers",
        "trip_days",
        "source",
        "success",
        "latency_ms",
        "kind",
        "mode",
        "stage",
        "rule",
        "reason_code",
        "blocked",
    }
)

# Keys that must never reach a trace, whatever the caller passes.
BLOCKED_METADATA_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "token",
        "password",
        "secret",
        "database_url",
        "groq_api_key",
        "tavily_api_key",
        "aviationstack_api_key",
        "openweather_api_key",
        "langsmith_api_key",
        "passport",
        "passport_number",
        "national_id",
        "credit_card",
        "card_number",
        "cvv",
        "email",
        "phone",
        "query",
        "user_query",
        "requested_changes",
        "special_requirements",
        "additional_instructions",
    }
)

_MAX_VALUE_LENGTH = 200


@dataclass
class LangSmithStatus:
    """What the tracer is actually doing right now."""

    enabled: bool = False
    configured: bool = False
    sdk_installed: bool = False
    project: str | None = None
    endpoint: str | None = None
    reason: str | None = None
    errors: int = 0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "configured": self.configured,
            "sdk_installed": self.sdk_installed,
            "project": self.project,
            "endpoint": self.endpoint,
            "reason": self.reason,
            "errors": self.errors,
        }


_status = LangSmithStatus()
_configured = False
_warned = False


def _warn_once(message: str, **extra: Any) -> None:
    """Log a tracer failure once, then stay quiet - it must not spam a run."""
    global _warned
    _status.errors += 1
    if not _warned:
        _warned = True
        logger.warning(message, extra=extra)


def _sdk_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("langsmith") is not None


def configure(force: bool = False) -> LangSmithStatus:
    """Prepare LangSmith tracing. Safe to call more than once."""
    global _configured, _status

    if _configured and not force:
        return _status

    settings = get_settings()
    status = LangSmithStatus(
        project=settings.langsmith_project,
        endpoint=settings.langsmith_endpoint,
    )

    try:
        if not settings.langsmith_tracing:
            status.reason = "LANGSMITH_TRACING is not enabled"
        elif not settings.langsmith_api_key:
            status.reason = "LANGSMITH_API_KEY is not configured"
        else:
            status.sdk_installed = _sdk_available()
            if not status.sdk_installed:
                status.reason = "the langsmith package is not installed"
            else:
                # LangChain and LangGraph pick tracing up from the environment,
                # which is what makes the graph traceable without touching any
                # agent. Both spellings are set: older releases read LANGCHAIN_*.
                os.environ["LANGSMITH_TRACING"] = "true"
                os.environ["LANGCHAIN_TRACING_V2"] = "true"
                os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
                os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
                os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
                os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
                os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
                os.environ["LANGCHAIN_ENDPOINT"] = settings.langsmith_endpoint
                status.enabled = True
                status.configured = True
                logger.info(
                    "LangSmith tracing is on",
                    extra={"project": settings.langsmith_project},
                )
    except Exception as exc:  # noqa: BLE001 - observability must never raise
        status.reason = f"configuration failed: {type(exc).__name__}"
        logger.warning("LangSmith configuration failed", extra={"error": str(exc)})

    if not status.enabled:
        # Make sure a stale environment cannot switch tracing on behind our back.
        for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"):
            if os.environ.get(name, "").lower() in {"true", "1", "yes"}:
                os.environ[name] = "false"
        logger.info("LangSmith tracing is off", extra={"reason": status.reason})

    _status = status
    _configured = True
    return _status


def status() -> LangSmithStatus:
    if not _configured:
        configure()
    return _status


def is_enabled() -> bool:
    return status().enabled


def reset() -> None:
    """Forget the cached status. Used by tests."""
    global _configured, _status, _warned
    _configured = False
    _warned = False
    _status = LangSmithStatus()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------
def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only allowlisted, non-sensitive, short metadata values."""
    from app.guardrails import pii_guard  # local import keeps the module light

    if not metadata:
        return {}

    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        lowered = str(key).lower()
        if lowered in BLOCKED_METADATA_KEYS or lowered not in SAFE_METADATA_KEYS:
            continue
        if value is None:
            continue

        if isinstance(value, (list, tuple, set)):
            rendered = ", ".join(str(item) for item in list(value)[:12])
        elif isinstance(value, (bool, int, float)):
            clean[key] = value
            continue
        else:
            rendered = str(value)

        rendered = pii_guard.redact_text(rendered).text
        clean[key] = rendered[:_MAX_VALUE_LENGTH]
    return clean


def run_config(
    *,
    name: str,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    base: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a LangGraph/LangChain config carrying trace identity.

    The values are harmless when tracing is off - LangChain simply ignores
    ``run_name``, ``tags`` and ``metadata`` if no tracer is attached - so the
    caller does not need to branch on whether LangSmith is configured.
    """
    config: dict[str, Any] = dict(base or {})
    config["run_name"] = name

    merged_tags = list(config.get("tags") or [])
    for tag in tags or []:
        if tag and tag not in merged_tags:
            merged_tags.append(str(tag)[:64])
    if merged_tags:
        config["tags"] = merged_tags

    merged_metadata = dict(config.get("metadata") or {})
    merged_metadata.update(sanitize_metadata(metadata))
    if merged_metadata:
        config["metadata"] = merged_metadata
    return config


# ---------------------------------------------------------------------------
# Spans
# ---------------------------------------------------------------------------
def _load_trace() -> Any:
    """Return LangSmith's ``trace`` context manager.

    Isolated in one function so the failure path - SDK missing, SDK broken,
    SDK changed - has a single place to be handled and a single place to be
    tested.
    """
    from langsmith.run_helpers import trace

    return trace


@contextmanager
def span(
    name: str,
    run_type: str = "chain",
    **metadata: Any,
) -> Iterator[Any]:
    """Open a LangSmith child run, or do nothing at all.

    Any failure inside the tracer is swallowed: the body of the ``with`` block
    still runs, and the caller cannot tell the difference.
    """
    if not is_enabled():
        yield None
        return

    manager = None
    handle = None
    try:
        langsmith_trace = _load_trace()
        manager = langsmith_trace(
            name=name,
            run_type=run_type if run_type in _RUN_TYPES else "chain",
            metadata=sanitize_metadata(metadata),
            project_name=status().project,
        )
        handle = manager.__enter__()
    except Exception as exc:  # noqa: BLE001
        _warn_once("LangSmith span could not be opened", error=str(exc), span=name)
        manager = None
        handle = None

    try:
        yield handle
    except Exception as error:
        if manager is not None:
            try:
                manager.__exit__(type(error), error, error.__traceback__)
            except Exception as exc:  # noqa: BLE001
                _warn_once("LangSmith span could not be closed", error=str(exc))
            manager = None
        raise
    finally:
        if manager is not None:
            try:
                manager.__exit__(None, None, None)
            except Exception as exc:  # noqa: BLE001
                _warn_once("LangSmith span could not be closed", error=str(exc))


_RUN_TYPES = frozenset({"tool", "chain", "llm", "retriever", "embedding", "prompt", "parser"})


def flush() -> None:
    """Best-effort flush of pending traces, e.g. on shutdown."""
    if not is_enabled():
        return
    try:
        from langsmith import Client

        Client().flush()
    except Exception as exc:  # noqa: BLE001
        _warn_once("LangSmith flush failed", error=str(exc))
