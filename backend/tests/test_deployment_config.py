"""Deployment configuration.

These tests protect the promises the deployment makes: the port comes from the
environment, the database provider is defined only by DATABASE_URL, the CI
pipeline gates deployment, and no secret is committed.

Production is a self-hosted OVHcloud VPS running deploy/docker-compose.prod.yml
behind Caddy. See deploy/OVHCLOUD.md.
"""

from __future__ import annotations

import re
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
    needles = (
        "api.render" + ".com/deploy/srv-",
        "railway_token=",
        "BEGIN OPENSSH PRIVATE" + " KEY",
        "BEGIN RSA PRIVATE" + " KEY",
    )
    skip_parts = {".git", "node_modules", "dist", ".venv", "__pycache__", "coverage"}
    # These three legitimately contain credential-SHAPED strings: the workflows
    # carry the detection patterns they scan for, and the checklist documents
    # what a leak looks like. gitleaks covers them from the other direction.
    allowed = {"deploy-production.yml", "ci.yml", "HARDENING.md"}

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


def test_no_previous_platform_configuration_remains():
    """Render, then Railway, then this. Only one deployment may be described."""
    assert not (ROOT / "render.yaml").exists()
    assert not (ROOT / "RAILWAY.md").exists()
    for service in ("backend", "frontend"):
        assert not (ROOT / service / "railway.json").exists()

    deploy = (ROOT / ".github" / "workflows" / "deploy-production.yml").read_text().lower()
    for stale in ("render.com", "render_deploy_hook_url", "railway"):
        assert stale not in deploy, f"deploy-production.yml still mentions {stale}"


def test_ci_runs_on_pull_requests_and_main():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "pull_request:" in workflow
    assert "push:" in workflow
    assert "quality-gate" in workflow
    # A pull request must not deploy.
    assert "OVH_SSH_PRIVATE_KEY" not in workflow


def test_production_deployment_triggers_are_trusted_only():
    """Only main, or a deliberate manual run. Never an arbitrary branch."""
    workflow = (ROOT / ".github" / "workflows" / "deploy-production.yml").read_text()

    assert "workflow_dispatch:" in workflow
    assert "\n  push:\n    branches: [main]" in workflow
    # Nothing that could fire from untrusted input or on a timer.
    assert "\n  schedule:" not in workflow
    assert "pull_request" not in workflow


def test_the_deployment_refuses_to_run_off_main():
    workflow = (ROOT / ".github" / "workflows" / "deploy-production.yml").read_text()
    assert "refs/heads/main" in workflow
    assert "must run from main" in workflow


def test_the_deployment_verifies_health_before_finishing():
    workflow = (ROOT / ".github" / "workflows" / "deploy-production.yml").read_text()
    assert "/health" in workflow
    assert "did not report healthy" in workflow


def test_the_deployment_never_touches_the_database():
    """Deploying an application service must not recreate or reseed data."""
    workflow = (ROOT / ".github" / "workflows" / "deploy-production.yml").read_text().lower()
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
# The OVHcloud VPS: the production platform
#
# This VPS is designed to host several small SaaS applications, so exactly one
# container on the whole machine - the shared Caddy in deploy/proxy - owns a
# public port. The application stack publishes nothing at all.
# ---------------------------------------------------------------------------
DEPLOY = ROOT / "deploy"
PROD_COMPOSE = DEPLOY / "docker-compose.prod.yml"
PROXY_COMPOSE = DEPLOY / "proxy" / "docker-compose.yml"
CADDYFILE = DEPLOY / "proxy" / "Caddyfile"

# The name the shared proxy actually dials, read from the Caddyfile so the
# two halves cannot drift apart silently.
CADDY_UPSTREAM = re.search(
    r"reverse_proxy\s+(\S+):80", CADDYFILE.read_text()
).group(1)


def test_the_production_stack_is_committed():
    for relative in (
        "docker-compose.prod.yml",
        "deploy.sh",
        "backup.sh",
        "bootstrap-vps.sh",
        "proxy/docker-compose.yml",
        "proxy/Caddyfile",
    ):
        assert (DEPLOY / relative).exists(), f"deploy/{relative} is missing"


