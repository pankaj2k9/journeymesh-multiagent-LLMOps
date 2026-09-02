"""Health and readiness.

This endpoint is the platform's health check, so it has to be cheap and
predictable. It never calls an LLM, never runs the LangGraph workflow, never
invokes an MCP tool or an external travel API, never talks to LangSmith and
never opens a database connection - it reports configuration, not liveness of
third parties. ``?verbose=true`` adds the provider and MCP catalogue, which is
still local information.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query

from app.core.config import get_settings
from app.core.constants import APP_TAGLINE
from app.db.database import configured_backend
from app.schemas.travel import HealthResponse

router = APIRouter(tags=["health"])

VERSION = "1.0.0"


@router.get("/health", response_model=HealthResponse, summary="Service health")
def health(
    verbose: bool = Query(default=False, description="Include provider and MCP details"),
) -> HealthResponse:
    settings = get_settings()

    response = HealthResponse(
        status="ok",
        service="JourneyMesh API",
        app=settings.app_name,
        tagline=APP_TAGLINE,
        version=VERSION,
        environment=settings.app_env,
        database=configured_backend(),
        llm="groq" if settings.llm_available else "deterministic",
        time=datetime.now(timezone.utc),
    )

    if verbose:
        # Local configuration only - still no network and no database.
        from app.observability import metrics
        from app.services import provider_service

        response.checks = {
            "providers": provider_service.provider_configuration(),
            "mcp": provider_service.mcp_status(),
            "runtime": provider_service.runtime_status(),
            "observability": provider_service.observability_status(),
            "metrics": metrics.snapshot(),
        }
    return response
