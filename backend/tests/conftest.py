"""Shared pytest fixtures.

Environment defaults are set before ``app.core.config`` is imported so the
suite runs deterministically: no provider credentials, no external network,
rate limiting out of the way, and a fresh in-memory database per test.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("TAVILY_API_KEY", "")
os.environ.setdefault("AVIATIONSTACK_API_KEY", "")
os.environ.setdefault("OPENWEATHER_API_KEY", "")
os.environ.setdefault("MCP_WEATHER_TRANSPORT", "disabled")
os.environ.setdefault("RATE_LIMIT_REQUESTS", "10000")
os.environ.setdefault("MAX_REVISION_COUNT", "3")
os.environ.setdefault("LOG_LEVEL", "ERROR")
os.environ.setdefault("ENABLE_MOCK_DATA", "true")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import models  # noqa: E402
from app.db.database import get_engine, session_scope  # noqa: E402
from app.graph.travel_graph import TravelWorkflow, reset_workflow  # noqa: E402
from app.guardrails.tool_guard import get_tool_guard  # noqa: E402
from app.main import app  # noqa: E402
from app.mcp.client import MCPClient, reset_mcp_client  # noqa: E402
from app.observability import metrics  # noqa: E402
from app.schemas.travel import TripPlanRequest  # noqa: E402
from app.security.rate_limit import reset_rate_limiter  # noqa: E402
from app.services.llm_service import reset_llm_service  # noqa: E402


@pytest.fixture(autouse=True)
def clean_state() -> Iterator[None]:
    """Give every test a fresh database, guard, workflow and metrics."""
    engine = get_engine()
    models.Base.metadata.drop_all(bind=engine)
    models.Base.metadata.create_all(bind=engine)

    get_tool_guard().reset()
    reset_mcp_client()
    reset_llm_service()
    reset_workflow()
    reset_rate_limiter()
    metrics.reset()
    yield
    reset_workflow()
    reset_rate_limiter()


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session() -> Iterator[Session]:
    with session_scope() as session:
        yield session


@pytest.fixture()
def workflow() -> TravelWorkflow:
    """A workflow with its own tool client, isolated from other tests."""
    return TravelWorkflow(mcp_client=MCPClient())


@pytest.fixture()
def family_request() -> TripPlanRequest:
    return TripPlanRequest(
        query=(
            "Plan a relaxing 5-day family trip from Dhaka to Singapore with a budget of "
            "$3000. We like nature, local food and child-friendly activities."
        ),
        origin="Dhaka",
        destination="Singapore",
        departure_date="2027-01-10",
        return_date="2027-01-14",
        travelers=3,
        budget=3000,
        currency="USD",
        travel_style="family",
        interests=["food", "nature", "family_activities"],
        response_language="en",
        session_id="test-session",
    )


@pytest.fixture()
def plan_payload() -> dict:
    return {
        "query": (
            "Plan a relaxing 5-day family trip from Dhaka to Singapore with a budget of "
            "$3000. We like nature and local food."
        ),
        "origin": "Dhaka",
        "destination": "Singapore",
        "departure_date": "2027-01-10",
        "return_date": "2027-01-14",
        "travelers": 3,
        "budget": 3000,
        "currency": "USD",
        "travel_style": "family",
        "interests": ["food", "nature"],
        "response_language": "en",
        "session_id": "test-session",
    }
