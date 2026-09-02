"""Prompt-injection detection.

Prompting alone is not a control. This module is an application-level
classifier that runs before any user text reaches an LLM, and its verdict is
enforced by the API layer rather than by the model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# Each rule is (rule_id, weight, pattern).
_RULES: list[tuple[str, float, re.Pattern[str]]] = [
    (
        "override_instructions",
        0.9,
        re.compile(
            r"\b(ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}\b"
            r"(previous|prior|earlier|above|all|any|your)\b[^.\n]{0,30}\b"
            r"(instruction|instructions|prompt|prompts|rule|rules|guideline|guidelines|context)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "reveal_system_prompt",
        0.9,
        re.compile(
            r"\b(show|reveal|print|repeat|output|display|dump|tell me)\b[^.\n]{0,40}\b"
            r"(system prompt|system message|initial instructions|your prompt|"
            r"developer message|hidden instructions)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "extract_secrets",
        1.0,
        re.compile(
            r"\b(api[ _-]?key|secret key|access token|bearer token|credential|password|"
            r"env(?:ironment)? variable|\.env|DATABASE_URL|GROQ_API_KEY|TAVILY_API_KEY|"
            r"AVIATIONSTACK_API_KEY|OPENWEATHER_API_KEY)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "file_access",
        0.9,
        re.compile(
            r"\b(cat|open|read|load|fetch|download)\b[^.\n]{0,25}"
            r"(/etc/passwd|/etc/shadow|~/\.ssh|id_rsa|\.env\b|file://|"
            r"[A-Za-z]:\\\\Windows)",
            re.IGNORECASE,
        ),
    ),
    (
        "shell_execution",
        0.9,
        re.compile(
            r"\b(execute|run|eval|exec|spawn)\b[^.\n]{0,25}"
            r"\b(shell|bash|sh|command|os\.system|subprocess|powershell|cmd\.exe)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "tool_permission_override",
        0.9,
        re.compile(
            r"\b(you are now|act as|pretend to be|switch to)\b[^.\n]{0,40}\b"
            r"(admin|root|developer mode|dan|unrestricted|god mode|no restrictions)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "hidden_tool_invocation",
        0.8,
        re.compile(
            r"(<\|?(?:im_start|im_end|system|assistant)\|?>|"
            r"\{\{\s*tool[\w\s]*\}\}|\[\[\s*tool[^\]]*\]\]|"
            r"call\s+the\s+hidden\s+tool|invoke\s+internal\s+tool)",
            re.IGNORECASE,
        ),
    ),
    (
        "guard_disable",
        0.9,
        re.compile(
            r"\b(disable|turn off|skip|remove|deactivate)\b[^.\n]{0,30}\b"
            r"(guardrail|guardrails|safety|filter|validation|moderation|tool guard)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "role_confusion",
        0.6,
        re.compile(
            r"^\s*(system|assistant|developer)\s*:",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "exfiltration",
        0.8,
        re.compile(
            r"\b(send|post|upload|forward|leak)\b[^.\n]{0,30}\b"
            r"(to\s+https?://|to\s+my\s+server|webhook|pastebin)\b",
            re.IGNORECASE,
        ),
    ),
]

BLOCK_THRESHOLD = 0.8


@dataclass
class InjectionVerdict:
    blocked: bool = False
    score: float = 0.0
    matched_rules: list[str] = field(default_factory=list)
    reason: Optional[str] = None

    @property
    def suspicious(self) -> bool:
        return bool(self.matched_rules)


def scan(text: str) -> InjectionVerdict:
    """Score ``text`` against the injection rule set."""
    if not text:
        return InjectionVerdict()

    matched: list[str] = []
    score = 0.0
    for rule_id, weight, pattern in _RULES:
        if pattern.search(text):
            matched.append(rule_id)
            score = max(score, weight)

    # Two independent medium-confidence signals are treated as one strong one.
    if len(matched) >= 2:
        score = min(1.0, score + 0.2)

    blocked = score >= BLOCK_THRESHOLD
    reason = None
    if blocked:
        reason = (
            "The request asks JourneyMesh to change its own instructions or to expose "
            "internal configuration, which is not something a travel planner will do."
        )
    return InjectionVerdict(blocked=blocked, score=round(score, 2), matched_rules=matched, reason=reason)


def is_injection(text: str) -> bool:
    return scan(text).blocked


def neutralise(text: str) -> str:
    """Strip control markers so untrusted text can be embedded as data."""
    cleaned = re.sub(r"<\|?(?:im_start|im_end|system|assistant)\|?>", " ", text or "")
    cleaned = re.sub(r"^\s*(system|assistant|developer)\s*:", "user note:", cleaned, flags=re.IGNORECASE | re.MULTILINE)
    return cleaned.strip()
