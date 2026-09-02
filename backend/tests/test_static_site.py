"""FastAPI serving the React build.

In production one container answers both the interface and the API, so these
tests assert the routing contract: /api belongs to FastAPI, everything else
belongs to React Router, and a browser refresh on a nested route works.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import reload_settings

ROOT = Path(__file__).resolve().parents[2]

SHELL = (
    "<!doctype html><html><head><title>JourneyMesh</title></head>"
    '<body><div id="root"></div><script src="/assets/index-abc123.js"></script></body></html>'
)


@pytest.fixture()
def spa_client(tmp_path: Path, monkeypatch):
    """An application configured to serve a small stand-in React build."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(SHELL, encoding="utf-8")
    (dist / "assets" / "index-abc123.js").write_text("console.log('journeymesh');", encoding="utf-8")
    (dist / "journeymesh.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")

    monkeypatch.setenv("SERVE_FRONTEND", "true")
    monkeypatch.setenv("FRONTEND_DIST_DIR", str(dist))
    reload_settings()

    from app.main import create_app

    with TestClient(create_app()) as client:
        yield client

    monkeypatch.undo()
    reload_settings()


def test_the_root_path_returns_the_react_shell(spa_client):
    response = spa_client.get("/")
    assert response.status_code == 200
    assert '<div id="root">' in response.text
    assert response.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize(
    "route",
    ["/trip/abc-123", "/history", "/about", "/settings", "/trip/abc-123/anything"],
)
def test_nested_routes_survive_a_refresh(spa_client, route):
    """A refresh on a client-side route must not 404."""
    response = spa_client.get(route)
    assert response.status_code == 200
    assert '<div id="root">' in response.text


def test_api_routes_still_reach_fastapi(spa_client):
    response = spa_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["service"] == "JourneyMesh API"


def test_an_unknown_api_route_is_a_404_not_the_spa(spa_client):
    response = spa_client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert '<div id="root">' not in response.text


def test_the_openapi_document_and_docs_are_untouched(spa_client):
    assert spa_client.get("/openapi.json").status_code == 200
    assert spa_client.get("/docs").status_code == 200


def test_hashed_assets_are_served_and_cached_forever(spa_client):
    response = spa_client.get("/assets/index-abc123.js")
    assert response.status_code == 200
    assert "journeymesh" in response.text
    assert "immutable" in response.headers["cache-control"]


def test_a_real_file_at_the_root_is_served(spa_client):
    response = spa_client.get("/journeymesh.svg")
    assert response.status_code == 200
    assert "svg" in response.text


def test_path_traversal_returns_the_shell_and_never_a_system_file(spa_client):
    for attempt in ("/../../etc/passwd", "/assets/../../../etc/passwd", "/%2e%2e/etc/passwd"):
        response = spa_client.get(attempt)
        assert "root:x:" not in response.text


def test_the_api_runs_without_a_build(client):
    """With no build present the API keeps its own root route."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["app"] == "JourneyMesh"


def test_planning_still_works_through_the_combined_application(spa_client, plan_payload):
    response = spa_client.post("/api/v1/trips/plan", json=plan_payload)
    assert response.status_code == 200
    body = response.json()
    assert body["review_status"] == "awaiting_review"
    assert body["itinerary"]["days"]


# ---------------------------------------------------------------------------
# Theme: the inline initialiser is allowed by hash, never by 'unsafe-inline'
# ---------------------------------------------------------------------------
def test_the_csp_allows_the_theme_script_by_hash_only():
    from app.security.headers import APP_CONTENT_SECURITY_POLICY, THEME_INIT_SCRIPT_HASH

    assert THEME_INIT_SCRIPT_HASH.startswith("sha256-")
    assert f"'{THEME_INIT_SCRIPT_HASH}'" in APP_CONTENT_SECURITY_POLICY
    assert "unsafe-inline" not in APP_CONTENT_SECURITY_POLICY.split("style-src")[0]


def test_the_csp_hash_matches_the_script_index_html_actually_ships():
    """A changed initialiser must not silently start being blocked."""
    import base64
    import hashlib
    import re

    index = ROOT / "frontend" / "index.html"
    if not index.is_file():  # pragma: no cover - the image ships no source
        pytest.skip("frontend/index.html is not part of this build")

    from app.security.headers import THEME_INIT_SCRIPT_HASH

    html = index.read_text(encoding="utf-8")
    match = re.search(r"<script>(\(function\(\)\{try\{var k=.*?)</script>", html, re.S)
    assert match, "index.html must contain the inline theme initialiser"

    digest = base64.b64encode(hashlib.sha256(match.group(1).encode()).digest()).decode()
    assert f"sha256-{digest}" == THEME_INIT_SCRIPT_HASH, (
        "the theme script changed - update THEME_INIT_SCRIPT_HASH in "
        "backend/app/security/headers.py and frontend/nginx.conf"
    )


def test_the_theme_script_runs_before_the_bundle():
    index = ROOT / "frontend" / "index.html"
    if not index.is_file():  # pragma: no cover
        pytest.skip("frontend/index.html is not part of this build")

    html = index.read_text(encoding="utf-8")
    # If the bundle loaded first there would be a flash of the wrong theme.
    assert html.index("journeymesh_theme") < html.index("/src/main.tsx")


def test_a_served_page_carries_the_theme_aware_policy(spa_client):
    policy = spa_client.get("/").headers["content-security-policy"]
    assert "script-src 'self' 'sha256-" in policy
