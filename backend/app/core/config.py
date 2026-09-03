"""Typed application settings for JourneyMesh.

Every value can be supplied through the environment or ``backend/.env``.
Blank values fall back to safe development defaults so that the project can
be started without any third-party credential.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import DEFAULT_LANGUAGE


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
    app_name: str = "JourneyMesh"
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
    openweather_api_key: str | None = None
    provider_timeout_seconds: int = 20

    # ---- MCP ------------------------------------------------------------
    mcp_search_transport: str = "disabled"
    mcp_search_url: str | None = None
    mcp_aviation_transport: str = "disabled"
    mcp_aviation_url: str | None = None
    mcp_weather_transport: str = "stdio"
    mcp_weather_url: str | None = None
    mcp_timeout_seconds: int = 30

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
    langsmith_project: str = "JourneyMesh"
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
        "openweather_api_key",
        "mcp_search_url",
        "mcp_aviation_url",
        "mcp_weather_url",
        "evaluator_model",
        "langsmith_api_key",
        "frontend_dist_dir",
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
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

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
