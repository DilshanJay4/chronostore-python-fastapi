import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.db


def test_openapi_json_schema(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    assert schema["info"]["title"] == "ChronoStore API"
    assert schema["info"]["version"] == "1.0.0"
    assert "paths" in schema

    # Verify key routes are documented
    paths = schema["paths"]
    assert "/api/v1/auth/register" in paths
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/products" in paths
    assert "/api/v1/cart" in paths
    assert "/api/v1/checkout" in paths
    assert "/api/v1/orders" in paths
    assert "/api/v1/admin/inventory/adjustments" in paths
    assert "/api/v1/admin/reports/sales" in paths
    assert "/health/live" in paths
    assert "/health/ready" in paths

    # Verify OAuth2 bearer security scheme definition
    components = schema.get("components", {})
    security_schemes = components.get("securitySchemes", {})
    assert "OAuth2PasswordBearer" in security_schemes or "OAuth2Password" in str(security_schemes)


def test_swagger_and_redoc_ui(client: TestClient) -> None:
    res_docs = client.get("/docs")
    assert res_docs.status_code == 200
    assert "swagger-ui" in res_docs.text.lower()

    res_redoc = client.get("/redoc")
    assert res_redoc.status_code == 200
    assert "redoc" in res_redoc.text.lower()
