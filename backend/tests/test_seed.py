"""The start-up administrator seed."""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.constants import ROLE_ADMIN, ROLE_USER, USER_ACTIVE, USER_SUSPENDED
from app.db.database import session_scope
from app.db.repositories import UserRepository
from app.db.seed import seed_admin, seed_demo_user
from app.security import auth

EMAIL = "admin@travelcrew.dev"
PASSWORD = "a-long-enough-password"


@pytest.fixture
def admin_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ADMIN_EMAIL", EMAIL)
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _user(email: str = EMAIL):
    with session_scope() as session:
        user = UserRepository(session).by_email(email)
        if user is None:
            return None
        session.expunge(user)
        return user


def test_nothing_happens_without_configuration() -> None:
    assert seed_admin() == "skipped"


def test_creates_the_admin_once(admin_env) -> None:
    assert seed_admin() == "created"
    assert seed_admin() == "unchanged"

    user = _user()
    assert user is not None
    assert user.role == ROLE_ADMIN
    assert user.status == USER_ACTIVE
    assert auth.verify_password(PASSWORD, user.password_hash)


def test_the_seeded_admin_can_sign_in(admin_env, client) -> None:
    seed_admin()
    response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200
    assert response.json()["user"]["role"] == ROLE_ADMIN


def test_promotes_an_existing_account_without_touching_its_password(admin_env) -> None:
    with session_scope() as session:
        UserRepository(session).create(
            email=EMAIL,
            password_hash=auth.hash_password("the-password-they-chose"),
            role=ROLE_USER,
            status=USER_SUSPENDED,
        )

    assert seed_admin() == "promoted"

    user = _user()
    assert user.role == ROLE_ADMIN
    assert user.status == USER_ACTIVE
    assert auth.verify_password("the-password-they-chose", user.password_hash)


@pytest.mark.parametrize(
    ("email", "password"),
    [("admin@travelcrew.local", PASSWORD), (EMAIL, "short")],
)
def test_refuses_an_account_nobody_could_sign_in_to(
    monkeypatch: pytest.MonkeyPatch, email: str, password: str
) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", email)
    monkeypatch.setenv("ADMIN_PASSWORD", password)
    get_settings.cache_clear()
    try:
        assert seed_admin() == "rejected"
        assert _user(email) is None
    finally:
        get_settings.cache_clear()


DEMO_EMAIL = "traveller@travelcrew.dev"
DEMO_PASSWORD = "another-long-password"


@pytest.fixture
def demo_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEMO_USER_EMAIL", DEMO_EMAIL)
    monkeypatch.setenv("DEMO_USER_PASSWORD", DEMO_PASSWORD)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_demo_user_is_skipped_without_configuration() -> None:
    assert seed_demo_user() == "skipped"


def test_creates_the_demo_traveller_as_an_ordinary_user(demo_env) -> None:
    assert seed_demo_user() == "created"
    assert seed_demo_user() == "unchanged"
    assert _user(DEMO_EMAIL).role == ROLE_USER


def test_start_up_seeds_a_demo_traveller_who_can_sign_in(demo_env, client) -> None:
    # The client fixture starts the app, and start-up runs the seed.
    assert seed_demo_user() == "unchanged"

    response = client.post(
        "/api/v1/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}
    )
    assert response.status_code == 200
    assert response.json()["user"]["role"] == ROLE_USER


def test_never_reactivates_a_suspended_demo_traveller(demo_env) -> None:
    with session_scope() as session:
        UserRepository(session).create(
            email=DEMO_EMAIL,
            password_hash=auth.hash_password(DEMO_PASSWORD),
            role=ROLE_USER,
            status=USER_SUSPENDED,
        )

    assert seed_demo_user() == "unchanged"
    assert _user(DEMO_EMAIL).status == USER_SUSPENDED
