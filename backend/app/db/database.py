"""Database engine and session management.

PostgreSQL is the target database for JourneyMesh. When ``DATABASE_URL`` is
not configured the application falls back to a process-local SQLite database
so that the API, the graph and the test-suite still run end to end. The
fallback is reported by the health endpoint and is never silent.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

logger = logging.getLogger("journeymesh.db")

FALLBACK_URL = "sqlite+pysqlite:///:memory:"

_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker[Session]] = None
_backend: str = "uninitialised"


def _build_engine() -> tuple[Engine, str]:
    settings = get_settings()
    url = settings.sqlalchemy_url
    if url:
        engine = create_engine(url, pool_pre_ping=True, future=True)
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
    return _engine


def get_session_factory() -> "sessionmaker[Session]":
    get_engine()
    assert _session_factory is not None
    return _session_factory


def backend_name() -> str:
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
