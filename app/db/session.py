"""Engine and request-scoped session management."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_recycle=settings.db_pool_recycle_seconds,
        pool_pre_ping=True,
        connect_args={
            "options": f"-c statement_timeout={settings.db_statement_timeout_ms} -c timezone=UTC",
            "application_name": "chronostore-api",
        },
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    # expire_on_commit=False lets services return committed ORM objects for serialisation.
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding one session per request.

    Services own commit boundaries; anything left uncommitted (including after an
    exception) is rolled back when the session closes.
    """
    session = get_session_factory()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_database(session: Session) -> bool:
    session.execute(text("SELECT 1"))
    return True
