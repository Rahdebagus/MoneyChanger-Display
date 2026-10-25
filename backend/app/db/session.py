"""Engine and session factory.

``pool_pre_ping`` matters here: MariaDB closes idle connections after
``wait_timeout`` (XAMPP ships 8 hours) and a long-lived worker process would
otherwise wake up holding a dead socket.
"""

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()

_is_sqlite = _settings.database_url.startswith("sqlite")

_engine_kwargs: dict = {
    "echo": _settings.db_echo,
    "pool_pre_ping": True,
    "future": True,
}
if not _is_sqlite:
    _engine_kwargs.update(
        pool_size=_settings.db_pool_size,
        max_overflow=_settings.db_max_overflow,
        pool_recycle=_settings.db_pool_recycle,
        pool_timeout=_settings.db_pool_timeout_seconds,
        connect_args={"connect_timeout": 5, "read_timeout": 15, "write_timeout": 15},
    )

engine: Engine = create_engine(_settings.database_url, **_engine_kwargs)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - test aid
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
else:
    @event.listens_for(engine, "connect")
    def _mysql_session_mode(dbapi_connection, _record):
        """Force strict mode and UTC on every connection.

        XAMPP ships MariaDB without STRICT_TRANS_TABLES, which silently
        truncates oversized values instead of raising - exactly the wrong
        behaviour for a DECIMAL rate. Setting it per connection means the
        application is safe regardless of how the server was configured.
        time_zone is pinned so NOW() matches the UTC timestamps written by
        the application.
        """
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(
                "SET SESSION sql_mode = CONCAT_WS(',', @@sql_mode, "
                "'STRICT_TRANS_TABLES', 'NO_ENGINE_SUBSTITUTION'), "
                "time_zone = '+00:00'"
            )
        finally:
            cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    # Keep one physical connection until the request ends. A direct save may
    # commit its draft before rendering while retaining its MariaDB advisory lock.
    with engine.connect() as connection:
        with SessionLocal(bind=connection) as db:
            yield db


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for workers and scripts."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
