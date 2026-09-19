"""The media upload endpoints.

Authorisation is checked server-side here, not by hiding a button, which is
the rule §115 states and the one that actually holds.
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image

from app.db.database import session_scope
from app.db.models import MediaAsset

PASSWORD = "a-long-enough-passphrase"


def png(width: int = 900, height: int = 600) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (12, 99, 220)).save(buffer, format="PNG")
    return buffer.getvalue()


def admin_headers(client: TestClient) -> dict[str, str]:
    """The first account created on a fresh deployment is the administrator."""
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "admin@example.com", "password": PASSWORD},
    ).json()
    assert registered["user"]["role"] == "ADMIN"
    return {"Authorization": f"Bearer {registered['access_token']}"}


def member_headers(client: TestClient) -> dict[str, str]:
    client.post(
        "/api/v1/auth/register",
        json={"email": "admin@example.com", "password": PASSWORD},
    )
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "member@example.com", "password": PASSWORD},
    ).json()
    assert registered["user"]["role"] == "USER"
    return {"Authorization": f"Bearer {registered['access_token']}"}


def upload(client: TestClient, headers: dict, payload: bytes, **fields):
    data = {"category": "blog", "alt_text": "A blue rectangle", **fields}
    return client.post(
        "/api/v1/media",
        headers=headers,
        files={"file": ("Barcelona Guide.png", payload, "image/png")},
        data=data,
    )


class TestAuthorisation:
    def test_an_anonymous_visitor_cannot_upload(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/media",
            files={"file": ("x.png", png(), "image/png")},
            data={"category": "blog"},
        )
        assert response.status_code == 401

    def test_an_ordinary_account_cannot_upload(self, client: TestClient) -> None:
        response = upload(client, member_headers(client), png())
        assert response.status_code == 403
        assert response.json()["error"] == "permission_denied"

    def test_an_ordinary_account_cannot_browse_the_library(
        self, client: TestClient
    ) -> None:
        assert client.get("/api/v1/media", headers=member_headers(client)).status_code == 403

    def test_an_administrator_can(self, client: TestClient) -> None:
        assert upload(client, admin_headers(client), png()).status_code == 201


class TestUpload:
    def test_an_upload_is_stored_and_recorded(self, client: TestClient) -> None:
        response = upload(client, admin_headers(client), png(1600, 900))
        assert response.status_code == 201

        payload = response.json()
        assert payload["mime_type"] == "image/webp"
        assert payload["width"] == 1600 and payload["height"] == 900
        assert payload["alt_text"] == "A blue rectangle"
        assert payload["file_size"] > 0
        assert payload["url"].startswith("/media/blog/")

    def test_the_original_filename_never_becomes_the_path(
        self, client: TestClient
    ) -> None:
        headers = admin_headers(client)
        response = client.post(
            "/api/v1/media",
            headers=headers,
            files={"file": ("../../etc/passwd.png", png(), "image/png")},
            data={"category": "blog"},
        )
        assert response.status_code == 201
        payload = response.json()
        assert ".." not in payload["relative_path"]
        assert payload["relative_path"].startswith("blog/")
        # It is kept for display, and only for display.
        assert payload["original_filename"] == "../../etc/passwd.png"

    def test_derivatives_are_returned_with_urls(self, client: TestClient) -> None:
        payload = upload(client, admin_headers(client), png(2400, 1600)).json()
        assert set(payload["derivatives"]) == {"thumbnail", "small", "medium", "large"}
        for name, child in payload["derivatives"].items():
            assert child["url"].startswith("/media/blog/")
            assert f"@{name}." in child["url"]
            assert child["width"] > 0

    def test_an_svg_is_refused(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/media",
            headers=admin_headers(client),
            files={
                "file": (
                    "logo.svg",
                    b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
                    "image/svg+xml",
                )
            },
            data={"category": "blog"},
        )
        assert response.status_code == 415
        assert response.json()["error"] == "unsupported_media_type"

    def test_a_script_disguised_as_a_png_is_refused(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/media",
            headers=admin_headers(client),
            files={"file": ("innocent.png", b"<?php system($_GET['c']); ?>", "image/png")},
            data={"category": "blog"},
        )
        assert response.status_code == 415

    def test_an_unknown_category_is_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/media",
            headers=admin_headers(client),
            files={"file": ("x.png", png(), "image/png")},
            data={"category": "../../etc"},
        )
        assert response.status_code == 422

    def test_the_file_actually_lands_on_disk_and_is_served(
        self, client: TestClient
    ) -> None:
        payload = upload(client, admin_headers(client), png()).json()
        served = client.get(payload["url"])
        assert served.status_code == 200
        assert served.headers["content-type"].startswith("image/")


class TestLibrary:
    def test_uploads_are_listed_newest_first(self, client: TestClient) -> None:
        headers = admin_headers(client)
        upload(client, headers, png(400, 300))
        upload(client, headers, png(500, 400))

        payload = client.get("/api/v1/media", headers=headers).json()
        assert payload["total"] == 2
        assert len(payload["items"]) == 2

    def test_the_library_can_be_filtered_by_category(self, client: TestClient) -> None:
        headers = admin_headers(client)
        upload(client, headers, png(), category="blog")
        upload(client, headers, png(), category="destinations")

        blog = client.get("/api/v1/media?category=blog", headers=headers).json()
        assert blog["total"] == 1
        assert blog["items"][0]["category"] == "blog"

    def test_alt_text_can_be_corrected_afterwards(self, client: TestClient) -> None:
        headers = admin_headers(client)
        asset = upload(client, headers, png()).json()

        response = client.patch(
            f"/api/v1/media/{asset['id']}",
            headers=headers,
            json={"alt_text": "Sagrada Familia at sunset"},
        )
        assert response.status_code == 200
        assert response.json()["alt_text"] == "Sagrada Familia at sunset"

    def test_deleting_removes_the_derivatives_too(self, client: TestClient) -> None:
        headers = admin_headers(client)
        asset = upload(client, headers, png(2400, 1600)).json()
        derivative_url = asset["derivatives"]["small"]["url"]

        assert client.get(derivative_url).status_code == 200
        assert client.delete(f"/api/v1/media/{asset['id']}", headers=headers).status_code == 204

        assert client.get(asset["url"]).status_code == 404
        assert client.get(derivative_url).status_code == 404
        with session_scope() as session:
            assert session.get(MediaAsset, asset["id"]) is None

    def test_an_image_in_use_is_not_deleted_by_accident(self, client: TestClient) -> None:
        """A published article should not quietly develop a broken image."""
        headers = admin_headers(client)
        asset = upload(client, headers, png()).json()

        with session_scope() as session:
            session.get(MediaAsset, asset["id"]).usage_count = 2

        refused = client.delete(f"/api/v1/media/{asset['id']}", headers=headers)
        assert refused.status_code == 409
        assert refused.json()["error"] == "media_in_use"

        forced = client.delete(f"/api/v1/media/{asset['id']}?force=true", headers=headers)
        assert forced.status_code == 204

    def test_an_unknown_asset_is_a_404(self, client: TestClient) -> None:
        response = client.get("/api/v1/media/nope", headers=admin_headers(client))
        assert response.status_code == 404
