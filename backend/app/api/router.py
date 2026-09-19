"""Versioned API router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    auth,
    budget,
    currency,
    dashboard,
    health,
    history,
    media,
    places,
    preferences,
    review,
    search,
    travel,
)
from app.core.constants import API_PREFIX

api_router = APIRouter(prefix=API_PREFIX)
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(travel.router)
api_router.include_router(history.router)
api_router.include_router(review.router)
api_router.include_router(budget.router)
api_router.include_router(preferences.router)
api_router.include_router(search.router)
api_router.include_router(dashboard.router)
api_router.include_router(currency.router)
api_router.include_router(media.router)
api_router.include_router(places.router)

__all__ = ["api_router"]
