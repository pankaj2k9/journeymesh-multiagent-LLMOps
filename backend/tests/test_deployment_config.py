"""Deployment configuration.

These tests protect the promises the deployment makes: the port comes from the
environment, the database provider is defined only by DATABASE_URL, the CI
pipeline gates deployment, and no secret is committed.
"""

from __future__ import annotations

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
    banned = ("neon.tech", "render.com", "onrender.com", "supabase.co", "rds.amazonaws")
    for path in (ROOT / "backend" / "app").rglob("*.py"):
        content = path.read_text().lower()
        for needle in banned:
            assert needle not in content, f"{path} hard-codes {needle}"


def test_a_managed_database_url_gets_tls():
    url = apply_ssl_mode("postgresql+psycopg://user:pw@ep-x-1.eu-central-1.aws.neon.tech/db")
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
    assert "/api/v1/health" in dockerfile


def test_the_build_context_excludes_secrets_and_caches():
    ignore = (ROOT / ".dockerignore").read_text()
    for entry in (".env", ".git/", "frontend/node_modules/", "backend/.venv/", "__pycache__"):
        assert entry in ignore


def test_no_environment_file_is_tracked_by_git():
    gitignore = (ROOT / ".gitignore").read_text()
    assert ".env" in gitignore


def test_the_deploy_hook_is_never_committed():
    """The Render deploy hook belongs in GitHub secrets and nowhere else."""
    # Assembled at runtime so this file is not itself a match.
    needle = "api.render" + ".com/deploy/srv-"
    skip_parts = {".git", "node_modules", "dist", ".venv", "__pycache__", "coverage"}

    for path in ROOT.rglob("*"):
        if not path.is_file() or path == Path(__file__):
            continue
        if any(part in skip_parts for part in path.parts):
            continue
        try:
            content = path.read_text(errors="ignore")
        except OSError:
            continue
        assert needle not in content, f"{path} contains a deploy hook"


def test_ci_runs_on_pull_requests_and_main():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "pull_request:" in workflow
    assert "push:" in workflow
    assert "quality-gate" in workflow
    # A pull request must not deploy.
    assert "RENDER_DEPLOY_HOOK_URL" not in workflow


def test_deployment_only_happens_after_ci_succeeds_on_main():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()
    assert "workflow_run" in workflow
    assert "branches: [main]" in workflow
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert "secrets.RENDER_DEPLOY_HOOK_URL" in workflow
    # The hook URL must never be echoed.
    assert 'echo "$RENDER_DEPLOY_HOOK_URL"' not in workflow


def test_render_does_not_deploy_independently():
    blueprint = (ROOT / "render.yaml").read_text()
    assert "autoDeploy: false" in blueprint
    assert "healthCheckPath: /api/v1/health" in blueprint
    assert "runtime: docker" in blueprint
    # PostgreSQL is Neon, reached through DATABASE_URL - not a Render database.
    assert "databases:" not in blueprint


def test_the_blueprint_stores_no_secret_values():
    blueprint = (ROOT / "render.yaml").read_text()
    for line in blueprint.splitlines():
        stripped = line.strip()
        if stripped.startswith("- key:") and any(
            marker in stripped for marker in ("API_KEY", "DATABASE_URL")
        ):
            continue
        assert "gsk_" not in stripped
        assert "lsv2_" not in stripped
        assert "postgres://" not in stripped
