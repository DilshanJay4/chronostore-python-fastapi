"""Contract tests for idempotent checkout and concurrent last-item stock reservation."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any
import uuid

import httpx


def test_idempotent_checkout_and_payload_mismatch(
    http: httpx.Client,
    shared_catalog: dict[str, Any],
    register_customer: Callable[[str | None], tuple[dict[str, Any], dict[str, str], dict[str, Any]]],
    validate_schema: Callable[[Any, str, str | None], None],
) -> None:
    _, headers, _ = register_customer("idem")
    luxury_watch = shared_catalog["luxury_watch"]

    # Create shipping address
    addr_res = http.post(
        "/api/v1/users/me/addresses",
        headers=headers,
        json={
            "label": "Home",
            "recipient_name": "Idem Buyer",
            "phone": "0771112233",
            "street_line1": "100 Galle Face",
            "city": "Colombo",
            "postal_code": "00100",
            "province": "Western",
            "country_code": "LK",
        },
    )
    assert addr_res.status_code == 201
    addr_id = addr_res.json()["id"]

    # Add 1 watch to cart
    http.post(
        "/api/v1/cart/items",
        headers=headers,
        json={"product_id": luxury_watch["id"], "quantity": 1},
    )

    idem_key = f"idem-key-{uuid.uuid4().hex}"
    checkout_payload = {
        "shipping_address_id": addr_id,
        "customer_notes": "Deliver before 5pm",
    }

    # 1. First checkout -> 201 Created
    res1 = http.post(
        "/api/v1/checkout",
        headers={**headers, "Idempotency-Key": idem_key},
        json=checkout_payload,
    )
    assert res1.status_code == 201
    order1 = res1.json()
    validate_schema(order1, "order-and-payment.schema.json", "OrderResponse")
    assert order1["status"] == "placed"
    assert order1["total_lkr"] == "125000.00"
    assert order1["payment"]["status"] == "pending"
    assert order1["payment"]["method"] == "cash_on_delivery"

    # 2. Replay identical request with same Idempotency-Key -> 200 OK + Idempotent-Replayed: true
    res2 = http.post(
        "/api/v1/checkout",
        headers={**headers, "Idempotency-Key": idem_key},
        json=checkout_payload,
    )
    assert res2.status_code == 200
    assert res2.headers.get("Idempotent-Replayed") == "true"
    assert res2.json()["id"] == order1["id"]

    # 3. Replay same Idempotency-Key with different payload -> 409 Conflict
    res_mismatch = http.post(
        "/api/v1/checkout",
        headers={**headers, "Idempotency-Key": idem_key},
        json={"shipping_address_id": addr_id, "customer_notes": "Different notes!"},
    )
    assert res_mismatch.status_code == 409
    validate_schema(res_mismatch.json(), "problem-details.schema.json", None)


def test_concurrent_last_item_checkout_prevents_overselling(
    base_url: str,
    http: httpx.Client,
    shared_catalog: dict[str, Any],
    admin_headers: dict[str, str],
    register_customer: Callable[[str | None], tuple[dict[str, Any], dict[str, str], dict[str, Any]]],
) -> None:
    """Two customers simultaneously attempt to checkout the last remaining item in stock."""
    brand = shared_catalog["brand"]
    category = shared_catalog["category"]
    uid = uuid.uuid4().hex[:8]

    # Admin creates a limited-edition watch with initial_stock = 1
    prod_res = http.post(
        "/api/v1/products",
        headers=admin_headers,
        json={
            "sku": f"LIMITED-1-{uid.upper()}",
            "name": f"Limited Edition 1-of-1 Watch {uid}",
            "model": f"LE-{uid}",
            "description": "Single unit stock watch to verify row-level locking under race.",
            "brand_id": brand["id"],
            "category_id": category["id"],
            "movement_type": "manual",
            "case_material": "Platinum",
            "strap_material": "Alligator Leather",
            "water_resistance": "30m",
            "dial_color": "Champagne",
            "image_urls": [],
            "price_lkr": "450000.00",
            "status": "published",
            "initial_stock": 1,
        },
    )
    assert prod_res.status_code == 201
    limited_product_id = prod_res.json()["id"]

    # Prepare two independent customers, each with the 1-stock watch in their cart
    buyers = []
    for i in range(2):
        _, cust_headers, _ = register_customer(f"race{i}")
        addr_r = http.post(
            "/api/v1/users/me/addresses",
            headers=cust_headers,
            json={
                "label": "Home",
                "recipient_name": f"Race Buyer {i}",
                "phone": "0771234567",
                "street_line1": "10 Race Course Ave",
                "city": "Colombo",
                "postal_code": "00700",
                "province": "Western",
                "country_code": "LK",
            },
        )
        assert addr_r.status_code == 201
        cart_r = http.post(
            "/api/v1/cart/items",
            headers=cust_headers,
            json={"product_id": limited_product_id, "quantity": 1},
        )
        assert cart_r.status_code == 201
        buyers.append((cust_headers, addr_r.json()["id"]))

    def _attempt_checkout(buyer_tuple: tuple[dict[str, str], str]) -> int:
        hdrs, address_id = buyer_tuple
        with httpx.Client(base_url=base_url, timeout=15.0) as client:
            r = client.post(
                "/api/v1/checkout",
                headers=hdrs,
                json={"shipping_address_id": address_id},
            )
            return r.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(_attempt_checkout, buyers))

    # Exactly one must succeed (201) and one must fail with 409 Conflict
    assert statuses == [201, 409], f"Expected [201, 409] on last-item race, got {statuses}"

