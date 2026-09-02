"""Language-model access.

Every prompt leaves the process through this module, which means there is one
place that redacts personal data, enforces timeouts, counts calls and repairs
malformed JSON. When no model is configured the service reports itself as
unavailable and callers fall back to their deterministic path - JourneyMesh
never blocks on a missing credential.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.guardrails import pii_guard, prompt_injection
from app.observability import metrics
from app.observability.logging import get_logger
from app.observability.tracing import span

logger = get_logger("journeymesh.llm")

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


@dataclass
class LLMCall:
    purpose: str
    ok: bool
    latency_ms: int = 0
    error: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class LLMUsage:
    calls: list[LLMCall] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.calls)

    def summary(self) -> dict[str, Any]:
        return {
            "calls": self.count,
            "failed": sum(1 for call in self.calls if not call.ok),
            "input_tokens": sum(call.input_tokens or 0 for call in self.calls) or None,
            "output_tokens": sum(call.output_tokens or 0 for call in self.calls) or None,
        }


class LLMService:
    """Thin wrapper over the configured chat model."""

    def __init__(self) -> None:
        self.usage = LLMUsage()
        self._model: Any = None
        self._model_failed = False

    # ---- capability ------------------------------------------------------
    @property
    def available(self) -> bool:
        settings = get_settings()
        return bool(settings.groq_api_key) and not self._model_failed

    @property
    def model_name(self) -> str:
        return get_settings().groq_model

    def describe(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "model": self.model_name if self.available else None,
            "mode": "groq" if self.available else "deterministic",
        }

    def _client(self) -> Any:
        if self._model is not None:
            return self._model
        settings = get_settings()
        try:
            from langchain_groq import ChatGroq

            self._model = ChatGroq(
                api_key=settings.groq_api_key,
                model=settings.groq_model,
                temperature=settings.llm_temperature,
                timeout=settings.llm_timeout_seconds,
                max_retries=1,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("chat model unavailable", extra={"error": str(exc)})
            self._model_failed = True
            raise
        return self._model

    # ---- prompting -------------------------------------------------------
    def _prepare(self, text: str) -> str:
        """Redact personal data and neutralise embedded instructions."""
        cleaned = pii_guard.sanitize_for_model(text or "").text
        return prompt_injection.neutralise(cleaned)

    async def complete_text(
        self, *, system: str, user: str, purpose: str, max_chars: int = 4000
    ) -> str | None:
        """Return a plain-text completion, or ``None`` when unavailable."""
        if not self.available:
            return None

        safe_user = self._prepare(user)[:max_chars]
        with span(f"llm:{purpose}", kind="llm", model=self.model_name) as current:
            try:
                model = self._client()
                response = await model.ainvoke(
                    [("system", system), ("human", safe_user)]
                )
            except Exception as exc:  # noqa: BLE001
                current.success = False
                self.usage.calls.append(
                    LLMCall(purpose=purpose, ok=False, error=type(exc).__name__)
                )
                metrics.increment("llm.failures", purpose=purpose)
                logger.warning("llm call failed", extra={"purpose": purpose, "error": str(exc)})
                return None

        content = getattr(response, "content", None)
        if isinstance(content, list):  # some providers return content blocks
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part) for part in content
            )

        metadata = getattr(response, "usage_metadata", None) or {}
        self.usage.calls.append(
            LLMCall(
                purpose=purpose,
                ok=True,
                latency_ms=current.latency_ms or 0,
                input_tokens=metadata.get("input_tokens"),
                output_tokens=metadata.get("output_tokens"),
            )
        )
        metrics.increment("llm.calls", purpose=purpose)
        metrics.observe("llm.latency", current.latency_ms or 0, purpose=purpose)
        return content if isinstance(content, str) else None

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        purpose: str,
        fallback: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Return a parsed JSON object, or ``fallback`` when that is not possible."""
        instruction = (
            f"{system}\n\n"
            "Reply with a single JSON object and nothing else. Do not include an "
            "explanation, markdown fences or your reasoning."
        )
        raw = await self.complete_text(system=instruction, user=user, purpose=purpose)
        if not raw:
            return fallback

        parsed = parse_json_object(raw)
        if parsed is None:
            logger.info("llm returned unparseable json", extra={"purpose": purpose})
            metrics.increment("llm.json_parse_failures", purpose=purpose)
            return fallback
        return parsed


def parse_json_object(raw: str) -> dict[str, Any] | None:
    """Extract the first JSON object from a model response."""
    if not raw:
        return None

    candidate = raw.strip()
    fenced = _JSON_BLOCK.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()

    try:
        value = json.loads(candidate)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        value = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


_service: LLMService | None = None


def get_llm_service() -> LLMService:
    global _service
    if _service is None:
        _service = LLMService()
    return _service


def reset_llm_service() -> None:
    global _service
    _service = None
