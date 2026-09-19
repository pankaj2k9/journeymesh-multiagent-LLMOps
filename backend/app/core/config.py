"""Typed application settings for Travel Crew AI.

Every value can be supplied through the environment or ``backend/.env``.
Blank values fall back to safe development defaults so that the project can
be started without any third-party credential.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import DEFAULT_LANGUAGE

# HS256 signs with SHA-256, so a key below the digest length adds nothing.
MIN_JWT_KEY_BYTES = 32


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


class Settings(BaseSettings):
    """Runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=(".env",),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Application ----------------------------------------------------
    app_name: str = "Travel Crew AI"
    app_env: str = "development"
    debug: bool = True
    api_prefix: str = "/api/v1"

    # ---- Database -------------------------------------------------------
    # The provider is defined entirely by DATABASE_URL. A PostgreSQL container
    # on a laptop, a PostgreSQL container on a VPS, or any managed
    # PostgreSQL are all the same to this application - there is no
    # provider-specific branch anywhere in it.
    database_url: str | None = None
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 900
    db_connect_timeout_seconds: int = 10
    db_statement_timeout_ms: int = 30000
    db_require_ssl: bool = True
    run_migrations_on_startup: bool = False

    # ---- Language model -------------------------------------------------
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    llm_temperature: float = 0.2
    llm_timeout_seconds: int = 45

    # ---- Providers ------------------------------------------------------
    tavily_api_key: str | None = None
    aviationstack_api_key: str | None = None
    # AviationStack's own MCP package reads AVIATION_STACK_API_KEY, while this
    # application has always called it AVIATIONSTACK_API_KEY. Both are accepted
    # and `aviation_api_key` below is the single value the rest of the code
    # reads, so nobody has to set the same secret twice.
    aviation_stack_api_key: str | None = None
    openweather_api_key: str | None = None
    provider_timeout_seconds: int = 20

    # ---- MCP ------------------------------------------------------------
    #
    # "auto" is the default and means: use MCP when this deployment can
    # actually reach an MCP server, and fall back to the in-process adapter
    # when it cannot. That is what makes MCP the preferred provider without
    # turning a missing API key into a startup failure.
    #
    #   search    auto -> streamable_http when TAVILY_API_KEY is set
    #   aviation  auto -> stdio when an AviationStack key is set AND uvx exists
    #   weather   auto -> stdio always; the server ships inside this image and
    #                     produces labelled ESTIMATE data without a key
    #
    # Set an explicit transport to override: "stdio", "streamable_http" or
    # "disabled". `app/mcp/config.py` resolves "auto" into a real transport.
    mcp_search_transport: str = "auto"
    mcp_search_url: str | None = None
    mcp_aviation_transport: str = "auto"
    mcp_aviation_url: str | None = None
    mcp_weather_transport: str = "auto"
    mcp_weather_url: str | None = None
    mcp_timeout_seconds: int = 30
    # The hosted Tavily MCP endpoint. The API key is a query parameter, so the
    # full URL is a credential and is built at use time - never stored, never
    # logged, never returned by an endpoint. See app/mcp/security.py.
    mcp_tavily_base_url: str = "https://mcp.tavily.com/mcp/"
    # The console command that launches the AviationStack MCP server.
    mcp_aviation_command: str = "uvx"
    mcp_aviation_package: str = "aviationstack-mcp"

    # ---- Identity and access ---------------------------------------------
    #
    # In development a secret is derived at import time when none is set, so
    # the project still starts with no configuration. In production a missing
    # secret is a hard failure - see `jwt_signing_key` below - because a
    # per-process random key silently invalidates every token on restart and
    # behind two workers it invalidates them at random.
    jwt_secret_key: str | None = None
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 14
    # Registration can be closed without redeploying, for a public demo that
    # should stay one account wide.
    registration_enabled: bool = True
    password_min_length: int = 10

    # ---- Foreign exchange ------------------------------------------------
    # Frankfurter serves European Central Bank reference rates with no API key
    # and no quota, so currency conversion works in CI and in a credential-free
    # demo exactly as it does in production. Set FX_PROVIDER=offline to use the
    # built-in indicative table instead, which is labelled MOCK wherever it
    # surfaces.
    fx_enabled: bool = True
    fx_provider: str = "frankfurter"
    fx_base_url: str = "https://api.frankfurter.app"
    # Used when FX_PROVIDER=erapi. Also keyless, and unlike the ECB set it
    # covers BDT and AED - which this application supports and the ECB does
    # not publish.
    fx_erapi_base_url: str = "https://open.er-api.com/v6/latest"
    fx_timeout_seconds: int = 10
    # The ECB publishes once a working day, so refetching more often than this
    # spends a request to receive the same numbers.
    fx_cache_hours: int = 6
    # What a traveller sees before they have told us anything. Step 5 of the
    # resolution chain in services/currency.py.
    default_currency: str = "USD"

    # ---- Media -----------------------------------------------------------
    # Uploaded files must live on a volume that survives deployment. In
    # production this is a named Docker volume mounted at /app/storage/media;
    # anywhere inside the built image would mean every deploy silently deleted
    # every uploaded picture.
    media_storage_driver: str = "local"
    media_root: str = "storage/media"
    # The path the application serves media from. Swapped for a CDN origin when
    # the storage driver becomes S3 or R2.
    media_base_url: str = "/media"
    max_upload_bytes: int = 10 * 1024 * 1024
    # A decompression-bomb ceiling: a 200MP PNG is a handful of kilobytes on
    # disk and gigabytes once decoded.
    max_image_pixels: int = 50_000_000
    max_image_dimension: int = 8000

    # ---- HTTP security --------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60
    max_request_size: int = 65536

    # ---- Guardrails -----------------------------------------------------
    guardrails_enabled: bool = True
    prompt_injection_check_enabled: bool = True
    pii_guard_enabled: bool = True
    tool_guard_enabled: bool = True

    # ---- Evaluation -----------------------------------------------------
    evaluation_enabled: bool = True
    evaluation_mode: str = "deterministic"
    evaluator_model: str | None = None
    evaluation_pass_threshold: float = 0.7

    # ---- Human-in-the-loop ---------------------------------------------
    max_revision_count: int = 3
    auto_approve: bool = False

    # ---- URLs -----------------------------------------------------------
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"

    # ---- Observability: LangSmith --------------------------------------
    langsmith_tracing: bool = False
    langsmith_api_key: str | None = None
    langsmith_project: str = "TravelCrewAI"
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    # ---- Serving --------------------------------------------------------
    port: int = 8000
    serve_frontend: bool = True
    frontend_dist_dir: str | None = None

    # ---- Development ----------------------------------------------------
    enable_mock_data: bool = True
    log_level: str = "INFO"
    log_format: str = "json"

    default_response_language: str = DEFAULT_LANGUAGE

    # ---- Normalisation --------------------------------------------------
    @field_validator(
        "database_url",
        "groq_api_key",
        "tavily_api_key",
        "aviationstack_api_key",
        "aviation_stack_api_key",
        "openweather_api_key",
        "mcp_search_url",
        "mcp_aviation_url",
        "mcp_weather_url",
        "evaluator_model",
        "langsmith_api_key",
        "frontend_dist_dir",
        "jwt_secret_key",
        mode="before",
    )
    @classmethod
    def _empty_optional(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @field_validator(
        "app_name",
        "app_env",
        "groq_model",
        "cors_origins",
        "evaluation_mode",
        "frontend_url",
        "backend_url",
        "log_level",
        "log_format",
        "mcp_search_transport",
        "mcp_aviation_transport",
        "mcp_weather_transport",
        "mcp_tavily_base_url",
        "mcp_aviation_command",
        "mcp_aviation_package",
        "media_storage_driver",
        "media_root",
        "media_base_url",
        "fx_provider",
        "fx_base_url",
        "fx_erapi_base_url",
        "default_currency",
        "langsmith_project",
        "langsmith_endpoint",
        mode="before",
    )
    @classmethod
    def _empty_string_uses_default(cls, value: Any, info: Any) -> Any:
        if isinstance(value, str) and value.strip() == "":
            field = cls.model_fields[info.field_name]
            return field.default
        return value

    @field_validator(
        "debug",
        "rate_limit_enabled",
        "guardrails_enabled",
        "prompt_injection_check_enabled",
        "pii_guard_enabled",
        "tool_guard_enabled",
        "evaluation_enabled",
        "enable_mock_data",
        "auto_approve",
        "langsmith_tracing",
        "serve_frontend",
        "db_require_ssl",
        "run_migrations_on_startup",
        mode="before",
    )
    @classmethod
    def _empty_bool_uses_default(cls, value: Any, info: Any) -> Any:
        if isinstance(value, str) and value.strip() == "":
            return cls.model_fields[info.field_name].default
        return value

    @field_validator(
        "rate_limit_requests",
        "rate_limit_window_seconds",
        "max_request_size",
        "max_revision_count",
        "port",
        "db_pool_size",
        "db_max_overflow",
        "db_pool_timeout_seconds",
        "db_pool_recycle_seconds",
        "db_connect_timeout_seconds",
        "db_statement_timeout_ms",
        mode="before",
    )
    @classmethod
    def _empty_int_uses_default(cls, value: Any, info: Any) -> Any:
        if isinstance(value, str) and value.strip() == "":
            return cls.model_fields[info.field_name].default
        return value

    # ---- Derived helpers ------------------------------------------------
    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def aviation_api_key(self) -> str | None:
        """The AviationStack key, under whichever name it was supplied.

        One canonical accessor so no caller has to know both spellings, and
        so adding a third name later is a one-line change here.
        """
        return self.aviationstack_api_key or self.aviation_stack_api_key

    def tavily_mcp_url(self) -> str | None:
        """The hosted Tavily MCP endpoint, with the key as a query parameter.

        Built here rather than configured, so the secret lives in exactly one
        variable (TAVILY_API_KEY) and never has to be pasted into a URL in an
        environment file. An explicit MCP_SEARCH_URL still wins, for anyone
        pointing at a self-hosted server.

        The return value IS a credential. Never log it, never return it from an
        endpoint: pass it through `app.mcp.security.redact_url` first.
        """
        if self.mcp_search_url:
            return self.mcp_search_url
        if not self.tavily_api_key:
            return None

        from urllib.parse import urlencode

        separator = "&" if "?" in self.mcp_tavily_base_url else "?"
        return (
            f"{self.mcp_tavily_base_url}{separator}"
            f"{urlencode({'tavilyApiKey': self.tavily_api_key})}"
        )

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def jwt_signing_key(self) -> str:
        """The key access and refresh tokens are signed with.

        Outside production a stable key is derived from the application name so
        that the project still runs with an empty ``.env`` and tokens survive a
        reload. In production a missing ``JWT_SECRET_KEY`` raises: a fallback
        there would either invalidate every session on each restart or, behind
        more than one worker, accept a token from one process and reject it
        from the next.
        """
        if self.jwt_secret_key:
            # HS256 keys shorter than the digest are weaker than the algorithm
            # they are used with (RFC 7518 s3.2). Refusing here is better than
            # a warning nobody reads in a log they never open.
            if len(self.jwt_secret_key.encode()) < MIN_JWT_KEY_BYTES:
                raise RuntimeError(
                    f"JWT_SECRET_KEY must be at least {MIN_JWT_KEY_BYTES} bytes. "
                    "Generate one with `openssl rand -hex 32`."
                )
            return self.jwt_secret_key
        if self.is_production:
            raise RuntimeError(
                "JWT_SECRET_KEY must be set in production. Generate one with "
                "`openssl rand -hex 32`."
            )
        return hashlib.sha256(
            f"travelcrewai-development-key::{self.app_name}".encode()
        ).hexdigest()

    @property
    def sqlalchemy_url(self) -> str | None:
        """Return a SQLAlchemy-compatible URL for the configured database."""
        if not self.database_url:
            return None
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    @property
    def psycopg_url(self) -> str | None:
        """Return a driver-native URL, used by the LangGraph checkpointer."""
        if not self.database_url:
            return None
        url = self.database_url
        for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql://" + url.split("://", 1)[1]
        return url

    @property
    def langsmith_enabled(self) -> bool:
        """Tracing only runs when it is switched on and has a key."""
        return bool(self.langsmith_tracing and self.langsmith_api_key)

    @property
    def frontend_dist_path(self) -> Path | None:
        """Where the built React assets live, if they are present."""
        if not self.serve_frontend:
            return None
        candidates = []
        if self.frontend_dist_dir:
            candidates.append(Path(self.frontend_dist_dir))
        here = Path(__file__).resolve().parents[2]
        candidates.append(here / "static")
        candidates.append(here.parent / "frontend" / "dist")
        for candidate in candidates:
            if (candidate / "index.html").is_file():
                return candidate
        return None

    @property
    def llm_available(self) -> bool:
        return bool(self.groq_api_key)

    @property
    def persistence_available(self) -> bool:
        return bool(self.database_url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


def reload_settings() -> Settings:
    """Clear the cache and re-read the environment. Used by tests."""
    get_settings.cache_clear()
    return get_settings()


settings = get_settings()
