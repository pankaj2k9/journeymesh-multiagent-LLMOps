"""Provider and MCP status reporting.

Used by the health endpoint and by the frontend's provider panel so a
traveller can see which data was live and which was estimated.
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.db.database import backend_name
from app.mcp import registry
from app.mcp.config import server_configs
from app.security import secret_manager
from app.services.llm_service import get_llm_service


def provider_configuration() -> dict[str, Any]:
    """Which providers are configured. Never returns a secret value."""
    configured = secret_manager.configured_secrets()
    return {
        "flights": {
            "provider": "aviationstack",
            "configured": configured["aviationstack_api_key"],
            "fallback": "JourneyMesh route reference data (labelled ESTIMATE)",
        },
        "hotels": {
            "provider": "tavily",
            "configured": configured["tavily_api_key"],
            "fallback": "JourneyMesh nightly-rate bands (labelled ESTIMATE)",
        },
        "weather": {
            "provider": "openweather",
            "configured": configured["openweather_api_key"],
            "fallback": "JourneyMesh climate normals (labelled ESTIMATE)",
        },
        "llm": get_llm_service().describe(),
    }


def mcp_status() -> dict[str, Any]:
    """Configuration only: what each MCP server is set up to do.

    Cheap by construction - it reads settings and starts nothing. `describe()`
    is what keeps the Tavily URL out of this response: the key is a query
    parameter, so the raw URL is a credential and only its redacted form is
    ever returned.

    For "can it actually be reached?", use GET /api/v1/health/mcp?probe=true.
    """
    servers = server_configs()
    return {
        "servers": {name: config.describe() for name, config in servers.items()},
        "tools": registry.catalogue(),
    }


async def mcp_probe(names: list[str] | None = None) -> dict[str, Any]:
    """Actually connect to each MCP server and list its tools.

    Expensive: it opens an HTTPS session or starts a subprocess per server.
    Each is probed independently and concurrently, so one failure reports as
    one failure rather than taking the report down with it.
    """
    from app.mcp.lifecycle import probe_all

    report = await probe_all(names)
    return {
        "servers": report,
        "reachable": sorted(n for n, r in report.items() if r.get("reachable")),
        "unreachable": sorted(
            n for n, r in report.items() if r.get("enabled") and not r.get("reachable")
        ),
        "disabled": sorted(n for n, r in report.items() if not r.get("enabled")),
    }


def observability_status() -> dict[str, Any]:
    """What the observability stack is doing. Never contains a key."""
    from app.observability import langsmith

    return {"langsmith": langsmith.status().to_dict()}


def runtime_status() -> dict[str, Any]:
    settings = get_settings()
    return {
        "environment": settings.app_env,
        "database": backend_name(),
        "observability": observability_status(),
        "guardrails_enabled": settings.guardrails_enabled,
        "tool_guard_enabled": settings.tool_guard_enabled,
        "evaluation": {
            "enabled": settings.evaluation_enabled,
            "mode": settings.evaluation_mode,
            "pass_threshold": settings.evaluation_pass_threshold,
        },
        "max_revision_count": settings.max_revision_count,
        "mock_data": settings.enable_mock_data,
    }
