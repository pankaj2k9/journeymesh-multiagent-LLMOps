"""Application level exceptions.

Every exception carries a stable machine-readable ``code`` so the API can
return a safe payload without leaking internals to the caller.
"""

from __future__ import annotations

from typing import Any, Optional


class JourneyMeshError(Exception):
    """Base class for every error raised by JourneyMesh."""

    status_code: int = 500
    code: str = "internal_error"
    safe_message: str = "JourneyMesh could not complete this request."

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        details: Optional[dict[str, Any]] = None,
        code: Optional[str] = None,
    ) -> None:
        super().__init__(message or self.safe_message)
        self.message = message or self.safe_message
        self.details = details or {}
        if code:
            self.code = code

    def to_payload(self, *, include_message: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {"error": self.code, "message": self.safe_message}
        if include_message and self.message != self.safe_message:
            payload["detail"] = self.message
        if self.details:
            payload["details"] = self.details
        return payload


class ValidationRejection(JourneyMeshError):
    status_code = 422
    code = "invalid_request"
    safe_message = "The travel request could not be validated."


class GuardrailRejection(JourneyMeshError):
    status_code = 400
    code = "guardrail_blocked"
    safe_message = "This request was blocked by JourneyMesh safety checks."


class PromptInjectionRejection(GuardrailRejection):
    code = "prompt_injection_blocked"
    safe_message = "The request contained instructions JourneyMesh cannot follow."


class ToolAuthorizationError(JourneyMeshError):
    status_code = 403
    code = "tool_call_blocked"
    safe_message = "The requested tool call is not permitted."


class OutputValidationError(JourneyMeshError):
    status_code = 502
    code = "output_validation_failed"
    safe_message = "JourneyMesh produced a response that failed validation."


class ProviderError(JourneyMeshError):
    status_code = 502
    code = "provider_failure"
    safe_message = "An external travel data provider is unavailable."


class RateLimitExceeded(JourneyMeshError):
    status_code = 429
    code = "rate_limit_exceeded"
    safe_message = "Too many requests. Please slow down and try again shortly."


class RequestTooLarge(JourneyMeshError):
    status_code = 413
    code = "payload_too_large"
    safe_message = "The request payload is larger than JourneyMesh accepts."


class TripNotFound(JourneyMeshError):
    status_code = 404
    code = "trip_not_found"
    safe_message = "That journey could not be found."


class InvalidReviewState(JourneyMeshError):
    status_code = 409
    code = "invalid_review_state"
    safe_message = "This journey is not in a state that accepts that review action."


class RevisionLimitReached(JourneyMeshError):
    status_code = 409
    code = "revision_limit_reached"
    safe_message = (
        "This journey has reached its revision limit. "
        "Approve the current plan or start a new journey."
    )


class PersistenceUnavailable(JourneyMeshError):
    status_code = 503
    code = "persistence_unavailable"
    safe_message = "Journey storage is not configured."
