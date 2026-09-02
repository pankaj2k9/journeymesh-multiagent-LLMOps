"""HTTP security: headers, size limits, rate limiting and safe errors."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings, reload_settings
from app.main import app
from app.security.rate_limit import InMemoryRateLimiter, reset_rate_limiter
from app.security.secret_manager import configured_secrets, get_secret, mask


def test_security_headers_are_present(client):
    response = client.get("/api/v1/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert "Server" not in response.headers


def test_every_response_carries_a_request_id(client):
    response = client.get("/api/v1/health")
    assert response.headers["X-Request-ID"]


def test_an_oversized_payload_is_refused(client):
    limit = get_settings().max_request_size
    response = client.post(
        "/api/v1/trips/plan",
        content=b"x" * (limit + 1024),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["error"] == "payload_too_large"


def test_the_rate_limiter_counts_within_a_window():
    limiter = InMemoryRateLimiter(limit=2, window_seconds=60)
    assert limiter.hit("a").allowed
    assert limiter.hit("a").allowed
    third = limiter.hit("a")
    assert not third.allowed
    assert third.remaining == 0
    # A different client has its own bucket.
    assert limiter.hit("b").allowed


def test_the_api_returns_429_when_the_limit_is_exceeded(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "2")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    reload_settings()
    reset_rate_limiter()

    try:
        with TestClient(app) as limited:
            payload = {"query": "Plan a trip to Rome for a weekend", "destination": "Rome"}
            statuses = [
                limited.post("/api/v1/trips/plan", json=payload).status_code for _ in range(4)
            ]
        assert 429 in statuses
    finally:
        monkeypatch.undo()
        reload_settings()
        reset_rate_limiter()


def test_cors_is_restricted_to_the_configured_origins(client):
    response = client.options(
        "/api/v1/trips/plan",
        headers={
            "Origin": "https://not-allowed.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in {key.lower() for key in response.headers}


def test_secrets_are_reported_without_being_revealed():
    report = configured_secrets()
    assert set(report) >= {"groq_api_key", "database_url"}
    assert mask("gsk_supersecretvalue") .endswith("alue")
    assert mask("gsk_supersecretvalue").startswith("*")
    assert mask(None) == "not_configured"


def test_unknown_secrets_cannot_be_requested():
    with pytest.raises(KeyError):
        get_secret("aws_root_password")


def test_an_internal_error_does_not_leak_a_traceback(monkeypatch):
    from app.services import travel_service

    async def explode(self, request, request_id=None):  # noqa: ANN001
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(travel_service.TravelService, "plan", explode)

    # The test client re-raises server errors by default; disable that so the
    # response the caller would actually receive can be inspected.
    with TestClient(app, raise_server_exceptions=False) as strict:
        response = strict.post(
            "/api/v1/trips/plan",
            json={"query": "Plan a 3-day trip to Rome", "destination": "Rome"},
        )
    assert response.status_code == 500
    assert "secret internal detail" not in response.text
    assert response.json()["error"] == "internal_error"
