import uuid

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.db


def test_e2e_api_customer_and_admin_flows(client: TestClient) -> None:
    # 1. Register Customer
    res_reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": "e2e_customer@example.lk",
            "password": "Password123!",
            "full_name": "E2E Customer",
            "phone": "+94770001122",
        },
    )
    assert res_reg.status_code == 201
    assert "id" in res_reg.json()

    # 2. Login as Customer (using OAuth2 form)
    res_login = client.post(
        "/api/v1/auth/login",
        data={"username": "e2e_customer@example.lk", "password": "Password123!"},
    )
    assert res_login.status_code == 200
    token_data = res_login.json()
    access_token = token_data["access_token"]
    auth_header = {"Authorization": f"Bearer {access_token}"}

    # 3. Add address
    res_addr = client.post(
        "/api/v1/users/me/addresses",
        headers=auth_header,
        json={
            "label": "Apartment",
            "recipient_name": "E2E Customer",
            "phone": "0770001122",
            "street_line1": "Flat 4B, Colombo 03",
            "city": "Colombo",
            "postal_code": "00300",
            "province": "Western",
            "country_code": "LK",
        },
    )
    assert res_addr.status_code == 201
    address_id = res_addr.json()["id"]

    # 4. Attempt to create brand as non-admin -> 403 Forbidden
    res_forbidden = client.post(
        "/api/v1/brands",
        headers=auth_header,
        json={"name": "Audemars Piguet", "slug": "ap"},
    )
    assert res_forbidden.status_code == 403

    # 5. Create an Admin User directly or test admin endpoints
    # Register admin user via test session directly
    from app.core.config import get_settings
    from app.core.security import create_access_token
    from app.db.session import get_session_factory
    from app.domain.enums import UserRole
    from app.schemas.users import UserRegisterRequest
    from app.services.auth import AuthService

    settings = get_settings()
    admin_id = uuid.uuid4()
    with get_session_factory()() as session:
        auth_svc = AuthService(session, settings)
        admin = auth_svc.register(
            UserRegisterRequest(
                email="superadmin@chronostore.lk",
                password="SuperSecretPassword123!",
                full_name="Super Admin",
            ),
            role=UserRole.ADMIN,
        )
        admin_id = admin.id

    admin_token = create_access_token(admin_id, UserRole.ADMIN.value, settings)
    admin_header = {"Authorization": f"Bearer {admin_token}"}

    # 6. Admin creates Brand, Category, and Product
    res_brand = client.post(
        "/api/v1/brands",
        headers=admin_header,
        json={"name": "Omega", "slug": "omega", "description": "Swiss luxury watches"},
    )
    assert res_brand.status_code == 201
    brand_id = res_brand.json()["id"]

    res_cat = client.post(
        "/api/v1/categories",
        headers=admin_header,
        json={"name": "Moonwatch", "slug": "moonwatch"},
    )
    assert res_cat.status_code == 201
    cat_id = res_cat.json()["id"]

    res_prod = client.post(
        "/api/v1/products",
        headers=admin_header,
        json={
            "sku": "SPEEDMASTER-PROF",
            "name": "Omega Speedmaster Professional Moonwatch",
            "model": "Speedmaster",
            "description": "The Moonwatch chronograph with Co-Axial Master Chronometer cal. 3861.",
            "brand_id": brand_id,
            "category_id": cat_id,
            "movement_type": "manual",
            "case_material": "Stainless Steel",
            "strap_material": "Stainless Steel",
            "water_resistance": "50m",
            "dial_color": "Black",
            "price_lkr": 2500000.00,
            "status": "published",
            "initial_stock": 5,
        },
    )
    assert res_prod.status_code == 201
    product_id = res_prod.json()["id"]

    # 7. Customer browses catalog
    res_list = client.get("/api/v1/products?search=moonwatch")
    assert res_list.status_code == 200
    assert res_list.json()["total"] == 1

    # 8. Customer adds item to cart
    res_cart = client.post(
        "/api/v1/cart/items",
        headers=auth_header,
        json={"product_id": product_id, "quantity": 1},
    )
    assert res_cart.status_code == 201
    assert res_cart.json()["item_count"] == 1

    # 9. Customer Checkouts
    res_chk = client.post(
        "/api/v1/checkout",
        headers={**auth_header, "Idempotency-Key": "e2e-idem-1"},
        json={"shipping_address_id": address_id, "customer_notes": "Urgent delivery please"},
    )
    assert res_chk.status_code == 201
    order_id = res_chk.json()["id"]
    assert res_chk.json()["status"] == "placed"

    # 10. Admin creates shipment and dispatches
    res_ship = client.post(
        f"/api/v1/admin/orders/{order_id}/shipments",
        headers=admin_header,
        json={"tracking_number": "CERTIS-E2E-12345", "carrier": "Certis Lanka"},
    )
    assert res_ship.status_code == 201
    shipment_id = res_ship.json()["id"]

    res_dispatch = client.patch(
        f"/api/v1/admin/shipments/{shipment_id}/status",
        headers=admin_header,
        json={"status": "dispatched", "notes": "Handed to courier"},
    )
    assert res_dispatch.status_code == 200
    assert res_dispatch.json()["status"] == "dispatched"

    # 11. Admin reports
    res_report = client.get("/api/v1/admin/reports/sales", headers=admin_header)
    assert res_report.status_code == 200
    assert "daily_breakdown" in res_report.json()

    res_orders_rep = client.get("/api/v1/admin/reports/orders", headers=admin_header)
    assert res_orders_rep.status_code == 200
    assert len(res_orders_rep.json()) >= 1
