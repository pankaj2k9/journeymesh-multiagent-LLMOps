"""JourneyMesh API entry point.

Every journey, intelligently connected.

Author: Pankaj <pkp2.me2k9@gmail.com> - https://pankajpramanik.com
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.api.static_site import mount_frontend
from app.core.config import get_settings
from app.core.constants import APP_TAGLINE, EVENT_INVALID_REQUEST
from app.core.exceptions import JourneyMeshError
from app.db.database import init_db
from app.mcp import lifecycle as mcp_lifecycle
from app.observability import langsmith, metrics
from app.observability.logging import configure_logging, get_logger
from app.security import audit
from app.security.headers import SecurityHeadersMiddleware
from app.security.request_security import (
    RateLimitMiddleware,
    RequestContextMiddleware,
    RequestSizeLimitMiddleware,
)

logger = get_logger("journeymesh.app")

DESCRIPTION = """
A multilingual, agentic travel planning API.

* A **Supervisor** chooses which specialist agents a request actually needs.
* **Flight, Hotel, Weather, Budget and Itinerary** agents work through a shared
  `TravelState` rather than calling each other.
* Every external call passes the **MCP Tool Guard** before it reaches a provider.
* **Input and output guardrails** protect the model in both directions.
* Every draft is **evaluated** and then paused for **human review**; requesting a
  change re-runs only the agents that change affects.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging()

    # Observability first, so start-up itself can be traced. This never raises:
    # a misconfigured tracer must not stop the service from starting.
    tracing_status = langsmith.configure()

    logger.info(
        "JourneyMesh starting",
        extra={
            "environment": settings.app_env,
            "tagline": APP_TAGLINE,
            "database": "configured" if settings.database_url else "ephemeral",
            "langsmith": tracing_status.enabled,
        },
    )

    try:
        init_db()
    except Exception as exc:  # noqa: BLE001 - the API can still serve health
        logger.error("database initialisation failed", extra={"error": str(exc)})

    # Start the MCP servers this application owns. The weather server is a
    # child process of THIS process - `sys.executable -m app.mcp.weather_server`
    # - so it appears by itself under `uvicorn app.main:app --reload` locally
    # and under `docker compose up -d` in production, with no systemd unit, no
    # extra container, no port and no terminal to keep open.
    #
    # A failure here is logged and nothing more: tool calls fall back to a
    # per-call session and then to the in-process adapter, so a weather server
    # that will not start must never stop the API from serving.
    try:
        started = await mcp_lifecycle.start_managed_servers()
        logger.info("MCP servers started", extra={"servers": started})
    except Exception as exc:  # noqa: BLE001
        logger.error("MCP start-up failed", extra={"error": str(exc)})

    yield

    # Terminate those child processes explicitly. Without this a reload or a
    # container stop would leave them holding pipes until the kernel reaps
    # them, which is how a long-running container accumulates zombies.
    try:
        await mcp_lifecycle.stop_managed_servers()
    except Exception as exc:  # noqa: BLE001 - shutdown must not raise
        logger.warning("MCP shutdown raised", extra={"error": str(exc)})

    langsmith.flush()
    logger.info("JourneyMesh shutting down")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        summary=APP_TAGLINE,
        version="1.0.0",
        contact={
            "name": "Pankaj",
            "email": "pkp2.me2k9@gmail.com",
            "url": "https://pankajpramanik.com",
        },
        license_info={"name": "MIT"},
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # Middleware runs bottom-up: context first, then size, rate limit, headers.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID", "X-JourneyMesh-Session"],
        expose_headers=["X-Request-ID", "X-RateLimit-Remaining"],
        max_age=600,
    )

    app.include_router(api_router)

    @app.get("/health", include_in_schema=False)
    def platform_health() -> dict[str, str]:
        """The deployment platform's readiness probe.

        Deliberately the cheapest route in the application: no model, no graph,
        no MCP tool, no travel provider, no tracing call and no database round
        trip. A probe that touched any of those would fail during someone
        else's outage and the platform would restart a healthy container,
        turning a partial degradation into a total one.

        It answers 200 as soon as the application object is built and the
        routes are mounted, which is exactly what "ready for traffic" means
        here - migrations have already run in the pre-deploy step by the time
        this process starts. `/api/v1/health` remains the richer, versioned
        endpoint for humans and for the interface.
        """
        return {"status": "healthy", "service": settings.app_name}


    @app.exception_handler(JourneyMeshError)
    async def journeymesh_error_handler(
        request: Request, exc: JourneyMeshError
    ) -> JSONResponse:
        metrics.increment("http.errors", code=exc.code)
        logger.warning(
            "request failed",
            extra={"code": exc.code, "path": request.url.path},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_payload(include_message=not settings.is_production),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        audit.record(EVENT_INVALID_REQUEST, detail={"path": request.url.path})
        return JSONResponse(
            status_code=422,
            content={
                "error": "invalid_request",
                "message": "The request could not be validated.",
                "details": {
                    "fields": [
                        {
                            "field": ".".join(str(part) for part in error.get("loc", [])[1:]),
                            "problem": error.get("msg"),
                        }
                        for error in exc.errors()[:10]
                    ]
                },
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error", extra={"path": request.url.path})
        metrics.increment("http.errors", code="internal_error")
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "JourneyMesh could not complete this request.",
            },
        )

    # The SPA catch-all is registered last so that /api, /docs and /openapi.json
    # keep their own routes. When no build is present this is a no-op and the
    # root route below answers instead.
    serving_frontend = mount_frontend(app)

    if not serving_frontend:

        @app.get("/", include_in_schema=False)
        def root() -> dict[str, str]:
            return {
                "app": settings.app_name,
                "tagline": APP_TAGLINE,
                "docs": "/docs",
                "api": settings.api_prefix,
            }

    return app


app = create_app()
