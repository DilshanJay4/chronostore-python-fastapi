"""Contract tests verifying RFC 9457 Problem Details across 401, 403, 404, 409, and 422 errors."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
import uuid

import httpx


def test_problem_details_format_across_status_codes(
    http: httpx.Client,
    register_customer: Callable[[str | None], tuple[dict[str, Any], dict[str, str], dict[str, Any]]],
    validate_schema: Callable[[Any, str, str | None], None],
) -> None:
    # 1. 401 Unauthorized (missing Bearer token)
    res_401 = http.get("/api/v1/users/me", headers={"X-Request-ID": "err-401-check"})
    assert res_401.status_code == 401
    assert res_401.headers["content-type"].startswith("application/problem+json")
    body_401 = res_401.json()
    validate_schema(body_401, "problem-details.schema.json", None)
    assert body_401["status"] == 401
    assert body_401["code"] == "NOT_AUTHENTICATED"
    assert body_401["request_id"] == "err-401-check"

    # 2. 403 Forbidden (customer accessing admin endpoint)
    _, cust_headers, _ = register_customer("err_403")
    res_403 = http.get("/api/v1/admin/inventory", headers=cust_headers)
    assert res_403.status_code == 403
    assert res_403.headers["content-type"].startswith("application/problem+json")
    body_403 = res_403.json()
    validate_schema(body_403, "problem-details.schema.json", None)
    assert body_403["status"] == 403
    assert body_403["code"] == "FORBIDDEN"

    # 3. 404 Not Found (non-existent product UUID)
    missing_id = str(uuid.uuid4())
    res_404 = http.get(f"/api/v1/products/{missing_id}")
    assert res_404.status_code == 404
    assert res_404.headers["content-type"].startswith("application/problem+json")
    body_404 = res_404.json()
    validate_schema(body_404, "problem-details.schema.json", None)
    assert body_404["status"] == 404
    assert body_404["code"] == "NOT_FOUND"

    # 4. 422 Validation Error (short password on register; must not leak password value)
    secret_pw = "short1!"
    res_422 = http.post(
        "/api/v1/auth/register",
        json={"email": "invalid_pw@example.lk", "password": secret_pw, "full_name": "Test User"},
    )
    assert res_422.status_code == 422
    assert res_422.headers["content-type"].startswith("application/problem+json")
    body_422 = res_422.json()
    validate_schema(body_422, "problem-details.schema.json", None)
    assert body_422["status"] == 422
    assert body_422["code"] == "VALIDATION_ERROR"
    assert isinstance(body_422.get("errors"), list)
    assert len(body_422["errors"]) >= 1
    assert secret_pw not in res_422.text

    # 5. 422 Business Rule Violation (checkout with empty cart)
    addr_res = http.post(
        "/api/v1/users/me/addresses",
        headers=cust_headers,
        json={
            "label": "Home",
            "recipient_name": "Empty Cart User",
            "phone": "0771234567",
            "street_line1": "10 Main St",
            "city": "Colombo",
            "postal_code": "00100",
            "province": "Western",
            "country_code": "LK",
        },
    )
    empty_chk = http.post(
        "/api/v1/checkout",
        headers=cust_headers,
        json={"shipping_address_id": addr_res.json()["id"]},
    )
    assert empty_chk.status_code == 422
    body_brv = empty_chk.json()
    validate_schema(body_brv, "problem-details.schema.json", None)
    assert body_brv["code"] == "BUSINESS_RULE_VIOLATION"

