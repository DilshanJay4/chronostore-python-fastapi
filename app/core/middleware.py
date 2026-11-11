"""Pure ASGI middleware: request IDs, access logging, safe 500s, body limits, headers.

Pure ASGI (rather than `BaseHTTPMiddleware`) keeps context variables intact for
endpoints running in the threadpool and avoids buffering streamed bodies.
"""

import time

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions import problem_response, unexpected_error_response
from app.core.logging import get_logger
from app.core.request_context import (
    REQUEST_ID_HEADER,
    reset_request_id,
    resolve_request_id,
    set_request_id,
)

logger = get_logger("app.http")

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}
_SERVER_ERROR = 500
_CLIENT_ERROR = 400


class RequestContextMiddleware:
    """Assigns a request ID, logs one structured line per request, and converts
    unhandled exceptions into a safe Problem Details response (logged once, with stack)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = resolve_request_id(headers.get(REQUEST_ID_HEADER))
        token = set_request_id(request_id)
        structlog.contextvars.bind_contextvars(request_id=request_id)

        started = time.perf_counter()
        status_code = _SERVER_ERROR
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                response_headers = MutableHeaders(scope=message)
                response_headers[REQUEST_ID_HEADER] = request_id
                for name, value in _SECURITY_HEADERS.items():
                    response_headers.setdefault(name, value)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.exception(
                "http.unhandled_exception",
                method=scope.get("method"),
                path=scope.get("path"),
            )
            if response_started:
                raise
            await unexpected_error_response(scope.get("path"))(scope, receive, send_wrapper)
        finally:
            self._log_request(scope, status_code, started)
            structlog.contextvars.unbind_contextvars("request_id")
            reset_request_id(token)

    @staticmethod
    def _log_request(scope: Scope, status_code: int, started: float) -> None:
        route = scope.get("route")
        route_template = getattr(route, "path", None)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        client = scope.get("client")
        fields = {
            "method": scope.get("method"),
            "path": scope.get("path"),
            "route": route_template,
            "status": status_code,
            "duration_ms": duration_ms,
            "client_ip": client[0] if client else None,
        }
        user_id = scope.get("state", {}).get("user_id")
        if user_id:
            fields["user_id"] = user_id
        if status_code >= _SERVER_ERROR:
            logger.error("http.request.completed", **fields)
        elif status_code >= _CLIENT_ERROR:
            logger.warning("http.request.completed", **fields)
        else:
            logger.info("http.request.completed", **fields)


class BodySizeLimitMiddleware:
    """Rejects request bodies larger than the configured limit with 413."""

    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_body_bytes:
            await self._reject(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise _BodyTooLargeError
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLargeError:
            await self._reject(scope, receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = problem_response(
            status_code=413,
            code="PAYLOAD_TOO_LARGE",
            title="Payload too large",
            detail=f"Request body exceeds the {self.max_body_bytes} byte limit.",
            instance=scope.get("path"),
        )
        await response(scope, receive, send)


class _BodyTooLargeError(Exception):
    pass