def test_the_production_stack_pulls_images_and_never_builds_on_the_vps():
    """The artefact CI verified must be the artefact that serves traffic."""
    compose = PROD_COMPOSE.read_text()
    assert "\n    build:" not in compose, "production must not build on the VPS"
    assert "${BACKEND_IMAGE" in compose
    assert "${FRONTEND_IMAGE" in compose


def test_the_application_stack_publishes_no_host_port():
    """Only the shared proxy may own a port; two stacks cannot both own 443."""
    compose = PROD_COMPOSE.read_text()
    assert "\n    ports:" not in compose, "the application stack must publish nothing"
    for banned in ('"80:80"', '"443:443"', '"8000:8000"', '"5173:80"', ":5432:5432"):
        assert banned not in compose, f"{banned} must not be published"


def test_caddy_is_not_part_of_the_application_stack():
    """TLS belongs to the VPS, not to one of the applications on it."""
    compose = PROD_COMPOSE.read_text()
    assert "\n  caddy:" not in compose
    assert "caddy-data" not in compose


def test_the_shared_proxy_owns_eighty_and_four_four_three():
    proxy = PROXY_COMPOSE.read_text()
    assert '"80:80"' in proxy
    assert '"443:443"' in proxy
    assert "caddy-data:/data" in proxy


def test_the_shared_proxy_lifecycle_is_independent_of_any_application():
    """It also serves the other SaaS stacks, so a release must not restart it."""
    proxy = _without_comments(PROXY_COMPOSE.read_text())
    assert "depends_on" not in proxy, "the proxy must start whether or not an app is up"
    # It may name JOURNEYMESH_DOMAIN - a routing fact - but must not depend on
    # this project's network, volumes or containers.
    assert "journeymesh_default" not in proxy
    assert "journeymesh-frontend" not in proxy

    workflow = _without_comments(
        (ROOT / ".github" / "workflows" / "deploy-production.yml").read_text())
    assert "deploy/proxy" not in workflow, "a release must not ship or restart the proxy"
    assert "shared-caddy" not in workflow.replace("filter name=shared-caddy", "")


def test_the_proxy_network_is_external_everywhere():
    """External, so bringing one stack down never disturbs the others."""
    for path in (PROD_COMPOSE, PROXY_COMPOSE):
        text = path.read_text()
        assert "  proxy:\n    external: true" in text, f"{path.name} must not own the network"


