"""Structured logging for JourneyMesh.

Logs are emitted as single-line JSON so they can be shipped anywhere without
a parser. Every record is passed through the PII redactor before it is
written, so credentials and traveller documents never reach the log stream.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Optional

from app.core.config import get_settings

_CONFIGURED = False
_SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "token",
    "password",
    "secret",
    "groq_api_key",
    "tavily_api_key",
    "aviationstack_api_key",
    "openweather_api_key",
    "database_url",
    "passport",
    "passport_number",
    "national_id",
    "credit_card",
    "card_number",
}

_RESERVED = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
) | {"message", "asctime", "taskName"}


def _scrub(value: Any, depth: int = 0) -> Any:
    from app.guardrails.pii_guard import redact_text  # local import avoids a cycle

    if depth > 6:
        return "..."
    if isinstance(value, dict):
        scrubbed: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in _SENSITIVE_KEYS:
                scrubbed[key] = "[REDACTED]"
            else:
                scrubbed[key] = _scrub(item, depth + 1)
        return scrubbed
    if isinstance(value, (list, tuple)):
        return [_scrub(item, depth + 1) for item in value]
    if isinstance(value, str):
        return redact_text(value).text
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": _scrub(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = _scrub(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.msg = _scrub(record.getMessage())
        record.args = ()
        return super().format(record)


def configure_logging(level: Optional[str] = None, fmt: Optional[str] = None) -> None:
    """Install the JourneyMesh log handler. Safe to call more than once."""
    global _CONFIGURED
    settings = get_settings()
    level = (level or settings.log_level).upper()
    fmt = (fmt or settings.log_format).lower()

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            TextFormatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s", "%H:%M:%S")
        )
    root.addHandler(handler)
    root.setLevel(getattr(logging, level, logging.INFO))

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    if not _CONFIGURED:
        configure_logging()
    return logging.getLogger(name)
