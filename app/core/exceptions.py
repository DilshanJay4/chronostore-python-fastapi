"""Application exceptions and RFC 9457 Problem Details error handling."""

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger
from app.core.request_context import get_request_id

PROBLEM_CONTENT_TYPE = "application/problem+json"
PROBLEM_TYPE_PREFIX = "urn:chronostore:problem:"

logger = get_logger(__name__)


def problem_type(code: str) -> str:
    return PROBLEM_TYPE_PREFIX + code.lower().replace("_", "-")


class AppError(Exception):
    """Base class for expected, client-facing failures.

    Subclasses define the HTTP status and a stable machine-readable `code`.
    """

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "BAD_REQUEST"
    title: str = "Bad request"

    def __init__(
        self,
        detail: str | None = None,
        *,
        code: str | None = None,
        extra: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.detail = detail or self.title
        if code:
            self.code = code
        self.extra = dict(extra or {})
        self.headers = dict(headers or {})
        super().__init__(self.detail)


class BadRequestError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "BAD_REQUEST"
    title = "Bad request"


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "NOT_AUTHENTICATED"
    title = "Authentication required"

    def __init__(self, detail: str | None = None, *, code: str | None = None) -> None:
        super().__init__(detail, code=code, headers={"WWW-Authenticate": "Bearer"})


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"
    title = "Forbidden"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"
    title = "Resource not found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"
    title = "Conflict"


class InvalidStateTransitionError(ConflictError):
    code = "INVALID_STATE_TRANSITION"
    title = "Invalid state transition"


class BusinessRuleViolationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "BUSINESS_RULE_VIOLATION"
    title = "Business rule violation"


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "RATE_LIMITED"
    title = "Too many requests"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "Too many requests. Please retry later.",
            headers={"Retry-After": str(retry_after_seconds)},
        )


class ServiceUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "SERVICE_UNAVAILABLE"
    title = "Service unavailable"


def build_problem(
    *,
    status_code: int,
    code: str,
    title: str,
    detail: str,
    instance: str | None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": problem_type(code),
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": instance,
        "code": code,
        "request_id": get_request_id(),
    }
    if extra:
        body.update(extra)
    return body


def problem_response(
    *,
    status_code: int,
    code: str,
    title: str,
    detail: str,
    instance: str | None,
    extra: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = build_problem(
        status_code=status_code,
        code=code,
        title=title,
        detail=detail,
        instance=instance,
        extra=extra,
    )
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(body),
        media_type=PROBLEM_CONTENT_TYPE,
        headers=dict(headers or {}),
    )


async def _handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)  # noqa: S101 - registered only for AppError
    # Expected business failures are not errors from the server's perspective.
    log = (
        logger.warning if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR else logger.info
    )
    log("request.rejected", status=exc.status_code, code=exc.code, path=request.url.path)
    return problem_response(
        status_code=exc.status_code,
        code=exc.code,
        title=exc.title,
        detail=exc.detail,
        instance=request.url.path,
        extra=exc.extra,
        headers=exc.headers,
    )


def _safe_validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Strip echoed input values so secrets (e.g. passwords) never appear in responses."""
    errors = []
    for error in exc.errors():
        errors.append(
            {
                "loc": [str(part) for part in error.get("loc", ())],
                "msg": error.get("msg", "Invalid value"),
                "type": error.get("type", "value_error"),
            }
        )
    return errors


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    errors = _safe_validation_errors(exc)
    logger.info("request.validation_failed", path=request.url.path, error_count=len(errors))
    return problem_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="VALIDATION_ERROR",
        title="Request validation failed",
        detail="One or more fields failed validation.",
        instance=request.url.path,
        extra={"errors": errors},
    )


async def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    try:
        phrase = HTTPStatus(exc.status_code).phrase
    except ValueError:
        phrase = "Error"
    code = phrase.upper().replace(" ", "_").replace("-", "_")
    detail = exc.detail if isinstance(exc.detail, str) else phrase
    return problem_response(
        status_code=exc.status_code,
        code=code,
        title=phrase,
        detail=detail,
        instance=request.url.path,
        headers=getattr(exc, "headers", None),
    )


def unexpected_error_response(path: str | None) -> JSONResponse:
    return problem_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="INTERNAL_ERROR",
        title="Internal server error",
        detail="An unexpected error occurred. Quote the request ID when contacting support.",
        instance=path,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    # Unexpected exceptions are handled (and logged once) by RequestContextMiddleware.