def _without_comments(text: str) -> str:
    """The lines that actually do something. Comments explain what a file
    deliberately does NOT do, and would trip every absence assertion here."""
    return "\n".join(
        line for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def _service_block(compose: str, name: str) -> str:
    """One service's directives, from its key to the next one, comments removed."""
    body = compose[compose.index(f"\n  {name}:") + 1:]
    lines = body.splitlines()
    end = len(lines)
    for line_no, line in enumerate(lines):
        if line_no and line and not line.startswith("   ") and not line.startswith("  #"):
            end = line_no
            break
    # Comments explain what a service deliberately does NOT do, so they would
    # otherwise trip every "this word must not appear" assertion below.
    return "\n".join(l for l in lines[:end] if not l.lstrip().startswith("#"))


def test_only_the_frontend_joins_the_shared_proxy_network():
    """Caddy must be able to reach nginx, and nothing else on this stack."""
    compose = PROD_COMPOSE.read_text()

    frontend = _service_block(compose, "frontend")
    assert "proxy:" in frontend, "the frontend must join the shared proxy network"

    # The alias, not the container name: this is the name the shared Caddyfile
    # proxies to, and it must survive the container being renamed.
    alias = re.search(r"aliases:\s*\n\s*-\s*(\S+)", frontend)
    assert alias, "the frontend must declare a network alias on the proxy network"
    assert alias.group(1) == CADDY_UPSTREAM, (
        f"the frontend alias is {alias.group(1)} but the Caddyfile proxies to {CADDY_UPSTREAM}"
    )

    for service in ("db", "backend", "migrate"):
        block = _service_block(compose, service)
        assert "networks:" in block, f"{service} must declare its networks explicitly"
        assert "proxy" not in block, f"{service} must not join the shared proxy network"


def test_the_caddyfile_routes_to_the_frontend_alias_and_is_expandable():
    caddy = CADDYFILE.read_text()
    assert "{$JOURNEYMESH_DOMAIN}" in caddy
    assert "reverse_proxy journeymesh-frontend:80" in caddy
    # Room for the next two SaaS applications, without touching this one.
    assert "SAAS2_DOMAIN" in caddy
    assert "SAAS3_DOMAIN" in caddy


def test_the_production_database_survives_a_redeploy():
    compose = PROD_COMPOSE.read_text()
    assert "postgres-data:/var/lib/postgresql/data" in compose
    assert "\nvolumes:" in compose


def test_no_deployment_command_removes_the_database_volume():
    """`down -v` deletes production data. Nothing automated may run it."""
    for path in (DEPLOY / "deploy.sh", DEPLOY / "backup.sh",
                 ROOT / ".github" / "workflows" / "deploy-production.yml"):
        text = path.read_text()
        for destructive in ("down -v", "down --volumes", "volume rm"):
            assert destructive not in text, f"{path.name} runs `{destructive}`"


def test_migrations_are_a_one_shot_job_that_can_fail_the_release():
    compose = PROD_COMPOSE.read_text()
    assert "\n  migrate:" in compose
    assert 'command: ["migrate"]' in compose
    # Kept out of `up -d`: the release runs it explicitly and stops on failure.
    assert 'profiles: ["migrate"]' in compose
    assert 'RUN_MIGRATIONS: "false"' in compose

    deploy_sh = _without_comments((DEPLOY / "deploy.sh").read_text())
    assert deploy_sh.index("compose pull") < deploy_sh.index("compose run --rm migrate")
    assert deploy_sh.index("compose run --rm migrate") < deploy_sh.index("compose up -d --remove-orphans")


def test_every_production_service_has_a_health_gate():
    compose = PROD_COMPOSE.read_text()
    assert "pg_isready" in compose
    assert "http://127.0.0.1:8000/health" in compose
    assert "http://127.0.0.1/healthz" in compose


def test_the_backend_keeps_docker_dns_for_nginx():
    """nginx resolves the upstream per request, which needs an explicit resolver."""
    compose = PROD_COMPOSE.read_text()
    assert "JOURNEYMESH_RESOLVER: 127.0.0.11" in compose
    assert "JOURNEYMESH_API_UPSTREAM: http://backend:8000" in compose

    template = (ROOT / "frontend" / "nginx.conf.template").read_text()
    assert "resolver ${JOURNEYMESH_RESOLVER}" in template


def test_production_defaults_are_conservative_for_a_four_gigabyte_vps():
    compose = PROD_COMPOSE.read_text()
    assert "ENABLE_MOCK_DATA: ${ENABLE_MOCK_DATA:-false}" in compose
    assert "WEB_CONCURRENCY: ${WEB_CONCURRENCY:-1}" in compose


def test_the_guardrails_stay_on_in_production():
    compose = PROD_COMPOSE.read_text()
    for guard in (
        "GUARDRAILS_ENABLED: ${GUARDRAILS_ENABLED:-true}",
        "PROMPT_INJECTION_CHECK_ENABLED: ${PROMPT_INJECTION_CHECK_ENABLED:-true}",
        "PII_GUARD_ENABLED: ${PII_GUARD_ENABLED:-true}",
        "TOOL_GUARD_ENABLED: ${TOOL_GUARD_ENABLED:-true}",
        "RATE_LIMIT_ENABLED: ${RATE_LIMIT_ENABLED:-true}",
    ):
        assert guard in compose, f"{guard} is not the production default"


def test_container_logs_are_rotated_everywhere():
    """A VPS disk filled by logs is how a small deployment falls over."""
    for path in (PROD_COMPOSE, PROXY_COMPOSE):
        text = path.read_text()
        assert "json-file" in text
        assert "max-size" in text


def test_the_production_stack_contains_no_credentials():
    """Secrets live in /opt/journeymesh/.env on the VPS and nowhere else."""
    for relative in ("docker-compose.prod.yml", "deploy.sh", "backup.sh",
                     "bootstrap-vps.sh", "proxy/docker-compose.yml", "proxy/Caddyfile"):
        content = (DEPLOY / relative).read_text()
        assert "POSTGRES_PASSWORD=" not in content.replace("POSTGRES_PASSWORD=$", "")
        assert "-----BEGIN" not in content


def test_the_environment_template_ships_no_filled_in_secret():
    template = (DEPLOY / ".env.prod.example").read_text()
    for key in ("POSTGRES_PASSWORD", "GROQ_API_KEY", "TAVILY_API_KEY", "LANGSMITH_API_KEY"):
        assert f"{key}=\n" in template, f"{key} must be blank in the template"


def test_the_environment_template_matches_the_production_defaults():
    template = (DEPLOY / ".env.prod.example").read_text()
    assert "ENABLE_MOCK_DATA=false" in template
    assert "WEB_CONCURRENCY=1" in template
    # TLS moved to the shared proxy; these belong to deploy/proxy/.env now.
    assert "PUBLIC_DOMAIN=" not in template
    assert "ACME_EMAIL=" not in template

    proxy_template = (DEPLOY / "proxy" / ".env.example").read_text()
    assert "ACME_EMAIL=" in proxy_template
    assert "JOURNEYMESH_DOMAIN=" in proxy_template


def test_the_production_environment_file_is_never_committed():
    ignore = (ROOT / ".gitignore").read_text()
    assert "deploy/.env" in ignore


def test_the_release_pins_an_immutable_image_tag():
    """A rollback must be a tag change, not a rebuild of whatever main is now."""
    workflow = (ROOT / ".github" / "workflows" / "deploy-production.yml").read_text()
    assert "${{ github.sha }}" in workflow
    assert ".env.images" in workflow


def test_the_release_pins_the_ssh_host_key():
    """Without this, a redirected DNS record collects the deploy key."""
    workflow = (ROOT / ".github" / "workflows" / "deploy-production.yml").read_text()
    assert "OVH_KNOWN_HOSTS" in workflow
    assert "StrictHostKeyChecking yes" in workflow
    assert "StrictHostKeyChecking=no" not in workflow
    assert "StrictHostKeyChecking no" not in workflow


def test_the_release_checks_the_shared_network_before_it_pulls():
    """Compose refuses an external network that is missing; say so early."""
    workflow = (ROOT / ".github" / "workflows" / "deploy-production.yml").read_text()
    assert "docker network inspect proxy" in workflow
    assert workflow.index("docker network inspect proxy") < workflow.index("Pull the images")


def test_the_release_migrates_before_it_starts_the_new_containers():
    workflow = (ROOT / ".github" / "workflows" / "deploy-production.yml").read_text()
    assert workflow.index("Apply database migrations") < workflow.index("Start the new containers")


def test_the_release_verifies_the_public_endpoint():
    """A container health check cannot prove TLS, DNS or the proxy route."""
    workflow = (ROOT / ".github" / "workflows" / "deploy-production.yml").read_text()
    assert "PUBLIC_URL" in workflow
    assert "did not report healthy" in workflow

    # /api/v1/health, not /health: nginx proxies only /api/, so the container
    # probe path falls through to the SPA and answers 200 with HTML for
    # anything at all - including a request to a backend that is not running.
    verify = workflow[workflow.index("Verify the public endpoint"):]
    assert "${PUBLIC_URL}/api/v1/health" in verify
    assert "${PUBLIC_URL}/health" not in verify


def test_the_container_probe_path_is_not_proxied_publicly():
    """The reason the release polls the versioned path instead."""
    template = (ROOT / "frontend" / "nginx.conf.template").read_text()
    assert "location /api/ {" in template
    assert "location /health" not in template


def test_the_vps_environment_is_owned_by_the_vps():
    """The workflow must never overwrite the file holding production secrets."""
    workflow = (ROOT / ".github" / "workflows" / "deploy-production.yml").read_text()
    ship = workflow[workflow.index("Ship the deployment files"):workflow.index("Pin the image tags")]
    assert ".env.prod.example" not in ship
    assert "docker-compose.prod.yml" in ship


# ---------------------------------------------------------------------------
# A public repository: the pipeline's trust boundary
#
# CI runs untrusted code with no secrets. CD runs trusted code from main only.
# These tests protect that boundary, because a mistake in it is not a bug that
# shows up in staging - it is a credential in someone else's hands.
# ---------------------------------------------------------------------------
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-production.yml"


def test_no_workflow_uses_pull_request_target():
    """It runs a fork's code with write access and this repository's secrets."""
    for path in (ROOT / ".github" / "workflows").glob("*.yml"):
        text = _without_comments(path.read_text())
        assert "pull_request_target" not in text, f"{path.name} uses pull_request_target"


def test_ci_has_no_access_to_production():
    """A pull request must not be able to reach the VPS or read a secret."""
    ci = CI_WORKFLOW.read_text()
    assert "environment:" not in ci, "CI must not attach a deployment environment"
    for forbidden in ("OVH_SSH_PRIVATE_KEY", "OVH_KNOWN_HOSTS", "OVH_HOST", "ssh "):
        assert forbidden not in ci, f"CI references {forbidden}"


def test_ci_is_read_only():
    ci = CI_WORKFLOW.read_text()
    assert "permissions:\n  contents: read" in ci
    for escalation in ("packages: write", "contents: write", "id-token: write"):
        assert escalation not in ci, f"CI requests {escalation}"


def test_only_the_build_jobs_may_publish_a_package():
    """`packages: write` is the one privilege CD adds, and only where needed."""
    deploy = _without_comments(DEPLOY_WORKFLOW.read_text())
    assert deploy.count("packages: write") == 2, "exactly the two build jobs"
    assert "permissions:\n  contents: read" in deploy


def test_the_release_runs_inside_the_production_environment():
    deploy = DEPLOY_WORKFLOW.read_text()
    assert "environment:\n      name: production" in deploy


def test_third_party_actions_are_pinned_to_a_commit_sha():
    """A moved tag must not be able to change what runs in a privileged job."""
    import re

    for path in (ROOT / ".github" / "workflows").glob("*.yml"):
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if not stripped.startswith("uses:"):
                continue
            ref = stripped.split("uses:", 1)[1].strip()
            if ref.startswith("./"):
                continue  # a local reusable workflow, not third-party
            assert "@" in ref, f"{path.name}: {ref} has no version"
            pin = ref.split("@", 1)[1].split()[0]
            assert re.fullmatch(r"[0-9a-f]{40}", pin), (
                f"{path.name}: {ref} is not pinned to a full commit SHA"
            )
            assert "#" in stripped, f"{path.name}: {ref} has no readable version comment"


def test_the_release_never_logs_a_secret():
    """These logs are public, so the usual debugging reflexes are hazards."""
    deploy = _without_comments(DEPLOY_WORKFLOW.read_text())
    for hazard in ("set -x", "printenv", "env |"):
        assert hazard not in deploy, f"the release runs `{hazard}`"

    # `cat .env.images` is fine - two image references and nothing else.
    # `cat .env` would print the database password into a public log.
    import re

    for match in re.finditer(r"cat\s+\S*\.env\S*", deploy):
        printed = match.group(0).split()[-1]
        assert printed.endswith(".env.images"), f"the release runs `{match.group(0)}`"
    # `docker compose config` renders the database password.
    assert "compose config" not in deploy


def test_ci_validates_compose_with_placeholders_only():
    """`docker compose config` renders real values; CI must never see one."""
    ci = CI_WORKFLOW.read_text()
    assert "docker compose -f deploy/docker-compose.prod.yml config" in ci
    assert "POSTGRES_PASSWORD: validate-only" in ci


def test_the_release_refuses_to_deploy_as_root():
    deploy = DEPLOY_WORKFLOW.read_text()
    assert 'if [ "${OVH_USER}" = "root" ]' in deploy
    assert "Refuse to deploy as root" in deploy


def test_the_release_is_serialised():
    """Two overlapping releases could interleave a migration with a restart."""
    deploy = DEPLOY_WORKFLOW.read_text()
    assert "concurrency:" in deploy
    assert "cancel-in-progress: false" in deploy


def test_ci_scans_the_full_history_for_secrets():
    ci = CI_WORKFLOW.read_text()
    assert "gitleaks" in ci
    assert "--redact" in ci, "a finding must not be printed into a public log"


def test_ci_asserts_the_images_carry_no_secret():
    ci = CI_WORKFLOW.read_text()
    assert "The images carry no secret" in ci
    assert "BEGIN OPENSSH PRIVATE KEY" in ci


def test_no_dockerfile_bakes_in_a_secret():
    """A published image is public; anything in a layer is public with it."""
    for name in ("Dockerfile", "backend/Dockerfile", "frontend/Dockerfile"):
        text = (ROOT / name).read_text()
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("ENV ", "ARG ", "COPY ")):
                continue
            upper = stripped.upper()
            if stripped.startswith("COPY "):
                assert ".env" not in stripped, f"{name} copies an environment file"
                continue
            for word in ("API_KEY", "PASSWORD", "SECRET", "TOKEN"):
                assert word not in upper, f"{name} sets {word} at build time: {stripped}"


