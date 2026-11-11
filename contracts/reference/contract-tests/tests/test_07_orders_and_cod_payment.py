"""Contract tests for orders, object-level ownership, customer cancellation, and COD collection."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx


def test_order_ownership_cancellation_and_cod_collection(
    http: httpx.Client,
    shared_catalog: dict[str, Any],
    admin_headers: dict[str, str],
    register_customer: Callable[[str | None], tuple[dict[str, Any], dict[str, str], dict[str, Any]]],
    validate_schema: Callable[[Any, str, str | None], None],
) -> None:
    _, owner_headers, _ = register_customer("ord_owner")
    _, other_headers, _ = register_customer("ord_other")
    budget_watch = shared_catalog["budget_watch"]

    # Owner creates address, adds item, and checks out
    addr_res = http.post(
        "/api/v1/users/me/addresses",
        headers=owner_headers,
        json={
            "label": "Home",
            "recipient_name": "Order Owner",
            "phone": "0775556677",
            "street_line1": "25 Ward Place",
            "city": "Colombo",
            "postal_code": "00700",
            "province": "Western",
            "country_code": "LK",
        },
    )
    addr_id = addr_res.json()["id"]

    http.post(
        "/api/v1/cart/items",
        headers=owner_headers,
        json={"product_id": budget_watch["id"], "quantity": 1},
    )
    chk_res = http.post(
        "/api/v1/checkout",
        headers=owner_headers,
        json={"shipping_address_id": addr_id},
    )
    assert chk_res.status_code == 201
    order = chk_res.json()
    order_id = order["id"]

    # 1. List orders for owner
    list_res = http.get("/api/v1/orders", headers=owner_headers)
    assert list_res.status_code == 200
    assert any(o["id"] == order_id for o in list_res.json())

    # 2. Other customer cannot view or cancel owner's order (403 Forbidden)
    forb_get = http.get(f"/api/v1/orders/{order_id}", headers=other_headers)
    assert forb_get.status_code == 403
    validate_schema(forb_get.json(), "problem-details.schema.json", None)

    forb_cancel = http.post(
        f"/api/v1/orders/{order_id}/cancel",
        headers=other_headers,
        json={"reason": "Unauthorized cancel attempt"},
    )
    assert forb_cancel.status_code == 403

    # 3. Owner views payment status
    pay_res = http.get(f"/api/v1/orders/{order_id}/payment", headers=owner_headers)
    assert pay_res.status_code == 200
    validate_schema(pay_res.json(), "order-and-payment.schema.json", "PaymentResponse")
    assert pay_res.json()["status"] == "pending"

    # 4. Owner cancels order -> status becomes cancelled, payment becomes voided
    cancel_res = http.post(
        f"/api/v1/orders/{order_id}/cancel",
        headers=owner_headers,
        json={"reason": "Ordered wrong watch model by mistake"},
    )
    assert cancel_res.status_code == 200
    cancelled_order = cancel_res.json()
    validate_schema(cancelled_order, "order-and-payment.schema.json", "OrderResponse")
    assert cancelled_order["status"] == "cancelled"
    assert cancelled_order["payment"]["status"] == "voided"

    # 5. Cannot collect COD on voided payment (409 InvalidStateTransitionError)
    collect_voided = http.post(
        f"/api/v1/admin/orders/{order_id}/payment/collect",
        headers=admin_headers,
        json={"collection_reference": "INVALID-COLLECT"},
    )
    assert collect_voided.status_code == 409
    assert collect_voided.json()["code"] == "INVALID_STATE_TRANSITION"

