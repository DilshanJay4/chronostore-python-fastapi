"""Contract tests for health endpoints, correlation headers, security headers, and OpenAPI spec."""

from __future__ import annotations

import uuid
from typing import Any

import httpx


def test_liveness_probe(http: httpx.Client) -> None:
    res = http.get("/health/live")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
    assert "X-Request-ID" in res.headers


def test_readiness_probe(http: httpx.Client) -> None:
    res = http.get("/health/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"


def test_request_id_generation_and_propagation(http: httpx.Client) -> None:
    # 1. Generated when absent
    res_gen = http.get("/health/live")
    generated_id = res_gen.headers.get("X-Request-ID")
    assert generated_id is not None
    uuid.UUID(generated_id)

    # 2. Echoed when valid
    custom_id = "contract-trace-2026-0001"
    res_echo = http.get("/health/live", headers={"X-Request-ID": custom_id})
    assert res_echo.headers.get("X-Request-ID") == custom_id


def test_security_headers_present(http: httpx.Client) -> None:
    res = http.get("/health/live")
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"


def test_canonical_openapi_spec_is_valid(openapi_spec: dict[str, Any]) -> None:
    assert openapi_spec["openapi"].startswith("3.1.")
    assert openapi_spec["info"]["title"] == "ChronoStore API"
    assert openapi_spec["info"]["version"] == "1.0.0"
    paths = openapi_spec["paths"]
    assert "/health/live" in paths
    assert "/health/ready" in paths
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/products" in paths
    assert "/api/v1/checkout" in paths
    assert "/api/v1/orders/{order_id}/shipments" in paths
    assert "/api/v1/returns/{return_id}" in paths

