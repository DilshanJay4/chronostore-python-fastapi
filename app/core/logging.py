"""Structured logging built on the standard library and structlog.

All records -- from application code, Uvicorn and SQLAlchemy -- flow through one
`ProcessorFormatter`, so every line on stdout has the same JSON shape and the same
redaction rules.
"""

import logging
import logging.config
import re
import sys
from collections.abc import Mapping
from typing import Any

import structlog
from structlog.types import EventDict, Processor, WrappedLogger

from app.core.config import Settings

REDACTED = "[REDACTED]"
_MAX_REDACTION_DEPTH = 6

# Keys whose values must never be written to logs, matched case-insensitively as substrings.
_SENSITIVE_KEY_PATTERN = re.compile(
    r"pass(word)?|secret|token|authorization|cookie|api[_-]?key|credential|"
    r"password_hash|card|cvv|database_url|dsn|idempotency_key",
    re.IGNORECASE,
)
# Defensive scrubbing of bearer tokens / JWTs that slip into free-text messages.
_BEARER_PATTERN = re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+")
_JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")
# Credentials embedded in connection URLs, e.g. postgresql://user:pass@host.
_URL_CREDENTIALS_PATTERN = re.compile(r"(?P<scheme>[a-z][a-z0-9+.\-]*://)[^\s/@:]+:[^\s/@]+@")


def _scrub_text(value: str) -> str:
    value = _BEARER_PATTERN.sub(f"Bearer {REDACTED}", value)
    value = _JWT_PATTERN.sub(REDACTED, value)
    return _URL_CREDENTIALS_PATTERN.sub(rf"\g<scheme>{REDACTED}@", value)


def _redact_value(key: str, value: Any, depth: int = 0) -> Any:
    if _SENSITIVE_KEY_PATTERN.search(key):
        return REDACTED
    if depth >= _MAX_REDACTION_DEPTH:
        return value
    if isinstance(value, Mapping):
        return {k: _redact_value(str(k), v, depth + 1) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_redact_value(key, item, depth + 1) for item in value]
    if isinstance(value, str):
        return _scrub_text(value)
    return value


def redact_sensitive_data(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """structlog processor that masks secrets in keys and free text."""
    for key in list(event_dict.keys()):
        if key in {"exc_info", "exception"}:
            continue
        event_dict[key] = _redact_value(key, event_dict[key])
    return event_dict


def _scrub_exception_text(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    exception = event_dict.get("exception")
    if isinstance(exception, str):
        event_dict["exception"] = _scrub_text(exception)
    return event_dict


def _static_fields(settings: Settings) -> Processor:
    service = settings.app_name
    environment = settings.environment.value

    def add_static_fields(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
        event_dict.setdefault("service", service)
        event_dict.setdefault("environment", environment)
        return event_dict

    return add_static_fields


def configure_logging(settings: Settings) -> None:
    """Configure stdlib + structlog. Safe to call more than once (e.g. in tests)."""
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        _static_fields(settings),
        structlog.stdlib.ExtraAdder(),
        redact_sensitive_data,
    ]

    renderer: Processor
    if settings.log_json:
        renderer = structlog.processors.JSONRenderer()
        final_processors: list[Processor] = [
            structlog.processors.format_exc_info,
            _scrub_exception_text,
            renderer,
        ]
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
        final_processors = [renderer]

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, *final_processors],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level)

    # Route third-party loggers through the root handler instead of their own handlers.
    for name in ("uvicorn", "uvicorn.error", "alembic"):
        lib_logger = logging.getLogger(name)
        lib_logger.handlers.clear()
        lib_logger.propagate = True
    # Request logging is done by our middleware; Uvicorn's access log would duplicate it.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False
    access_logger.disabled = True

    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.log_sql else logging.WARNING
    )

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.processors.StackInfoRenderer(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.stdlib.get_logger(name)
