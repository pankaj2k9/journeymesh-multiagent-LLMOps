"""Security response headers."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings

# The API returns JSON only, so the policy can be extremely tight.
API_CONTENT_SECURITY_POLICY = (
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)

# When the same origin also serves the React build, the policy has to allow the
# application's own bundle, inline styles from the bundler and the webfonts.
# The theme initialiser in frontend/index.html runs inline, before the bundle,
# so the first paint is already in the right theme. It is allowed by hash
# rather than by 'unsafe-inline'; tests keep the hash and the script in step.
THEME_INIT_SCRIPT_HASH = "sha256-hqWtUNryutPN2j1SNlBiamg54n3gSAvg2YQYmk4uP8A="

APP_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data:; "
    f"script-src 'self' '{THEME_INIT_SCRIPT_HASH}'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' data: https://fonts.gstatic.com; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)

# Swagger UI is served from the same origin in development and needs its assets.
DOCS_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data: https://fastapi.tiangolo.com; "
    "script-src 'self' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' "
    "https://cdn.jsdelivr.net; frame-ancestors 'none'; base-uri 'none'"
)

_DOC_PATHS = ("/docs", "/redoc", "/openapi.json")

# Vite emits content-hashed filenames under /assets, so they can be cached
# forever. Everything else the API returns must not be stored.
_IMMUTABLE_PATHS = ("/assets/",)


def _serves_frontend() -> bool:
    """True when this process also serves the React build."""
    try:
        return get_settings().frontend_dist_path is not None
    except Exception:  # noqa: BLE001 - headers must never break a response
        return False


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response: Response = await call_next(request)
        settings = get_settings()

        path = request.url.path
        is_docs = any(path.startswith(prefix) for prefix in _DOC_PATHS)
        is_static = any(path.startswith(prefix) for prefix in _IMMUTABLE_PATHS)
        serves_html = _serves_frontend()

        if is_docs:
            policy = DOCS_CONTENT_SECURITY_POLICY
        elif serves_html:
            policy = APP_CONTENT_SECURITY_POLICY
        else:
            policy = API_CONTENT_SECURITY_POLICY
        response.headers.setdefault("Content-Security-Policy", policy)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), camera=(), microphone=(), payment=()"
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        response.headers.setdefault(
            "Cache-Control",
            "public, max-age=31536000, immutable" if is_static else "no-store",
        )
        if settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        if "server" in response.headers:
            del response.headers["server"]
        return response
