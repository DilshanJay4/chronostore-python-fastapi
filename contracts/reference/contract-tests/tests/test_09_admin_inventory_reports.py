"""Contract tests for admin inventory adjustments, movement ledger, reports, and audit logs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx


def test_admin_inventory_adjustments_and_movements(
    http: httpx.Client,
    shared_catalog: dict[str, Any],
    admin_headers: dict[str, str],
) -> None:
    budget_watch = shared_catalog["budget_watch"]
    product_id = budget_watch["id"]

    # 1. List inventory
    inv_list = http.get("/api/v1/admin/inventory", headers=admin_headers)
    assert inv_list.status_code == 200
    item_before = next(i for i in inv_list.json() if i["product_id"] == product_id)
    on_hand_before = item_before["on_hand"]

    # 2. Adjust stock (+5 restock)
    adj_res = http.post(
        "/api/v1/admin/inventory/adjustments",
        headers=admin_headers,
        json={
            "product_id": product_id,
            "quantity_delta": 5,
            "reason": "restock",
            "notes": "Contract test restock shipment",
        },
    )
    assert adj_res.status_code == 200
    assert adj_res.json()["on_hand"] == on_hand_before + 5

    # 3. Verify movement history endpoint
    mov_res = http.get(
        "/api/v1/admin/inventory/movements",
        headers=admin_headers,
        params={"product_id": product_id},
    )
    assert mov_res.status_code == 200
    movements = mov_res.json()
    assert len(movements) >= 1
    assert movements[0]["product_id"] == product_id
    assert movements[0]["quantity_delta"] == 5


def test_admin_reports_and_audit_logs(
    http: httpx.Client,
    admin_headers: dict[str, str],
    validate_schema: Callable[[Any, str, str | None], None],
) -> None:
    # 1. Sales report
    sales_res = http.get("/api/v1/admin/reports/sales", headers=admin_headers)
    assert sales_res.status_code == 200
    validate_schema(sales_res.json(), "reports-and-audit.schema.json", "SalesReportResponse")

    # 2. Orders by status report
    ord_rep = http.get("/api/v1/admin/reports/orders", headers=admin_headers)
    assert ord_rep.status_code == 200
    assert isinstance(ord_rep.json(), list)

    # 3. Best sellers report
    best_rep = http.get(
        "/api/v1/admin/reports/best-sellers",
        headers=admin_headers,
        params={"limit": 5},
    )
    assert best_rep.status_code == 200
    assert isinstance(best_rep.json(), list)

    # 4. Low stock inventory report
    low_rep = http.get("/api/v1/admin/reports/inventory", headers=admin_headers)
    assert low_rep.status_code == 200
    assert isinstance(low_rep.json(), list)

    # 5. Audit logs
    audit_res = http.get(
        "/api/v1/admin/audit-logs",
        headers=admin_headers,
        params={"limit": 20},
    )
    assert audit_res.status_code == 200
    logs = audit_res.json()
    assert len(logs) >= 1
    for entry in logs:
        validate_schema(entry, "reports-and-audit.schema.json", "AuditLogResponse")

