"""Shared fixtures and JSON Schema validators for the ChronoStore Contract Test Suite."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import jsonschema
import pytest
import yaml


def _resolve_contracts_dir() -> Path:
    env_root = os.environ.get("CONTRACTS_ROOT")
    candidates = []
    if env_root:
        candidates.append(Path(env_root))
    parent = Path(__file__).resolve().parents[2]
    candidates.extend([parent / "contracts", parent])
    for candidate in candidates:
        if (candidate / "openapi" / "chronostore-v1.yaml").exists():
            return candidate
        if (candidate / "contracts" / "openapi" / "chronostore-v1.yaml").exists():
            return candidate / "contracts"
    raise FileNotFoundError("Could not locate canonical contracts directory (openapi/chronostore-v1.yaml).")


@pytest.fixture(scope="session")
def contracts_dir() -> Path:
    return _resolve_contracts_dir()


@pytest.fixture(scope="session")
def openapi_spec(contracts_dir: Path) -> dict[str, Any]:
    spec_path = contracts_dir / "openapi" / "chronostore-v1.yaml"
    with spec_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def json_schemas(contracts_dir: Path) -> dict[str, dict[str, Any]]:
    schemas_dir = contracts_dir / "schemas"
    loaded: dict[str, dict[str, Any]] = {}
    for path in schemas_dir.glob("*.schema.json"):
        with path.open("r", encoding="utf-8") as f:
            loaded[path.name] = json.load(f)
    return loaded


@pytest.fixture(scope="session")
def validate_schema(json_schemas: dict[str, dict[str, Any]]) -> Callable[[Any, str, str | None], None]:
    """Validate an instance against a standalone JSON schema file (and optional $defs key)."""

    def _validate(instance: Any, schema_file: str, def_name: str | None = None) -> None:
        root_schema = json_schemas[schema_file]
        if def_name:
            target_schema = {
                "$schema": root_schema["$schema"],
                "$defs": root_schema.get("$defs", {}),
                **root_schema["$defs"][def_name],
            }
        else:
            target_schema = root_schema
        jsonschema.validate(
            instance=instance,
            schema=target_schema,
            cls=jsonschema.Draft202012Validator,
            format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER,
        )

    return _validate


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("BASE_URL", "http://host.docker.internal:8000").rstrip("/")


@pytest.fixture(scope="session")
def http(base_url: str) -> httpx.Client:
    with httpx.Client(base_url=base_url, timeout=15.0) as client:
        yield client


@pytest.fixture(scope="session")
def run_suffix() -> str:
    return uuid.uuid4().hex[:8]


@pytest.fixture(scope="session")
def admin_tokens(http: httpx.Client) -> dict[str, Any]:
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@chronostore.lk")
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@Chrono2026")
    res = http.post(
        "/api/v1/auth/login",
        data={"username": admin_email, "password": admin_password},
    )
    assert res.status_code == 200, (
        f"Failed to login as seeded admin ({admin_email}): {res.status_code} {res.text}"
    )
    return res.json()


@pytest.fixture(scope="session")
def admin_headers(admin_tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_tokens['access_token']}"}


@pytest.fixture(scope="session")
def register_customer(
    http: httpx.Client,
) -> Callable[[str | None], tuple[dict[str, Any], dict[str, str], dict[str, Any]]]:
    """Registers and logs in a fresh customer account, returning (user, auth_headers, tokens)."""

    def _create(tag: str | None = None) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
        uid = uuid.uuid4().hex[:8]
        prefix = f"{tag}_{uid}" if tag else f"cust_{uid}"
        email = f"{prefix}@contract-test.lk"
        password = "ContractPass123!"
        reg_res = http.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": password,
                "full_name": f"Contract Customer {uid}",
                "phone": "+94771234567",
            },
        )
        assert reg_res.status_code == 201, reg_res.text
        user_data = reg_res.json()

        login_res = http.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert login_res.status_code == 200, login_res.text
        tokens = login_res.json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        return user_data, headers, tokens

    return _create


@pytest.fixture(scope="session")
def shared_catalog(
    http: httpx.Client, admin_headers: dict[str, str], run_suffix: str
) -> dict[str, Any]:
    """Creates a dedicated brand, category, and 2 products for contract tests."""
    brand_res = http.post(
        "/api/v1/brands",
        headers=admin_headers,
        json={
            "name": f"Contract Brand {run_suffix}",
            "slug": f"contract-brand-{run_suffix}",
            "description": "Brand created by automated contract test suite",
            "website_url": "https://chronostore.lk",
            "is_active": True,
        },
    )
    assert brand_res.status_code == 201, brand_res.text
    brand = brand_res.json()

    cat_res = http.post(
        "/api/v1/categories",
        headers=admin_headers,
        json={
            "name": f"Contract Category {run_suffix}",
            "slug": f"contract-cat-{run_suffix}",
            "description": "Category created by automated contract test suite",
            "is_active": True,
        },
    )
    assert cat_res.status_code == 201, cat_res.text
    category = cat_res.json()

    # Product 1: Under 50,000 LKR (triggers 500.00 LKR shipping fee when bought alone)
    p1_res = http.post(
        "/api/v1/products",
        headers=admin_headers,
        json={
            "sku": f"CT-QUARTZ-{run_suffix.upper()}",
            "name": f"Contract Quartz Watch {run_suffix}",
            "model": f"CQ-{run_suffix}",
            "description": "Precision quartz wristwatch below free shipping threshold.",
            "brand_id": brand["id"],
            "category_id": category["id"],
            "movement_type": "quartz",
            "case_material": "Stainless Steel",
            "strap_material": "Leather",
            "water_resistance": "50m",
            "dial_color": "Silver",
            "image_urls": ["https://cdn.chronostore.lk/ct-quartz.jpg"],
            "price_lkr": "24500.00",
            "status": "published",
            "low_stock_threshold": 5,
            "initial_stock": 30,
        },
    )
    assert p1_res.status_code == 201, p1_res.text
    budget_watch = p1_res.json()

    # Product 2: Over 50,000 LKR (qualifies for 0.00 LKR free shipping)
    p2_res = http.post(
        "/api/v1/products",
        headers=admin_headers,
        json={
            "sku": f"CT-AUTO-{run_suffix.upper()}",
            "name": f"Contract Automatic Diver {run_suffix}",
            "model": f"CA-{run_suffix}",
            "description": "Automatic mechanical diver wristwatch above free shipping threshold.",
            "brand_id": brand["id"],
            "category_id": category["id"],
            "movement_type": "automatic",
            "case_material": "Titanium",
            "strap_material": "Rubber",
            "water_resistance": "200m",
            "dial_color": "Deep Blue",
            "image_urls": ["https://cdn.chronostore.lk/ct-auto.jpg"],
            "price_lkr": "125000.00",
            "status": "published",
            "low_stock_threshold": 5,
            "initial_stock": 30,
        },
    )
    assert p2_res.status_code == 201, p2_res.text
    luxury_watch = p2_res.json()

    return {
        "brand": brand,
        "category": category,
        "budget_watch": budget_watch,
        "luxury_watch": luxury_watch,
    }

