"""Secret access and masking.

Secrets are read from the environment exactly once, through this module, so
that there is a single place to audit. Nothing here ever returns a raw secret
to a caller that only needs to know whether it exists.
"""

from __future__ import annotations

from typing import Optional

from app.core.config import get_settings

_SECRET_FIELDS = (
    "groq_api_key",
    "tavily_api_key",
    "aviationstack_api_key",
    "openweather_api_key",
    "database_url",
)


def get_secret(name: str) -> Optional[str]:
    """Return a configured secret by settings field name."""
    if name not in _SECRET_FIELDS:
        raise KeyError(f"'{name}' is not a registered JourneyMesh secret")
    return getattr(get_settings(), name, None)


def has_secret(name: str) -> bool:
    return bool(get_secret(name))


def mask(value: Optional[str], *, keep: int = 4) -> str:
    """Mask a secret for display: only the last ``keep`` characters survive."""
    if not value:
        return "not_configured"
    if len(value) <= keep:
        return "*" * len(value)
    return "*" * (len(value) - keep) + value[-keep:]


def configured_secrets() -> dict[str, bool]:
    """Report which secrets are present without revealing any value."""
    return {name: has_secret(name) for name in _SECRET_FIELDS}


def redact_environment_dump(text: str) -> str:
    """Defensive helper: remove any configured secret value from free text."""
    cleaned = text
    for name in _SECRET_FIELDS:
        value = get_secret(name)
        if value and len(value) >= 8 and value in cleaned:
            cleaned = cleaned.replace(value, "[REDACTED]")
    return cleaned
