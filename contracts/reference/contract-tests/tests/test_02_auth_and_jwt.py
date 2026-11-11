"""Contract tests for authentication, JWT claims, refresh token rotation, and replay protection."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import httpx


def test_register_and_login_both_json_and_form(
    http: httpx.Client,
    validate_schema: Callable[[Any, str, str | None], None],
) -> None:
    uid = uuid.uuid4().hex[:8]
    email = f"auth_{uid}@contract-test.lk"
    password = "StrongPassword123!"

    # 1. Register
    reg_res = http.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Nimal Perera",
            "phone": "+94771122334",
        },
    )
    assert reg_res.status_code == 201
    user = reg_res.json()
    validate_schema(user, "auth-and-user.schema.json", "UserResponse")
    assert user["email"] == email
    assert user["role"] == "customer"
    assert user["is_active"] is True

    # 2. Duplicate registration returns 409 Conflict
    dup_res = http.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Duplicate User"},
    )
    assert dup_res.status_code == 409
    validate_schema(dup_res.json(), "problem-details.schema.json", None)
    assert dup_res.json()["code"] == "CONFLICT"

    # 3. Login via JSON ({"email", "password"})
    json_login = http.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert json_login.status_code == 200
    validate_schema(json_login.json(), "auth-and-user.schema.json", "TokenResponse")

    # 4. Login via OAuth2 form-urlencoded ("username", "password")
    form_login = http.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert form_login.status_code == 200
    validate_schema(form_login.json(), "auth-and-user.schema.json", "TokenResponse")


def test_refresh_rotation_and_replay_detection(
    http: httpx.Client,
    register_customer: Callable[[str | None], tuple[dict[str, Any], dict[str, str], dict[str, Any]]],
    validate_schema: Callable[[Any, str, str | None], None],
) -> None:
    _, _, tokens1 = register_customer("refresh")
    rt1 = tokens1["refresh_token"]

    # Rotate refresh token
    rot_res = http.post("/api/v1/auth/refresh", json={"refresh_token": rt1})
    assert rot_res.status_code == 200
    tokens2 = rot_res.json()
    validate_schema(tokens2, "auth-and-user.schema.json", "TokenResponse")
    rt2 = tokens2["refresh_token"]
    assert rt2 != rt1

    # Replay old refresh token -> must return 401 and invalidate family
    replay_res = http.post("/api/v1/auth/refresh", json={"refresh_token": rt1})
    assert replay_res.status_code == 401
    validate_schema(replay_res.json(), "problem-details.schema.json", None)

    # Subsequent use of rt2 must also be rejected (401)
    revoked_res = http.post("/api/v1/auth/refresh", json={"refresh_token": rt2})
    assert revoked_res.status_code == 401


def test_logout_revokes_refresh_token(
    http: httpx.Client,
    register_customer: Callable[[str | None], tuple[dict[str, Any], dict[str, str], dict[str, Any]]],
) -> None:
    _, _, tokens = register_customer("logout")
    rt = tokens["refresh_token"]

    logout_res = http.post("/api/v1/auth/logout", json={"refresh_token": rt})
    assert logout_res.status_code == 204

    refresh_after = http.post("/api/v1/auth/refresh", json={"refresh_token": rt})
    assert refresh_after.status_code == 401

