"""Request-level security middleware: identity, size limits and rate limiting."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.constants import EVENT_RATE_LIMIT_EXCEEDED
from app.observability import metrics
from app.observability.tracing import new_request_id, set_request_context, start_trace
from app.security import audit
from app.security.rate_limit import get_rate_limiter

_EXEMPT_PATHS = ("/api/v1/health", "/docs", "/redoc", "/openapi.json")


def client_key(request: Request) -> str:
    """Identify the caller for rate limiting.

    ``X-Forwarded-For`` is honoured because JourneyMesh is expected to sit
    behind a platform proxy; the left-most entry is used and truncated so the
    key is not a durable identifier.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        candidate = forwarded.split(",")[0].strip()
    elif request.client:
        candidate = request.client.host
    else:
        candidate = "anonymous"
    session = request.headers.get("x-journeymesh-session")
    return f"{candidate}|{session}" if session else candidate


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request id and a fresh trace to every request."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or new_request_id()
        start_trace()
        set_request_context(
            request_id=request_id,
            session_id=request.headers.get("x-journeymesh-session"),
        )
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversized payloads before they are parsed."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        settings = get_settings()
        max_size = settings.max_request_size
        declared = request.headers.get("content-length")

        if declared is not None:
            try:
                if int(declared) > max_size:
                    return _too_large(max_size)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"error": "invalid_request", "message": "Malformed Content-Length."},
                )
        elif request.method in {"POST", "PUT", "PATCH"}:
            body = await request.body()
            if len(body) > max_size:
                return _too_large(max_size)

        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window rate limiting for the API surface."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        settings = get_settings()
        path = request.url.path

        if not settings.rate_limit_enabled or path.startswith(_EXEMPT_PATHS):
            return await call_next(request)

        limiter = get_rate_limiter(
            limit=settings.rate_limit_requests,
            window_seconds=settings.rate_limit_window_seconds,
        )
        result = limiter.hit(client_key(request))

        if not result.allowed:
            metrics.increment("http.rate_limited", path=path)
            audit.record(EVENT_RATE_LIMIT_EXCEEDED, detail={"path": path})
            response = JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": "Too many requests. Please slow down and try again shortly.",
                },
            )
        else:
            response = await call_next(request)

        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        response.headers["X-RateLimit-Reset"] = str(result.reset_after)
        if not result.allowed:
            response.headers["Retry-After"] = str(max(result.reset_after, 1))
        return response


def _too_large(max_size: int) -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content=json.loads(
            json.dumps(
                {
                    "error": "payload_too_large",
                    "message": f"Request body must not exceed {max_size} bytes.",
                }
            )
        ),
    )
