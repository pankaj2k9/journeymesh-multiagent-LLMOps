"""Vercel entry point for the JourneyMesh backend.

Vercel's Python runtime imports an ASGI application object from this module
and serves it directly - there is no long-running ``uvicorn`` process, so the
application must not rely on one. Everything JourneyMesh needs at start-up
happens in the FastAPI lifespan, which the platform runs per cold start.

Deploy this directory as its own Vercel project with `backend` as the root.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402

# Vercel looks for `app` (ASGI) in this module.
__all__ = ["app"]
