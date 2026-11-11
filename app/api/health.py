"""Liveness and readiness probes (unversioned, unauthenticated)."""

from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ServiceUnavailableError
from app.core.logging import get_logger
from app.db.migration_state import current_revision, expected_head_revision
from app.db.session import check_database, get_db
from app.schemas.common import ProblemDetail

router = APIRouter(prefix="/health", tags=["Health"])
logger = get_logger(__name__)


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    status: Literal["ready"] = "ready"
    checks: dict[str, Literal["ok"]]


@router.get(
    "/live",
    response_model=LivenessResponse,
    summary="Liveness probe",
    description="Reports that the process is running. Performs no dependency checks.",
)
def live() -> LivenessResponse:
    return LivenessResponse()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description=(
        "Reports whether the service can handle traffic: the database must be reachable "
        "and its schema must be at the latest migration revision."
    ),
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ProblemDetail}},
)
def ready(session: Session = Depends(get_db)) -> ReadinessResponse:
    try:
        check_database(session)
        revision = current_revision(session)
    except SQLAlchemyError as exc:
        logger.warning("health.database_unavailable", error_type=type(exc).__name__)
        raise ServiceUnavailableError("Database is not reachable.") from exc
    if revision != expected_head_revision():
        logger.warning(
            "health.schema_outdated", current=revision, expected=expected_head_revision()
        )
        raise ServiceUnavailableError("Database schema is not at the expected migration revision.")
    return ReadinessResponse(checks={"database": "ok", "migrations": "ok"})
