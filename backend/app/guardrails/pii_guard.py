"""Personally identifiable information detection and redaction.

The guard runs in two directions:

* outbound - before text is handed to an LLM, an MCP server or a log sink;
* inbound  - before a model response is returned to the caller.

Detection is deliberately regex based and deterministic: it must never depend
on a model call, because it also protects the model call itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.core.constants import REDACTION_TOKEN

# --- Patterns -------------------------------------------------------------
# Each entry is (category, compiled pattern, replacement label).
_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "credit_card",
        re.compile(r"\b(?:\d[ -]?){13,19}\b"),
        "card",
    ),
    (
        "passport",
        re.compile(
            r"\b(?:passport(?:\s*(?:no|number|#))?\s*[:=]?\s*)([A-Z]{1,2}\d{6,9})\b",
            re.IGNORECASE,
        ),
        "passport",
    ),
    (
        "national_id",
        re.compile(
            r"\b(?:nid|national\s*id|aadhaar|ssn)\s*[:=#]?\s*([0-9][0-9\- ]{7,17}[0-9])\b",
            re.IGNORECASE,
        ),
        "national_id",
    ),
    (
        "iban",
        re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"),
        "bank_account",
    ),
    (
        "email",
        re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b"),
        "email",
    ),
    (
        "phone",
        re.compile(r"(?<![\w.])\+?\d[\d\s().-]{8,17}\d(?![\w.])"),
        "phone",
    ),
    (
        "api_key",
        re.compile(
            r"\b(?:sk|gsk|pk|tvly|api|key|token|bearer)[-_ ]?[A-Za-z0-9_\-]{16,}\b",
            re.IGNORECASE,
        ),
        "credential",
    ),
]

# Terms whose presence signals a travel-document conversation even without a
# matching number.
_DOCUMENT_HINTS = (
    "passport number",
    "passport no",
    "visa number",
    "national id",
    "driving licence",
    "driver's license",
    "credit card",
    "cvv",
    "bank account",
    "routing number",
)


@dataclass
class RedactionResult:
    text: str
    categories: list[str] = field(default_factory=list)

    @property
    def redacted(self) -> bool:
        return bool(self.categories)


def _luhn_valid(digits: str) -> bool:
    numbers = [int(char) for char in digits if char.isdigit()]
    if len(numbers) < 13:
        return False
    checksum = 0
    parity = len(numbers) % 2
    for index, digit in enumerate(numbers):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def redact_text(text: str) -> RedactionResult:
    """Return ``text`` with recognised PII replaced by labelled placeholders."""
    if not text:
        return RedactionResult(text=text)

    found: list[str] = []
    redacted = text

    for category, pattern, label in _PATTERNS:
        def _replace(match: re.Match[str], _cat: str = category, _label: str = label) -> str:
            raw = match.group(0)
            if _cat == "credit_card" and not _luhn_valid(raw):
                return raw
            if _cat not in found:
                found.append(_cat)
            return f"{_label}={REDACTION_TOKEN}"

        redacted = pattern.sub(_replace, redacted)

    return RedactionResult(text=redacted, categories=found)


def detect(text: str) -> list[str]:
    """Return the PII categories present in ``text`` without modifying it."""
    return redact_text(text).categories


def mentions_travel_documents(text: str) -> bool:
    lowered = (text or "").lower()
    return any(hint in lowered for hint in _DOCUMENT_HINTS)


def sanitize_for_model(text: str) -> RedactionResult:
    """Redact before anything leaves the process toward an LLM or provider."""
    return redact_text(text)


def sanitize_payload(payload: Any, depth: int = 0) -> tuple[Any, list[str]]:
    """Recursively redact a JSON-like payload. Returns (payload, categories)."""
    categories: list[str] = []
    if depth > 8:
        return payload, categories

    if isinstance(payload, str):
        result = redact_text(payload)
        return result.text, result.categories
    if isinstance(payload, dict):
        cleaned: dict[Any, Any] = {}
        for key, value in payload.items():
            new_value, found = sanitize_payload(value, depth + 1)
            cleaned[key] = new_value
            for item in found:
                if item not in categories:
                    categories.append(item)
        return cleaned, categories
    if isinstance(payload, (list, tuple)):
        cleaned_list = []
        for value in payload:
            new_value, found = sanitize_payload(value, depth + 1)
            cleaned_list.append(new_value)
            for item in found:
                if item not in categories:
                    categories.append(item)
        return cleaned_list, categories
    return payload, categories


def summarise(categories: Iterable[str]) -> str:
    unique = sorted(set(categories))
    if not unique:
        return "no personal data detected"
    return "redacted: " + ", ".join(unique)
