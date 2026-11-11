import pytest
from pydantic import ValidationError

from app.core.config import Environment, Settings

BASE = {"database_url": "postgresql+psycopg://u:p@localhost/db"}
STRONG_SECRET = "Zq8v1PpK3m0Rr7tY2uWx9aLs5dFg4hJk6nBc"


def test_cors_origins_are_parsed_from_comma_separated_string() -> None:
    settings = Settings(**BASE, jwt_secret_key="x" * 40, cors_origins="https://a.lk, https://b.lk")
    assert settings.cors_origins == ["https://a.lk", "https://b.lk"]


def test_production_rejects_weak_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(**BASE, environment=Environment.PRODUCTION, jwt_secret_key="change-me")


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValidationError, match="CORS"):
        Settings(
            **BASE,
            environment=Environment.PRODUCTION,
            jwt_secret_key=STRONG_SECRET,
            cors_origins="*",
        )


def test_production_accepts_strong_configuration() -> None:
    settings = Settings(
        **BASE,
        environment=Environment.PRODUCTION,
        jwt_secret_key=STRONG_SECRET,
        cors_origins="https://chronostore.lk",
    )
    assert settings.is_production


def test_rejects_non_lkr_currency_and_unsafe_algorithm() -> None:
    with pytest.raises(ValidationError):
        Settings(**BASE, jwt_secret_key="x" * 40, currency="USD")
    with pytest.raises(ValidationError):
        Settings(**BASE, jwt_secret_key="x" * 40, jwt_algorithm="none")


def test_secrets_are_not_exposed_in_repr() -> None:
    settings = Settings(**BASE, jwt_secret_key=STRONG_SECRET)
    assert STRONG_SECRET not in repr(settings)
    assert "u:p@" not in repr(settings)
