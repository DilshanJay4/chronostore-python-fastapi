"""Contract tests for shopping cart operations and LKR shipping fee / decimal pricing rules."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx


def test_cart_item_lifecycle_and_lkr_shipping_threshold(
    http: httpx.Client,
    shared_catalog: dict[str, Any],
    register_customer: Callable[[str | None], tuple[dict[str, Any], dict[str, str], dict[str, Any]]],
    validate_schema: Callable[[Any, str, str | None], None],
) -> None:
    _, headers, _ = register_customer("cart")
    budget_watch = shared_catalog["budget_watch"]  # 24,500.00 LKR

    # 1. Empty cart initially
    empty_res = http.get("/api/v1/cart", headers=headers)
    assert empty_res.status_code == 200
    validate_schema(empty_res.json(), "cart.schema.json", None)
    assert empty_res.json()["item_count"] == 0
    assert empty_res.json()["total"]["amount"] == "0.00"

    # 2. Add 1 budget watch (24,500.00 LKR < 50,000.00 LKR threshold -> 500.00 LKR shipping)
    add_res = http.post(
        "/api/v1/cart/items",
        headers=headers,
        json={"product_id": budget_watch["id"], "quantity": 1},
    )
    assert add_res.status_code == 201
    cart1 = add_res.json()
    validate_schema(cart1, "cart.schema.json", None)
    assert cart1["subtotal"]["amount"] == "24500.00"
    assert cart1["shipping_fee"]["amount"] == "500.00"
    assert cart1["total"]["amount"] == "25000.00"
    item_id = cart1["items"][0]["id"]

    # 3. Update quantity to 3 (73,500.00 LKR >= 50,000.00 LKR -> 0.00 LKR free shipping)
    upd_res = http.patch(
        f"/api/v1/cart/items/{item_id}",
        headers=headers,
        json={"quantity": 3},
    )
    assert upd_res.status_code == 200
    cart2 = upd_res.json()
    validate_schema(cart2, "cart.schema.json", None)
    assert cart2["subtotal"]["amount"] == "73500.00"
    assert cart2["shipping_fee"]["amount"] == "0.00"
    assert cart2["total"]["amount"] == "73500.00"
    assert cart2["item_count"] == 3

    # 4. Remove item from cart
    rem_res = http.delete(f"/api/v1/cart/items/{item_id}", headers=headers)
    assert rem_res.status_code == 200
    assert rem_res.json()["item_count"] == 0

    # 5. Re-add and clear entire cart
    http.post(
        "/api/v1/cart/items",
        headers=headers,
        json={"product_id": budget_watch["id"], "quantity": 1},
    )
    clr_res = http.delete("/api/v1/cart", headers=headers)
    assert clr_res.status_code == 204