def test_every_build_context_excludes_secrets():
    """Each image is built from its own directory, so each needs its own rules."""
    for name in (".dockerignore", "backend/.dockerignore", "frontend/.dockerignore"):
        text = (ROOT / name).read_text()
        for rule in (".env", "*.pem", "*.key", "*.p12", "backups/", "*.sql"):
            assert rule in text, f"{name} does not exclude {rule}"


def test_git_excludes_every_class_of_secret():
    ignore = (ROOT / ".gitignore").read_text()
    for rule in (".env", "*.pem", "*.key", "*.p12", "*.pfx",
                 "backups/", "*.sql", "*.sql.gz", "id_ed25519", "db/postgres-data/"):
        assert rule in ignore, f".gitignore does not exclude {rule}"
    # The safe templates must stay tracked.
    for keep in ("!.env.example", "!**/.env.example"):
        assert keep in ignore


def test_no_environment_file_is_tracked():
    """The check CI performs, asserted here too so it fails fast locally."""
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    for path in tracked:
        name = path.rsplit("/", 1)[-1]
        assert not (name == ".env" or name.startswith(".env.") and not name.endswith(".example")), (
            f"{path} is tracked by git"
        )


def test_vite_variables_are_never_secrets():
    """Every VITE_* value is compiled into JavaScript the browser downloads."""
    import re

    names = set()
    for path in (ROOT / "frontend" / "src").rglob("*.ts*"):
        names.update(re.findall(r"VITE_[A-Z0-9_]+", path.read_text()))
    for name in names:
        for word in ("KEY", "SECRET", "TOKEN", "PASSWORD"):
            assert word not in name, f"{name} must not be a build-time variable"


def test_dependabot_watches_every_ecosystem():
    config = (ROOT / ".github" / "dependabot.yml").read_text()
    for ecosystem in ("github-actions", "pip", "npm", "docker"):
        assert f"package-ecosystem: {ecosystem}" in config


def test_the_hardening_checklist_exists():
    """The manual settings code cannot apply to itself."""
    doc = (DEPLOY / "HARDENING.md").read_text()
    for topic in ("production", "Branch protection", "Push protection",
                  "ssh-keyscan", "ufw allow 22/tcp", "read:packages", "Rotate first"):
        assert topic in doc, f"HARDENING.md does not cover {topic}"


def test_the_backup_does_not_need_a_database_host_port():
    """PostgreSQL publishes nothing, so pg_dump runs inside the container."""
    backup = (DEPLOY / "backup.sh").read_text()
    assert "exec -T db pg_dump" in backup
    assert "localhost:5432" not in backup
    assert "127.0.0.1:5432" not in backup
