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
    servers = server_configs()
    return {
        "servers": {
            name: {
                "transport": config.transport,
                "enabled": config.enabled,
                "url_configured": bool(config.url),
                "description": config.description,
            }
            for name, config in servers.items()
        },
        "tools": registry.catalogue(),
    }


def runtime_status() -> dict[str, Any]:
    settings = get_settings()
    return {
        "environment": settings.app_env,
        "database": backend_name(),
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
