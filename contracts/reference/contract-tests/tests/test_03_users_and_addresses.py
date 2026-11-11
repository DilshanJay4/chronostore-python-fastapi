"""Contract tests for user profile and Sri Lankan delivery address management."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx


def test_profile_and_address_lifecycle(
    http: httpx.Client,
    register_customer: Callable[[str | None], tuple[dict[str, Any], dict[str, str], dict[str, Any]]],
    validate_schema: Callable[[Any, str, str | None], None],
) -> None:
    _, headers, _ = register_customer("profile")

    # 1. Get current user
    me_res = http.get("/api/v1/users/me", headers=headers)
    assert me_res.status_code == 200
    validate_schema(me_res.json(), "auth-and-user.schema.json", "UserResponse")

    # 2. Update profile
    patch_res = http.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"full_name": "Updated Contract Name", "phone": "+94719998877"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["full_name"] == "Updated Contract Name"
    assert patch_res.json()["phone"] == "+94719998877"

    # 3. Create first address (automatically becomes default)
    a1_res = http.post(
        "/api/v1/users/me/addresses",
        headers=headers,
        json={
            "label": "Home",
            "recipient_name": "Updated Contract Name",
            "phone": "0719998877",
            "street_line1": "12 Flower Road",
            "city": "Colombo",
            "postal_code": "00700",
            "province": "Western",
            "country_code": "LK",
            "is_default": False,
        },
    )
    assert a1_res.status_code == 201
    addr1 = a1_res.json()
    validate_schema(addr1, "auth-and-user.schema.json", "AddressResponse")
    assert addr1["is_default"] is True

    # 4. Create second address marked default -> unsets first address default
    a2_res = http.post(
        "/api/v1/users/me/addresses",
        headers=headers,
        json={
            "label": "Office",
            "recipient_name": "Updated Contract Name",
            "phone": "0812223344",
            "street_line1": "88 Dalada Veediya",
            "city": "Kandy",
            "postal_code": "20000",
            "province": "Central",
            "country_code": "LK",
            "is_default": True,
        },
    )
    assert a2_res.status_code == 201
    addr2 = a2_res.json()
    assert addr2["is_default"] is True

    # 5. List addresses and verify single-default invariant
    list_res = http.get("/api/v1/users/me/addresses", headers=headers)
    assert list_res.status_code == 200
    addresses = list_res.json()
    assert len(addresses) == 2
    defaults = [a for a in addresses if a["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["id"] == addr2["id"]

    # 6. Update first address and delete second address
    upd_res = http.patch(
        f"/api/v1/users/me/addresses/{addr1['id']}",
        headers=headers,
        json={"label": "Colombo Residence", "is_default": True},
    )
    assert upd_res.status_code == 200
    assert upd_res.json()["label"] == "Colombo Residence"
    assert upd_res.json()["is_default"] is True

    del_res = http.delete(f"/api/v1/users/me/addresses/{addr2['id']}", headers=headers)
    assert del_res.status_code == 204

