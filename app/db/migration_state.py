"""Helpers to compare the database schema revision with the deployed migration head."""

from functools import lru_cache
from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


@lru_cache
def expected_head_revision() -> str | None:
    return ScriptDirectory(str(MIGRATIONS_DIR)).get_current_head()


def current_revision(session: Session) -> str | None:
    try:
        return session.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    except ProgrammingError:
        session.rollback()
        return None
