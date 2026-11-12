"""Application factory and ASGI entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.api import health
from app.api.openapi import API_DESCRIPTION, OPENAPI_TAGS
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import BodySizeLimitMiddleware, RequestContextMiddleware
from app.core.rate_limit import InMemoryRateLimiter
from app.db.migration_state import current_revision, expected_head_revision
from app.db.session import get_engine, get_session_factory

logger = get_logger(__name__)


def _log_schema_state() -> None:
    """Warn loudly (without crashing) if migrations have not been applied."""
    try:
        with get_session_factory()() as session:
            revision = current_revision(session)
    except SQLAlchemyError as exc:
        logger.warning("startup.database_unreachable", error_type=type(exc).__name__)
        return
    expected = expected_head_revision()
    if revision != expected:
        logger.warning("startup.schema_outdated", current=revision, expected=expected)
    else:
        logger.info("startup.schema_ok", revision=revision)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    logger.info("app.startup", version=settings.api_version)
    _log_schema_state()
    yield
    get_engine().dispose()
    logger.info("app.shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    docs_on = settings.docs_enabled
    app = FastAPI(
        title=settings.app_name,
        version=settings.api_version,
        description=API_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        openapi_url="/openapi.json" if docs_on else None,
        docs_url="/docs" if docs_on else None,
        redoc_url="/redoc" if docs_on else None,
        swagger_ui_parameters={"persistAuthorization": not settings.is_production},
        contact={"name": "ChronoStore Engineering", "email": "engineering@chronostore.lk"},
        lifespan=lifespan,
        debug=False,
    )
    app.state.settings = settings
    app.state.auth_rate_limiter = InMemoryRateLimiter(
        max_attempts=settings.auth_rate_limit_attempts,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )

    register_exception_handlers(app)

    # Added innermost-first: the request-context middleware must wrap everything else.
    app.add_middleware(BodySizeLimitMiddleware, max_body_bytes=settings.max_request_body_bytes)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
            expose_headers=["X-Request-ID", "Location", "Retry-After", "Idempotent-Replayed"],
        )
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    from app.core.telemetry import setup_telemetry
    from app.db.session import get_engine

    setup_telemetry(app, get_engine())
    return app


app = create_app()
