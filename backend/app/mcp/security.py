"""Redaction for MCP endpoints and errors.

Tavily's hosted MCP server takes its API key as a *query parameter*, so the
endpoint URL is itself a credential. That URL would otherwise reach a log
line, an exception string, a LangSmith trace and the health endpoint - four
places this repository treats as public, because the repository is public and
its Actions logs are public.

Everything here is deliberately conservative: it redacts by parameter name and
by shape, and when it cannot parse something it redacts the whole value rather
than guessing.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED = "***"

# Query parameters whose value is a credential. Matched case-insensitively and
# as a substring, so `tavilyApiKey`, `api_key` and `X-Api-Token` all hit.
_SECRET_PARAM_MARKERS = (
    "key",
    "token",
    "secret",
    "password",
    "passwd",
    "auth",
    "credential",
    "sig",
)

# Credential shapes that may appear in free text - an exception message, a
# subprocess stderr line - where there is no URL to parse.
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(tavily|api|access|secret)[-_]?key\s*[=:]\s*\S+"),
    re.compile(r"\bgsk_[A-Za-z0-9]{10,}"),
    re.compile(r"\btvly-[A-Za-z0-9]{8,}"),
    re.compile(r"\blsv2_[A-Za-z0-9_]{10,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{10,}"),
)


def _is_secret_param(name: str) -> bool:
    lowered = name.lower()
    return any(marker in lowered for marker in _SECRET_PARAM_MARKERS)


def redact_url(url: str | None) -> str | None:
    """Return a URL safe to log, with credential query parameters masked.

    ``https://mcp.tavily.com/mcp/?tavilyApiKey=abc123``
    becomes
    ``https://mcp.tavily.com/mcp/?tavilyApiKey=***``

    Userinfo credentials (``https://user:pass@host``) are masked too. A URL
    that cannot be parsed is replaced entirely rather than returned as-is.
    """
    if not url:
        return url

    try:
        parts = urlsplit(url)
    except ValueError:
        return REDACTED

    netloc = parts.netloc
    if "@" in netloc:
        _, _, host = netloc.rpartition("@")
        netloc = f"{REDACTED}@{host}"

    query = parts.query
    if query:
        pairs = parse_qsl(query, keep_blank_values=True)
        if pairs:
            # safe="*" so the marker stays a readable "***" rather than
            # being percent-encoded into %2A%2A%2A in every log line.
            query = urlencode(
                [(k, REDACTED if _is_secret_param(k) else v) for k, v in pairs],
                safe="*",
            )
        elif _looks_secret(query):
            query = REDACTED

    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


def _looks_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


def redact_text(text: str | None) -> str:
    """Mask credentials in free text: an error message, a stderr line.

    Applied to every MCP error before it reaches a log, a trace or an API
    response, because an SDK exception commonly quotes the URL it failed on.
    """
    if not text:
        return ""

    result = str(text)

    # Any URL inside the text, redacted through the parser above.
    for match in set(re.findall(r"https?://\S+", result)):
        redacted = redact_url(match.rstrip(".,;)")) or REDACTED
        result = result.replace(match.rstrip(".,;)"), redacted)

    for pattern in _SECRET_PATTERNS:
        result = pattern.sub(REDACTED, result)

    return result


def safe_error(exc: BaseException, *, limit: int = 300) -> str:
    """A short, redacted, single-line description of a failure.

    The type is kept because it is diagnostic and never sensitive; the message
    is redacted and truncated because it frequently is.
    """
    message = redact_text(str(exc)).replace("\n", " ").strip()
    if len(message) > limit:
        message = message[: limit - 1].rstrip() + "…"
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__
