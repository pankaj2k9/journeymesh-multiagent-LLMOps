"""Deployment configuration.

These tests protect the promises the deployment makes: the port comes from the
environment, the database provider is defined only by DATABASE_URL, the CI
pipeline gates deployment, and no secret is committed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import Settings, reload_settings
from app.db.database import apply_ssl_mode, configured_backend, engine_options

ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Port and binding
# ---------------------------------------------------------------------------
def test_the_port_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("PORT", "10000")
    settings = reload_settings()
    assert settings.port == 10000
    monkeypatch.undo()
    reload_settings()


def test_the_port_falls_back_to_8000_locally():
    assert Settings(port=8000).port == 8000


def test_the_entrypoint_binds_all_interfaces_on_the_platform_port():
    entrypoint = (ROOT / "backend" / "docker-entrypoint.sh").read_text()
    assert 'PORT="${PORT:-8000}"' in entrypoint
    assert "--host 0.0.0.0" in entrypoint
    # The production port must never be hard-coded.
    assert "--port 8000" not in entrypoint


# ---------------------------------------------------------------------------
# Database provider independence
# ---------------------------------------------------------------------------
def test_the_database_provider_is_only_ever_database_url():
    """No hostname, user or password of any provider may appear in the code."""
    banned = (
        "neon.tech",
        "render.com",
        "onrender.com",
        "railway.app",
        "railway.internal",
        "supabase.co",
        "rds.amazonaws",
    )
    for path in (ROOT / "backend" / "app").rglob("*.py"):
        content = path.read_text().lower()
        for needle in banned:
            assert needle not in content, f"{path} hard-codes {needle}"


def test_a_managed_database_url_gets_tls():
    url = apply_ssl_mode("postgresql+psycopg://user:pw@db.internal.example.com:5432/journeymesh")
    assert "sslmode=require" in url


def test_an_explicit_ssl_mode_is_respected():
    url = "postgresql+psycopg://user:pw@host.example/db?sslmode=verify-full"
    assert apply_ssl_mode(url) == url


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "db", "postgres"])
def test_a_local_database_is_left_alone(host):
    url = f"postgresql+psycopg://user:pw@{host}:5432/journeymesh"
    assert apply_ssl_mode(url) == url


def test_the_pool_is_bounded_and_pre_pings():
    options = engine_options("postgresql://example")
    assert options["pool_pre_ping"] is True
    assert options["pool_size"] >= 1
    assert options["pool_recycle"] > 0
    assert options["connect_args"]["connect_timeout"] > 0
    assert "statement_timeout" in options["connect_args"]["options"]


def test_url_variants_are_normalised_for_sqlalchemy_and_the_checkpointer(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pw@host.example:5432/journeymesh")
    settings = reload_settings()
    assert settings.sqlalchemy_url.startswith("postgresql+psycopg://")
    assert settings.psycopg_url.startswith("postgresql://")
    monkeypatch.undo()
    reload_settings()


def test_without_a_database_url_the_fallback_is_reported_honestly():
    assert configured_backend() == "ephemeral_sqlite"


# ---------------------------------------------------------------------------
# Container and CI configuration
# ---------------------------------------------------------------------------
def test_the_production_image_is_multi_stage_and_ships_only_the_build():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "AS frontend-builder" in dockerfile
    assert "AS backend-builder" in dockerfile
    assert "AS application" in dockerfile
    # The built assets travel; the source and node_modules do not.
    assert "COPY --from=frontend-builder" in dockerfile
    assert "/build/frontend/dist ./static" in dockerfile
    assert "USER journeymesh" in dockerfile
    # The platform probes the cheap top-level path.
    assert "/health" in dockerfile


def test_the_build_context_excludes_secrets_and_caches():
    ignore = (ROOT / ".dockerignore").read_text()
    for entry in (".env", ".git/", "frontend/node_modules/", "backend/.venv/", "__pycache__"):
        assert entry in ignore


def test_no_environment_file_is_tracked_by_git():
    gitignore = (ROOT / ".gitignore").read_text()
    assert ".env" in gitignore


def test_no_deploy_credential_is_committed():
    """Deployment credentials belong in GitHub secrets and nowhere else."""
    # Assembled at runtime so this file is not itself a match.
    needles = ("api.render" + ".com/deploy/srv-", "railway_token=", "RAILWAY_TOKEN:")
    skip_parts = {".git", "node_modules", "dist", ".venv", "__pycache__", "coverage"}
    allowed = {"deploy.yml"}

    for path in ROOT.rglob("*"):
        if not path.is_file() or path == Path(__file__):
            continue
        if any(part in skip_parts for part in path.parts):
            continue
        if path.name in allowed:
            continue
        try:
            content = path.read_text(errors="ignore")
        except OSError:
            continue
        for needle in needles:
            assert needle not in content, f"{path} contains a deployment credential"


def test_render_is_no_longer_part_of_the_deployment():
    """Render was replaced by Railway; no configuration for it may remain."""
    assert not (ROOT / "render.yaml").exists()
    deploy = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()
    assert "RENDER_DEPLOY_HOOK_URL" not in deploy
    assert "render.com" not in deploy.lower()


def test_ci_runs_on_pull_requests_and_main():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "pull_request:" in workflow
    assert "push:" in workflow
    assert "quality-gate" in workflow
    # A pull request must not deploy.
    assert "RAILWAY_TOKEN" not in workflow


def test_production_deployment_is_manual_only():
    """A push to main must not release anything by itself."""
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()

    assert "workflow_dispatch:" in workflow
    # No push or schedule trigger: a human runs this workflow.
    assert "\n  push:" not in workflow
    assert "\n  schedule:" not in workflow
    assert "\n  workflow_run:" not in workflow


def test_the_deployment_refuses_to_run_off_main():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()
    assert "refs/heads/main" in workflow
    assert "must be run from main" in workflow


def test_the_deployment_verifies_health_before_finishing():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()
    assert "/health" in workflow
    assert "did not report healthy" in workflow


def test_the_deployment_never_touches_the_database():
    """Deploying an application service must not recreate or reseed data."""
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text().lower()
    for destructive in ("drop table", "drop database", "downgrade base", "db reset"):
        assert destructive not in workflow


# ---------------------------------------------------------------------------
# Compose: the local development stack
# ---------------------------------------------------------------------------
def test_compose_declares_the_three_services():
    compose = (ROOT / "docker-compose.yml").read_text()
    for service in ("db:", "backend:", "frontend:"):
        assert f"\n  {service}" in compose


def test_the_backend_reaches_the_database_by_service_name():
    """Inside a container, localhost is the container - never the host."""
    compose = (ROOT / "docker-compose.yml").read_text()
    assert "@db:5432" in compose
    assert "@localhost:5432" not in compose
    assert "@127.0.0.1:5432" not in compose


def test_the_local_database_persists_outside_the_container():
    compose = (ROOT / "docker-compose.yml").read_text()
    assert "./db/postgres-data:/var/lib/postgresql/data" in compose

    ignore = (ROOT / ".gitignore").read_text()
    assert "db/postgres-data/" in ignore, "PostgreSQL data files must not be committed"


def test_the_database_has_a_health_gate():
    compose = (ROOT / "docker-compose.yml").read_text()
    assert "pg_isready" in compose
    assert "condition: service_healthy" in compose


def test_migrations_complete_before_the_backend_starts():
    compose = (ROOT / "docker-compose.yml").read_text()
    assert "condition: service_completed_successfully" in compose


# ---------------------------------------------------------------------------
# Railway: the production platform
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("service", ["backend", "frontend"])
def test_each_service_declares_its_railway_configuration(service):
    config = json.loads((ROOT / service / "railway.json").read_text())
    assert config["build"]["builder"] == "DOCKERFILE"
    assert config["deploy"]["healthcheckPath"]


def test_the_backend_migrates_before_it_is_deployed():
    """A failed migration must stop the deployment, not start a broken app."""
    config = json.loads((ROOT / "backend" / "railway.json").read_text())
    assert "migrate" in config["deploy"]["preDeployCommand"]
    assert config["deploy"]["healthcheckPath"] == "/health"


def test_railway_configuration_contains_no_credentials():
    for service in ("backend", "frontend"):
        content = (ROOT / service / "railway.json").read_text().lower()
        for banned in ("password", "postgres://", "postgresql://", "api_key", "token"):
            assert banned not in content
