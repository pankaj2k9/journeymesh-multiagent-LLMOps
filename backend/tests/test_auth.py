"""Accounts, tokens and role gating."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.constants import ROLE_ADMIN, ROLE_SUPPORT, ROLE_USER
from app.db.database import session_scope
from app.db.models import Trip, User
from app.security import auth

GOOD_PASSWORD = "a-long-enough-passphrase"


def register(client: TestClient, email: str, **extra: object) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": GOOD_PASSWORD, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestRegistration:
    def test_registering_returns_a_token_pair_and_the_account(self, client: TestClient) -> None:
        payload = register(client, "first@example.com", display_name="First")
        assert payload["token_type"] == "bearer"
        assert payload["access_token"] and payload["refresh_token"]
        assert payload["expires_in"] > 0
        assert payload["user"]["email"] == "first@example.com"
        assert payload["user"]["display_name"] == "First"

    def test_the_first_account_is_the_administrator(self, client: TestClient) -> None:
        assert register(client, "first@example.com")["user"]["role"] == ROLE_ADMIN
        assert register(client, "second@example.com")["user"]["role"] == ROLE_USER

    def test_a_role_cannot_be_asked_for_in_the_request(self, client: TestClient) -> None:
        register(client, "first@example.com")
        payload = register(client, "climber@example.com", role="ADMIN")
        assert payload["user"]["role"] == ROLE_USER

    def test_the_address_is_normalised(self, client: TestClient) -> None:
        register(client, "Mixed.Case@Example.com")
        assert register.__name__  # keep the helper referenced
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "mixed.case@example.com", "password": GOOD_PASSWORD},
        )
        assert response.status_code == 200

    def test_the_same_address_cannot_register_twice(self, client: TestClient) -> None:
        register(client, "taken@example.com")
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "TAKEN@example.com", "password": GOOD_PASSWORD},
        )
        assert response.status_code == 409
        assert response.json()["error"] == "email_already_registered"

    @pytest.mark.parametrize("password", ["short", "aaaaaaaaaaaaaaaa", "ababababababab"])
    def test_weak_passwords_are_refused(self, client: TestClient, password: str) -> None:
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "weak@example.com", "password": password},
        )
        assert response.status_code == 422

    def test_a_password_is_hashed_exactly_as_typed(self, client: TestClient) -> None:
        """The base model strips strings; a password must not be one of them."""
        padded = "  a padded passphrase  "
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "padded@example.com", "password": padded},
        )
        assert response.status_code == 201

        trimmed = client.post(
            "/api/v1/auth/login",
            json={"email": "padded@example.com", "password": padded.strip()},
        )
        assert trimmed.status_code == 401

        exact = client.post(
            "/api/v1/auth/login",
            json={"email": "padded@example.com", "password": padded},
        )
        assert exact.status_code == 200

    def test_the_password_is_never_stored_or_returned(self, client: TestClient) -> None:
        payload = register(client, "private@example.com")
        assert "password" not in payload["user"]
        with session_scope() as session:
            user = session.query(User).filter_by(email="private@example.com").one()
            assert GOOD_PASSWORD not in user.password_hash
            assert user.password_hash.startswith("$argon2")


class TestLogin:
    def test_signing_in_returns_a_fresh_pair(self, client: TestClient) -> None:
        register(client, "user@example.com")
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "user@example.com", "password": GOOD_PASSWORD},
        )
        assert response.status_code == 200
        assert response.json()["user"]["last_login_at"] is not None

    def test_an_unknown_address_and_a_wrong_password_are_indistinguishable(
        self, client: TestClient
    ) -> None:
        register(client, "user@example.com")
        wrong = client.post(
            "/api/v1/auth/login",
            json={"email": "user@example.com", "password": "definitely-not-it"},
        )
        unknown = client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": GOOD_PASSWORD},
        )
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json()["message"] == unknown.json()["message"]
        assert wrong.json()["error"] == unknown.json()["error"] == "invalid_credentials"

    def test_a_suspended_account_cannot_sign_in(self, client: TestClient) -> None:
        register(client, "user@example.com")
        with session_scope() as session:
            session.query(User).filter_by(email="user@example.com").one().status = "suspended"
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "user@example.com", "password": GOOD_PASSWORD},
        )
        assert response.status_code == 403
        assert response.json()["error"] == "account_suspended"


class TestTokens:
    def test_me_requires_a_token(self, client: TestClient) -> None:
        assert client.get("/api/v1/auth/me").status_code == 401

    def test_me_returns_the_signed_in_account(self, client: TestClient) -> None:
        payload = register(client, "user@example.com")
        response = client.get("/api/v1/auth/me", headers=bearer(payload["access_token"]))
        assert response.status_code == 200
        assert response.json()["id"] == payload["user"]["id"]

    def test_a_refresh_token_is_not_accepted_as_an_access_token(
        self, client: TestClient
    ) -> None:
        payload = register(client, "user@example.com")
        response = client.get("/api/v1/auth/me", headers=bearer(payload["refresh_token"]))
        assert response.status_code == 401

    def test_a_garbage_token_is_not_a_crash(self, client: TestClient) -> None:
        assert client.get("/api/v1/auth/me", headers=bearer("nonsense")).status_code == 401

    def test_refreshing_returns_a_new_pair(self, client: TestClient) -> None:
        payload = register(client, "user@example.com")
        response = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": payload["refresh_token"]}
        )
        assert response.status_code == 200
        assert response.json()["user"]["id"] == payload["user"]["id"]

    def test_signing_out_everywhere_strands_existing_tokens(
        self, client: TestClient
    ) -> None:
        payload = register(client, "user@example.com")
        headers = bearer(payload["access_token"])
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

        assert client.post("/api/v1/auth/sign-out-everywhere", headers=headers).status_code == 204

        assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
        refreshed = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": payload["refresh_token"]}
        )
        assert refreshed.status_code == 401

    def test_an_expired_token_is_rejected(self, client: TestClient) -> None:
        from datetime import datetime, timedelta, timezone

        payload = register(client, "user@example.com")
        stale = auth.create_token(
            user_id=payload["user"]["id"],
            role=ROLE_ADMIN,
            token_version=1,
            issued_at=datetime.now(timezone.utc) - timedelta(days=30),
        )
        assert client.get("/api/v1/auth/me", headers=bearer(stale)).status_code == 401


class TestAnonymousSessionAdoption:
    def _plan_anonymously(self, client: TestClient, plan_payload: dict) -> str:
        response = client.post(
            "/api/v1/trips/plan",
            json=plan_payload,
            headers={"X-JourneyMesh-Session": plan_payload["session_id"]},
        )
        assert response.status_code == 200, response.text
        return response.json()["trip_id"]

    def test_registering_adopts_the_sessions_trips(
        self, client: TestClient, plan_payload: dict
    ) -> None:
        trip_id = self._plan_anonymously(client, plan_payload)
        payload = register(
            client, "late@example.com", session_id=plan_payload["session_id"]
        )
        assert payload["claimed_trips"] == 1

        with session_scope() as session:
            assert session.get(Trip, trip_id).user_id == payload["user"]["id"]

    def test_a_trip_that_already_has_an_owner_is_never_transferred(
        self, client: TestClient, plan_payload: dict
    ) -> None:
        trip_id = self._plan_anonymously(client, plan_payload)
        owner = register(client, "owner@example.com", session_id=plan_payload["session_id"])

        # Somebody else guesses the session id and tries to claim it.
        thief = register(client, "thief@example.com")
        response = client.post(
            "/api/v1/auth/claim-session",
            json={"session_id": plan_payload["session_id"]},
            headers=bearer(thief["access_token"]),
        )
        assert response.status_code == 200
        assert response.json()["claimed_trips"] == 0

        with session_scope() as session:
            assert session.get(Trip, trip_id).user_id == owner["user"]["id"]

    def test_planning_while_signed_in_records_the_owner(
        self, client: TestClient, plan_payload: dict
    ) -> None:
        payload = register(client, "owner@example.com")
        response = client.post(
            "/api/v1/trips/plan",
            json=plan_payload,
            headers=bearer(payload["access_token"]),
        )
        assert response.status_code == 200
        with session_scope() as session:
            trip = session.get(Trip, response.json()["trip_id"])
            assert trip.user_id == payload["user"]["id"]

    def test_planning_anonymously_still_works(
        self, client: TestClient, plan_payload: dict
    ) -> None:
        trip_id = self._plan_anonymously(client, plan_payload)
        with session_scope() as session:
            assert session.get(Trip, trip_id).user_id is None


class TestRoleGating:
    def test_ranks_are_ordered_so_an_admin_satisfies_support(self) -> None:
        from app.core.constants import ROLE_RANK

        assert ROLE_RANK[ROLE_ADMIN] > ROLE_RANK[ROLE_SUPPORT] > ROLE_RANK[ROLE_USER]

    def test_require_role_refuses_an_account_below_the_bar(self, client: TestClient) -> None:
        from fastapi import Depends, FastAPI

        from app.api.deps import require_role
        from app.core.exceptions import TravelCrewError
        from app.main import app as main_app

        # Mounted on the real app so the error handler shapes the response.
        @main_app.get("/api/v1/_test/admin-only", include_in_schema=False)
        def _admin_only(user=Depends(require_role(ROLE_ADMIN))) -> dict[str, str]:  # noqa: ANN001
            return {"ok": user.role}

        register(client, "admin@example.com")
        member = register(client, "member@example.com")

        denied = client.get(
            "/api/v1/_test/admin-only", headers=bearer(member["access_token"])
        )
        assert denied.status_code == 403
        assert denied.json()["error"] == "permission_denied"

        assert client.get("/api/v1/_test/admin-only").status_code == 401

        assert isinstance(FastAPI, type) and issubclass(TravelCrewError, Exception)


class TestTravelerProfiles:
    def test_a_traveller_can_be_saved_and_listed(self, client: TestClient) -> None:
        payload = register(client, "user@example.com")
        headers = bearer(payload["access_token"])

        created = client.post(
            "/api/v1/auth/travelers",
            json={
                "full_name": "Ayesha Rahman",
                "traveler_type": "CHILD",
                "date_of_birth": "2018-04-02",
                "passport_country": "bd",
            },
            headers=headers,
        )
        assert created.status_code == 201
        assert created.json()["passport_country"] == "BD"

        listed = client.get("/api/v1/auth/travelers", headers=headers)
        assert listed.status_code == 200
        assert listed.json()["total"] == 1

    def test_traveller_profiles_need_an_account(self, client: TestClient) -> None:
        assert client.get("/api/v1/auth/travelers").status_code == 401


class TestSigningKey:
    """A weak signing key must fail loudly rather than sign weakly."""

    def test_a_short_key_is_refused(self) -> None:
        from app.core.config import Settings

        settings = Settings(jwt_secret_key="too-short", app_env="production")
        with pytest.raises(RuntimeError, match="at least 32 bytes"):
            _ = settings.jwt_signing_key

    def test_production_without_a_key_is_refused(self) -> None:
        from app.core.config import Settings

        settings = Settings(jwt_secret_key=None, app_env="production")
        with pytest.raises(RuntimeError, match="JWT_SECRET_KEY must be set"):
            _ = settings.jwt_signing_key

    def test_development_derives_a_stable_key(self) -> None:
        from app.core.config import Settings

        first = Settings(jwt_secret_key=None, app_env="development").jwt_signing_key
        second = Settings(jwt_secret_key=None, app_env="development").jwt_signing_key
        assert first == second
        assert len(first.encode()) >= 32
