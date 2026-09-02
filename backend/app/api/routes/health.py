"""Health and readiness."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.constants import APP_TAGLINE
from app.db.database import backend_name
from app.observability import metrics
from app.schemas.travel import HealthResponse
from app.services import provider_service

router = APIRouter(tags=["health"])

VERSION = "1.0.0"


@router.get("/health", response_model=HealthResponse, summary="Service health")
def health() -> HealthResponse:
    settings = get_settings()
    providers = provider_service.provider_configuration()
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        tagline=APP_TAGLINE,
        version=VERSION,
        environment=settings.app_env,
        database=backend_name(),
        llm=providers["llm"]["mode"],
        checks={
            "providers": providers,
            "mcp": provider_service.mcp_status(),
            "runtime": provider_service.runtime_status(),
            "metrics": metrics.snapshot(),
        },
        time=datetime.now(timezone.utc),
    )
