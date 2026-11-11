"""Contract tests for brands, categories, wristwatch products, filtering, sorting, and pagination."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx


def test_brands_and_categories_public_and_admin_rbac(
    http: httpx.Client,
    shared_catalog: dict[str, Any],
    register_customer: Callable[[str | None], tuple[dict[str, Any], dict[str, str], dict[str, Any]]],
    validate_schema: Callable[[Any, str, str | None], None],
) -> None:
    brand = shared_catalog["brand"]
    category = shared_catalog["category"]

    # Public brand & category list/detail
    b_list = http.get("/api/v1/brands")
    assert b_list.status_code == 200
    assert any(b["id"] == brand["id"] for b in b_list.json())

    b_get = http.get(f"/api/v1/brands/{brand['id']}")
    assert b_get.status_code == 200
    validate_schema(b_get.json(), "catalog.schema.json", "BrandResponse")

    c_list = http.get("/api/v1/categories")
    assert c_list.status_code == 200
    assert any(c["id"] == category["id"] for c in c_list.json())

    c_get = http.get(f"/api/v1/categories/{category['id']}")
    assert c_get.status_code == 200
    validate_schema(c_get.json(), "catalog.schema.json", "CategoryResponse")

    # Customer cannot create brand or category (403 Forbidden)
    _, cust_headers, _ = register_customer("cat_rbac")
    forb_b = http.post(
        "/api/v1/brands",
        headers=cust_headers,
        json={"name": "Unauthorized Brand", "slug": "unauth-brand"},
    )
    assert forb_b.status_code == 403
    validate_schema(forb_b.json(), "problem-details.schema.json", None)


def test_products_filtering_sorting_and_pagination(
    http: httpx.Client,
    shared_catalog: dict[str, Any],
    admin_headers: dict[str, str],
    validate_schema: Callable[[Any, str, str | None], None],
) -> None:
    brand = shared_catalog["brand"]
    budget_watch = shared_catalog["budget_watch"]
    luxury_watch = shared_catalog["luxury_watch"]

    # 1. Filter by brand_id and sort by price_asc
    res_asc = http.get(
        "/api/v1/products",
        params={"brand_id": brand["id"], "sort_by": "price_asc", "page": 1, "page_size": 10},
    )
    assert res_asc.status_code == 200
    page_data = res_asc.json()
    validate_schema(page_data, "pagination.schema.json", None)
    assert page_data["total"] == 2
    items = page_data["items"]
    assert items[0]["id"] == budget_watch["id"]
    assert items[1]["id"] == luxury_watch["id"]
    for item in items:
        validate_schema(item, "catalog.schema.json", "ProductResponse")
        # Public caller should not see exact available_stock count
        assert item["available_stock"] is None

    # 2. Filter by movement_type=automatic
    res_auto = http.get(
        "/api/v1/products",
        params={"brand_id": brand["id"], "movement_type": "automatic"},
    )
    assert res_auto.status_code == 200
    assert res_auto.json()["total"] == 1
    assert res_auto.json()["items"][0]["id"] == luxury_watch["id"]

    # 3. Admin detail call includes available_stock integer
    res_admin_detail = http.get(
        f"/api/v1/products/{budget_watch['id']}",
        headers=admin_headers,
    )
    assert res_admin_detail.status_code == 200
    assert isinstance(res_admin_detail.json()["available_stock"], int)

