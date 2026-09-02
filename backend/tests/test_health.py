"""Health endpoint and application wiring."""

from __future__ import annotations


def test_health_reports_status_and_configuration(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["app"] == "JourneyMesh"
    assert payload["tagline"] == "Every journey, intelligently connected."
    assert "providers" in payload["checks"]
    assert "mcp" in payload["checks"]


def test_health_never_exposes_a_secret(client):
    body = client.get("/api/v1/health").text
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
