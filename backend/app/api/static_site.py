"""Serving the React build from FastAPI.

In the single-image production deployment there is one origin:

    /                     the React application
    /trip/abc-123         the React application (client-side route)
    /history              the React application (client-side route)
    /assets/index-x.js    the hashed bundle
    /api/v1/health        FastAPI
    /api/v1/trips/plan    FastAPI

The catch-all below is what makes a browser refresh work on a nested route:
anything that is not an API path, not a documentation path and not a real file
on disk returns ``index.html`` so React Router can take over.

When no build is present - running the API on its own in development, for
example - nothing is mounted and the API behaves exactly as before.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.observability.logging import get_logger

logger = get_logger("journeymesh.static")

# Paths that belong to the API and must never fall through to the SPA.
RESERVED_PREFIXES = ("api", "docs", "redoc", "openapi.json", "healthz", "health")

# Hashed filenames may be cached forever; everything else must not be.
IMMUTABLE_DIRECTORIES = ("assets",)


def _is_reserved(path: str) -> bool:
    head = path.split("/", 1)[0].lower()
    return head in RESERVED_PREFIXES


def _safe_file(dist: Path, relative: str) -> Path | None:
    """Resolve a request path inside the build directory, or return None.

    Anything that escapes the directory - through ``..`` or a symlink - is
    rejected rather than served.
    """
    if not relative:
        return None
    candidate = (dist / relative).resolve()
    try:
        candidate.relative_to(dist.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def mount_frontend(app: FastAPI) -> bool:
    """Attach the React build to ``app``. Returns True when one was found."""
    settings = get_settings()
    dist = settings.frontend_dist_path

    if dist is None:
        logger.info(
            "no frontend build found - the API is serving its own routes only",
            extra={"serve_frontend": settings.serve_frontend},
        )
        return False

    index_file = dist / "index.html"

    assets_dir = dist / "assets"
    if assets_dir.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=assets_dir),
            name="journeymesh-assets",
        )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str, request: Request) -> FileResponse:  # noqa: ANN202
        if _is_reserved(full_path):
            # Let FastAPI's own 404 handling answer for API-shaped paths.
            raise HTTPException(status_code=404, detail="Not found")

        file = _safe_file(dist, full_path)
        if file is not None:
            immutable = file.parent.name in IMMUTABLE_DIRECTORIES
            return FileResponse(
                file,
                headers={
                    "Cache-Control": "public, max-age=31536000, immutable"
                    if immutable
                    else "no-cache"
                },
            )

        # A client-side route: hand back the shell and let React Router route it.
        return FileResponse(index_file, headers={"Cache-Control": "no-cache"})

    logger.info("serving the React build", extra={"dist": str(dist)})
    return True
