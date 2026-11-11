"""Shared pytest fixtures.

The suite runs against a real PostgreSQL database (``TEST_DATABASE_URL``) because
locking, constraints and concurrency semantics are part of what is being verified.
The schema is created once per session by running Alembic migrations from an empty
database; every database-backed test starts from empty tables.
"""

import io
import json
import logging
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_dotenv = dotenv_values(PROJECT_ROOT / ".env")
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or _dotenv.get("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError("TEST_DATABASE_URL must be set (see .env.example)")

# Must be configured before any application module reads settings.
os.environ.update(
    {
        "ENVIRONMENT": "testing",
        "DATABASE_URL": TEST_DATABASE_URL,
        "JWT_SECRET_KEY": "test-only-secret-key-that-is-long-enough-0123456789",
        "LOG_JSON": "true",
        "LOG_LEVEL": "INFO",
        "LOG_SQL": "false",
        "CORS_ORIGINS": "http://testclient.example",
        "DOCS_ENABLED": "true",
        "DB_POOL_SIZE": "20",
        "DB_MAX_OVERFLOW": "10",
        "AUTH_RATE_LIMIT_ATTEMPTS": "10",
        "AUTH_RATE_LIMIT_WINDOW_SECONDS": "60",
    }
)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402


def alembic_config() -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.attributes["database_url"] = TEST_DATABASE_URL
    config.attributes["configure_logger"] = False
    return config


def reset_schema() -> None:
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()


@pytest.fixture(scope="session")
def migrated_database() -> str:
    reset_schema()
    command.upgrade(alembic_config(), "head")
    return TEST_DATABASE_URL


def truncate_all_tables(session: Session) -> None:
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    if tables:
        session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        session.commit()


@pytest.fixture
def clean_database(migrated_database: str) -> Iterator[None]:
    yield
    with get_session_factory()() as session:
        truncate_all_tables(session)


@pytest.fixture
def db_session(clean_database: None) -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


class LogCapture:
    """Collects JSON log lines produced by the application's real formatter."""

    def __init__(self) -> None:
        self.stream = io.StringIO()

    def records(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.stream.getvalue().splitlines() if line]

    def events(self, name: str) -> list[dict[str, Any]]:
        return [record for record in self.records() if record.get("event") == name]


@pytest.fixture
def log_capture() -> Iterator[LogCapture]:
    root = logging.getLogger()
    capture = LogCapture()
    handler = logging.StreamHandler(capture.stream)
    handler.setFormatter(root.handlers[0].formatter)
    root.addHandler(handler)
    try:
        yield capture
    finally:
        root.removeHandler(handler)


@pytest.fixture(scope="session")
def _session_client(migrated_database: str) -> Iterator[TestClient]:
    with TestClient(fastapi_app) as test_client:
        yield test_client


@pytest.fixture
def client(_session_client: TestClient, clean_database: None) -> TestClient:
    fastapi_app.state.auth_rate_limiter.reset()
    _session_client.headers.clear()
    return _session_client
