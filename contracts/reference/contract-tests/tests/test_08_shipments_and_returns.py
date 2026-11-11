"""Contract tests for end-to-end fulfillment (shipments) and customer return/inspection/restock/refund."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
import uuid

import httpx


def test_shipment_delivery_and_return_inspection_restock_workflow(
    http: httpx.Client,
    shared_catalog: dict[str, Any],
    admin_headers: dict[str, str],
    register_customer: Callable[[str | None], tuple[dict[str, Any], dict[str, str], dict[str, Any]]],
    validate_schema: Callable[[Any, str, str | None], None],
) -> None:
    _, cust_headers, _ = register_customer("fulfill")
    _, other_headers, _ = register_customer("fulfill_other")
    luxury_watch = shared_catalog["luxury_watch"]
    product_id = luxury_watch["id"]

    # Check stock before order
    prod_before = http.get(f"/api/v1/products/{product_id}", headers=admin_headers).json()
    avail_before = prod_before["available_stock"]

    # 1. Customer places order for 1 luxury watch
    addr_res = http.post(
        "/api/v1/users/me/addresses",
        headers=cust_headers,
        json={
            "label": "Home",
            "recipient_name": "Fulfillment Customer",
            "phone": "0778889900",
            "street_line1": "77 Rosmead Place",
            "city": "Colombo",
            "postal_code": "00700",
            "province": "Western",
            "country_code": "LK",
        },
    )
    addr_id = addr_res.json()["id"]

    http.post(
        "/api/v1/cart/items",
        headers=cust_headers,
        json={"product_id": product_id, "quantity": 1},
    )
    order_res = http.post(
        "/api/v1/checkout",
        headers=cust_headers,
        json={"shipping_address_id": addr_id},
    )
    assert order_res.status_code == 201
    order = order_res.json()
    order_id = order["id"]
    order_item_id = order["items"][0]["id"]

    # 2. Admin creates shipment -> order transitions from placed to confirmed
    tracking_no = f"CERTIS-CT-{uuid.uuid4().hex[:8].upper()}"
    ship_res = http.post(
        f"/api/v1/admin/orders/{order_id}/shipments",
        headers=admin_headers,
        json={
            "tracking_number": tracking_no,
            "carrier": "Certis Lanka",
            "notes": "Insured watch parcel",
        },
    )
    assert ship_res.status_code == 201
    shipment = ship_res.json()
    validate_schema(shipment, "fulfillment-and-return.schema.json", "ShipmentResponse")
    shipment_id = shipment["id"]
    assert shipment["status"] == "pending"

    # Verify shipment ownership protection: other customer gets 403 Forbidden
    forb_ship = http.get(f"/api/v1/orders/{order_id}/shipments", headers=other_headers)
    assert forb_ship.status_code == 403

    # Owner can list order shipments
    own_ship = http.get(f"/api/v1/orders/{order_id}/shipments", headers=cust_headers)
    assert own_ship.status_code == 200
    assert len(own_ship.json()) == 1

    # 3. Admin dispatches shipment -> order becomes shipped
    disp_res = http.patch(
        f"/api/v1/admin/shipments/{shipment_id}/status",
        headers=admin_headers,
        json={"status": "dispatched", "notes": "Dispatched from Colombo hub"},
    )
    assert disp_res.status_code == 200
    assert disp_res.json()["status"] == "dispatched"

    # 4. Admin marks shipment delivered -> order becomes delivered
    deliv_res = http.patch(
        f"/api/v1/admin/shipments/{shipment_id}/status",
        headers=admin_headers,
        json={"status": "delivered", "notes": "Signed by recipient"},
    )
    assert deliv_res.status_code == 200
    assert deliv_res.json()["status"] == "delivered"

    # 5. Admin collects Cash on Delivery payment
    cod_res = http.post(
        f"/api/v1/admin/orders/{order_id}/payment/collect",
        headers=admin_headers,
        json={"collection_reference": f"COD-{tracking_no}", "notes": "Cash collected"},
    )
    assert cod_res.status_code == 200
    assert cod_res.json()["payment"]["status"] == "collected"

    # 6. Customer requests a return
    ret_create = http.post(
        f"/api/v1/orders/{order_id}/returns",
        headers=cust_headers,
        json={
            "reason": "defective",
            "customer_notes": "Bezel alignment is slightly off-center.",
            "items": [{"order_item_id": order_item_id, "quantity": 1}],
        },
    )
    assert ret_create.status_code == 201
    ret_data = ret_create.json()
    validate_schema(ret_data, "fulfillment-and-return.schema.json", "ReturnResponse")
    return_id = ret_data["id"]
    assert ret_data["status"] == "requested"

    # Other customer cannot view return request (403 Forbidden)
    forb_ret = http.get(f"/api/v1/returns/{return_id}", headers=other_headers)
    assert forb_ret.status_code == 403

    # Owner can view return request
    own_ret = http.get(f"/api/v1/returns/{return_id}", headers=cust_headers)
    assert own_ret.status_code == 200

    # 7. Admin approves return request
    rev_res = http.post(
        f"/api/v1/admin/returns/{return_id}/review",
        headers=admin_headers,
        json={"approved": True, "admin_notes": "Approved for watchmaker inspection"},
    )
    assert rev_res.status_code == 200
    assert rev_res.json()["status"] == "approved"

    # 8. Admin receives returned package
    rec_res = http.post(f"/api/v1/admin/returns/{return_id}/receive", headers=admin_headers)
    assert rec_res.status_code == 200
    assert rec_res.json()["status"] == "received"

    # 9. Admin inspects return as resellable with restock_resellable=True
    insp_res = http.post(
        f"/api/v1/admin/returns/{return_id}/inspect",
        headers=admin_headers,
        json={
            "outcome": "resellable",
            "notes": "Bezel ring realigned; watch in mint condition.",
            "restock_resellable": True,
        },
    )
    assert insp_res.status_code == 200
    assert insp_res.json()["status"] == "inspected"
    assert insp_res.json()["restocked"] is True

    # Verify stock was restored to avail_before
    prod_after = http.get(f"/api/v1/products/{product_id}", headers=admin_headers).json()
    assert prod_after["available_stock"] == avail_before

    # 10. Admin records refund
    ref_res = http.post(
        f"/api/v1/admin/returns/{return_id}/refund",
        headers=admin_headers,
        json={
            "refund_amount_lkr": "125000.00",
            "refund_method": "bank_transfer",
            "refund_reference": f"SAMPATH-{uuid.uuid4().hex[:6].upper()}",
        },
    )
    assert ref_res.status_code == 200
    refunded = ref_res.json()
    validate_schema(refunded, "fulfillment-and-return.schema.json", "ReturnResponse")
    assert refunded["status"] == "refunded"
    assert refunded["refund_amount_lkr"] == "125000.00"

