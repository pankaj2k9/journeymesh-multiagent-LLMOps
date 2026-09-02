"""Health endpoint and application wiring."""

from __future__ import annotations


def test_health_is_cheap_and_reports_status(client):
    """The platform health check must be fast and touch nothing external."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "JourneyMesh API"
    assert payload["app"] == "JourneyMesh"
    assert payload["tagline"] == "Every journey, intelligently connected."
    # No provider, MCP or database work unless it was asked for.
    assert payload["checks"] == {}


def test_health_does_not_open_a_database_connection(client, monkeypatch):
    from app.db import database

    def explode() -> None:
        raise AssertionError("the health endpoint must not create an engine")

    monkeypatch.setattr(database, "get_engine", explode)
    assert client.get("/api/v1/health").status_code == 200


def test_verbose_health_reports_configuration(client):
    payload = client.get("/api/v1/health?verbose=true").json()
    assert "providers" in payload["checks"]
    assert "mcp" in payload["checks"]
    assert "observability" in payload["checks"]
    assert payload["checks"]["observability"]["langsmith"]["enabled"] is False


def test_health_never_exposes_a_secret(client):
    body = client.get("/api/v1/health?verbose=true").text
    for marker in ("GROQ_API_KEY=", "postgres://", "sk-", "gsk_"):
        assert marker not in body


def test_root_describes_the_service(client):
    payload = client.get("/").json()
    assert payload["app"] == "JourneyMesh"
    assert payload["api"] == "/api/v1"


def test_openapi_document_is_available(client):
    payload = client.get("/openapi.json").json()
    assert "/api/v1/trips/plan" in payload["paths"]
    assert "/api/v1/trips/{trip_id}/approve" in payload["paths"]
    assert "/api/v1/trips/{trip_id}/request-changes" in payload["paths"]
