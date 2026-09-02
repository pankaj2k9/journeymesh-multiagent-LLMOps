"""Application services.

``TravelService`` and ``ReviewService`` are resolved lazily: they depend on the
graph, which depends on the agents, which depend on ``llm_service`` in this
same package. Importing them eagerly here would close that loop.
"""

from __future__ import annotations

from typing import Any

from app.services.llm_service import LLMService, get_llm_service

__all__ = [
    "LLMService",
    "get_llm_service",
    "ConversationService",
    "ReviewService",
    "TravelService",
    "provider_configuration",
    "mcp_status",
    "runtime_status",
]

_LAZY = {
    "ConversationService": ("app.services.conversation_service", "ConversationService"),
    "ReviewService": ("app.services.review_service", "ReviewService"),
    "TravelService": ("app.services.travel_service", "TravelService"),
    "provider_configuration": ("app.services.provider_service", "provider_configuration"),
    "mcp_status": ("app.services.provider_service", "mcp_status"),
    "runtime_status": ("app.services.provider_service", "runtime_status"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module 'app.services' has no attribute '{name}'")
    from importlib import import_module

    return getattr(import_module(target[0]), target[1])
