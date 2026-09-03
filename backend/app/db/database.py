"""Database engine and session management.

PostgreSQL is the target database for JourneyMesh, and the provider is defined
entirely by ``DATABASE_URL``. The PostgreSQL container in the local compose
stack and the Railway PostgreSQL service in production are the same thing to
this module; nothing here, and nothing above it, knows which one is in use, and
there is no ``if railway:`` or ``if docker:`` anywhere in the application.

The engine is built for the harder of the two cases - a managed database
reached over a network: a bounded pool, pre-ping so a connection dropped by the
provider is discovered before a query rather than during one, recycling well
inside typical idle timeouts, an explicit connect timeout, a server-side
statement timeout, and TLS unless the target is plainly local. Those settings
are harmless against a container on the same machine, which is why one code
path serves both.

When ``DATABASE_URL`` is not configured the application falls back to a
process-local SQLite database so the API, the graph and the test suite still
run end to end. The fallback is reported by the health endpoint, never
silently.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

logger = logging.getLogger("journeymesh.db")

FALLBACK_URL = "sqlite+pysqlite:///:memory:"

# Hosts for which TLS is not enforced, because there is no network in between.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "db", "postgres", ""})

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_backend: str = "uninitialised"


def _is_local(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host in LOCAL_HOSTS


def apply_ssl_mode(url: str, *, require_ssl: bool = True) -> str:
    """Ensure a TLS mode is present for a remote database.

    A managed provider reached over a network requires TLS; a container on the
    private compose network neither needs nor offers it. An ``sslmode`` already
    present in the URL is always respected, and a local host is left alone.
    """
    if not url or not require_ssl or _is_local(url):
        return url

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if "sslmode" in query:
        return url
    query["sslmode"] = "require"
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def engine_options(url: str) -> dict[str, Any]:
    """Pool and connection settings for a managed PostgreSQL instance."""
    settings = get_settings()
    return {
        "future": True,
        # Discover a connection the provider dropped before a query uses it.
        "pool_pre_ping": True,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout_seconds,
        # Well inside the idle timeout of a typical managed instance.
        "pool_recycle": settings.db_pool_recycle_seconds,
        "connect_args": {
            "connect_timeout": settings.db_connect_timeout_seconds,
            "application_name": "journeymesh",
            # A runaway query must not hold a pooled connection open forever.
            "options": f"-c statement_timeout={settings.db_statement_timeout_ms}",
        },
    }


def _build_engine() -> tuple[Engine, str]:
    settings = get_settings()
    url = settings.sqlalchemy_url
    if url:
        url = apply_ssl_mode(url, require_ssl=settings.db_require_ssl)
        engine = create_engine(url, **engine_options(url))
        logger.info(
            "connected to PostgreSQL",
            extra={
                "pool_size": settings.db_pool_size,
                "max_overflow": settings.db_max_overflow,
                "pool_recycle": settings.db_pool_recycle_seconds,
                "tls": not _is_local(url),
            },
        )
        return engine, "postgresql"

    logger.warning(
        "DATABASE_URL is not configured - JourneyMesh is using an ephemeral "
        "in-memory database. Journeys will not survive a restart."
    )
    engine = create_engine(
        FALLBACK_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    return engine, "ephemeral_sqlite"


def get_engine() -> Engine:
    global _engine, _session_factory, _backend
    if _engine is None:
        _engine, _backend = _build_engine()
        _session_factory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
        if _backend == "ephemeral_sqlite":
            # The fallback database has no migration history, so its schema is
            # created the moment the engine is built.
            from app.db import models

            models.Base.metadata.create_all(bind=_engine)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


def configured_backend() -> str:
    """The database JourneyMesh *would* use, without creating an engine.

    The health endpoint uses this so that a health check never opens a
    connection or waits on the network.
    """
    return "postgresql" if get_settings().database_url else "ephemeral_sqlite"


def backend_name() -> str:
    """The database actually in use. Creates the engine if needed."""
    get_engine()
    return _backend


def init_db() -> None:
    """Create tables when running against the ephemeral fallback.

    Against PostgreSQL the schema is owned by Alembic; ``init_db`` only
    verifies that a connection can be opened.
    """
    from app.db import models  # noqa: F401  (import registers the mappers)

    engine = get_engine()
    if backend_name() == "postgresql":
        with engine.connect() as connection:
            connection.close()
        return
    models.Base.metadata.create_all(bind=engine)


def reset_engine() -> None:
    """Drop the cached engine. Used by tests that swap configuration."""
    global _engine, _session_factory, _backend
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
    _backend = "uninitialised"


def ping(timeout_seconds: int = 5) -> bool:
    """Open one connection and run ``SELECT 1``.

    This is deliberately *not* part of the health endpoint - it is for
    start-up checks and for the deployment verification script.
    """
    try:
        engine = get_engine()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("database ping failed", extra={"error": str(exc)})
        return False


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional scope around a series of operations."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    with session_scope() as session:
        yield session
