"""Database engine & session management.

Supports SQLite (default) and PostgreSQL via SMART_SEARCH_DATABASE_URL.
"""

from __future__ import annotations

import os
import logging
from typing import TYPE_CHECKING

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from .models import Base

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_logger = logging.getLogger(__name__)

_DEFAULT_DB_URL = "sqlite:///smart-search-cloud.db"


def _database_url() -> str:
    """Return the configured database URL.

    Smart Search's canonical variable is ``SMART_SEARCH_DATABASE_URL``.  Zeabur
    PostgreSQL commonly exposes ``POSTGRES_CONNECTION_STRING``, so accept it as
    a deployment-friendly fallback.  ``DATABASE_URL`` is accepted last for other
    PaaS environments, but explicit Smart Search config always wins.
    """

    return (
        os.getenv("SMART_SEARCH_DATABASE_URL")
        or os.getenv("POSTGRES_CONNECTION_STRING")
        or os.getenv("DATABASE_URL")
        or _DEFAULT_DB_URL
    )


def _apply_sqlite_pragmas(engine: Engine) -> None:
    """Set WAL mode and busy_timeout for SQLite connections."""

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_engine_from_url(url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine with sensible defaults."""
    db_url = url or _database_url()
    engine_kwargs: dict = {}
    if db_url.startswith("sqlite"):
        engine_kwargs["pool_pre_ping"] = True
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        engine_kwargs["pool_size"] = 5
        engine_kwargs["max_overflow"] = 10
        engine_kwargs["pool_pre_ping"] = True

    engine = create_engine(db_url, **engine_kwargs)

    if db_url.startswith("sqlite"):
        _apply_sqlite_pragmas(engine)

    return engine


def create_session_factory(engine: Engine | None = None) -> sessionmaker:
    """Return a sessionmaker bound to *engine*."""
    if engine is None:
        engine = create_engine_from_url()
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine: Engine | None = None) -> None:
    """Create all tables (idempotent)."""
    if engine is None:
        engine = create_engine_from_url()
    Base.metadata.create_all(bind=engine)
    _logger.info("Database schema initialised")


def drop_db_for_tests(engine: Engine | None = None) -> None:
    """Drop all tables – only for test teardown."""
    if engine is None:
        engine = create_engine_from_url()
    Base.metadata.drop_all(bind=engine)
    _logger.debug("All tables dropped (test teardown)")
