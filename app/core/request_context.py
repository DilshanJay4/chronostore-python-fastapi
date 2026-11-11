"""Per-request context (request/correlation ID) shared with logging and error handling."""

import re
import uuid
from contextvars import ContextVar

REQUEST_ID_HEADER = "X-Request-ID"
# Accept caller-supplied correlation IDs only if they are short and log-safe.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._\-]{8,128}$")

_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def resolve_request_id(incoming: str | None) -> str:
    """Return the incoming ID when it is safe to propagate, otherwise a fresh one."""
    if incoming and _VALID_REQUEST_ID.fullmatch(incoming):
        return incoming
    return uuid.uuid4().hex


def set_request_id(request_id: str | None) -> object:
    return _request_id_var.set(request_id)


def reset_request_id(token: object) -> None:
    _request_id_var.reset(token)  # type: ignore[arg-type]


def get_request_id() -> str | None:
    return _request_id_var.get()
