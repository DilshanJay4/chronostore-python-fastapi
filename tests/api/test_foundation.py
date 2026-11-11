import uuid

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import LogCapture

pytestmark = pytest.mark.db


def test_liveness(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_checks_database_and_migrations(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ok", "migrations": "ok"}


def test_request_id_is_generated_when_absent(client: TestClient) -> None:
    response = client.get("/health/live")
    request_id = response.headers["X-Request-ID"]
    assert uuid.UUID(hex=request_id)


def test_valid_incoming_request_id_is_propagated(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "client-abc-12345"})
    assert response.headers["X-Request-ID"] == "client-abc-12345"


def test_unsafe_incoming_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "bad id\twith spaces"})
    assert response.headers["X-Request-ID"] != "bad id\twith spaces"


def test_security_headers_present(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_unknown_route_returns_problem_details(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist", headers={"X-Request-ID": "trace-0000001"})
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 404
    assert body["code"] == "NOT_FOUND"
    assert body["type"].startswith("urn:chronostore:problem:")
    assert body["instance"] == "/api/v1/does-not-exist"
    assert body["request_id"] == "trace-0000001"


def test_oversized_body_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/anything", content=b"x" * 2_000_000, headers={"Content-Type": "text/plain"}
    )
    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"


@pytest.fixture
def boom_app(migrated_database: str) -> FastAPI:
    app = create_app()
    router = APIRouter()

    @router.get("/boom")
    def boom() -> None:
        raise RuntimeError("database password=hunter2 leaked?")

    app.include_router(router)
    return app


def test_unexpected_exception_returns_safe_500_and_logs_once(
    boom_app: FastAPI, log_capture: LogCapture
) -> None:
    with TestClient(boom_app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/boom", headers={"X-Request-ID": "boom-request-1"})

    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "INTERNAL_ERROR"
    assert body["request_id"] == "boom-request-1"
    assert "hunter2" not in response.text
    assert "RuntimeError" not in response.text

    errors = log_capture.events("http.unhandled_exception")
    assert len(errors) == 1
    assert errors[0]["request_id"] == "boom-request-1"
    assert errors[0]["level"] == "error"
    assert "RuntimeError" in errors[0]["exception"]
    completed = log_capture.events("http.request.completed")
    assert completed[-1]["status"] == 500
    assert completed[-1]["route"] == "/boom"


def test_request_log_contains_structured_fields(
    client: TestClient, log_capture: LogCapture
) -> None:
    client.get(
        "/health/live",
        headers={"X-Request-ID": "log-fields-1", "Authorization": "Bearer abc.def.ghi"},
    )
    record = log_capture.events("http.request.completed")[-1]
    assert record["request_id"] == "log-fields-1"
    assert record["method"] == "GET"
    assert record["route"] == "/health/live"
    assert record["status"] == 200
    assert record["level"] == "info"
    assert record["logger"] == "app.http"
    assert record["environment"] == "testing"
    assert "timestamp" in record
    assert "duration_ms" in record
    assert "abc.def.ghi" not in log_capture.stream.getvalue()
