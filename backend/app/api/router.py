"""Versioned API router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import health, history, review, travel
from app.core.constants import API_PREFIX

api_router = APIRouter(prefix=API_PREFIX)
api_router.include_router(health.router)
api_router.include_router(travel.router)
api_router.include_router(history.router)
api_router.include_router(review.router)

__all__ = ["api_router"]
