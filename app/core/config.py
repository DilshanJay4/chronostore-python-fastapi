"""Typed, validated application configuration loaded from the environment and `.env`."""

from decimal import Decimal
from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

MIN_PRODUCTION_SECRET_LENGTH = 32
# Placeholder values that must never be accepted outside development/testing.
INSECURE_SECRET_MARKERS = ("change-me", "changeme", "dev-secret", "secret", "example")


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application -----------------------------------------------------------------------
    environment: Environment = Environment.DEVELOPMENT
    app_name: str = "ChronoStore API"
    api_version: str = "1.0.0"
    api_v1_prefix: str = "/api/v1"
    docs_enabled: bool = True
    business_timezone: str = Field(
        default="Asia/Colombo",
        description="IANA timezone used to interpret calendar dates in reports.",
    )

    # --- Logging ---------------------------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True
    log_sql: bool = False

    # --- Database --------------------------------------------------------------------------
    database_url: SecretStr = Field(
        description="SQLAlchemy URL, e.g. postgresql+psycopg://user:pass@host:5432/db",
    )
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_max_overflow: int = Field(default=10, ge=0, le=100)
    db_pool_timeout_seconds: int = Field(default=10, ge=1, le=120)
    db_pool_recycle_seconds: int = Field(default=1800, ge=60)
    db_statement_timeout_ms: int = Field(default=15000, ge=100)

    # --- Security / JWT --------------------------------------------------------------------
    jwt_secret_key: SecretStr
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "chronostore-api"
    jwt_audience: str = "chronostore-clients"
    access_token_expire_minutes: int = Field(default=15, ge=1, le=120)
    refresh_token_expire_days: int = Field(default=14, ge=1, le=90)

    auth_rate_limit_attempts: int = Field(default=10, ge=1)
    auth_rate_limit_window_seconds: int = Field(default=60, ge=1)

    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    max_request_body_bytes: int = Field(default=1_048_576, ge=1024)

    # --- Commerce rules --------------------------------------------------------------------
    currency: str = "LKR"
    shipping_flat_fee_lkr: Decimal = Field(default=Decimal("500.00"), ge=0)
    free_shipping_threshold_lkr: Decimal = Field(default=Decimal("50000.00"), ge=0)
    max_cart_item_quantity: int = Field(default=10, ge=1, le=100)
    max_cart_lines: int = Field(default=20, ge=1, le=100)
    max_addresses_per_user: int = Field(default=10, ge=1, le=50)
    order_confirmation_ttl_hours: int = Field(default=72, ge=1)
    return_window_days: int = Field(default=14, ge=1, le=365)
    idempotency_key_ttl_hours: int = Field(default=24, ge=1)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("log_level must be a standard logging level")
        return level

    @field_validator("jwt_algorithm")
    @classmethod
    def _restrict_algorithm(cls, value: str) -> str:
        # Only symmetric HMAC algorithms are supported by the current key configuration.
        if value not in {"HS256", "HS384", "HS512"}:
            raise ValueError("jwt_algorithm must be one of HS256, HS384, HS512")
        return value

    @field_validator("currency")
    @classmethod
    def _only_lkr(cls, value: str) -> str:
        if value != "LKR":
            raise ValueError("ChronoStore currently trades exclusively in LKR")
        return value

    @model_validator(mode="after")
    def _validate_production(self) -> Self:
        if self.environment is not Environment.PRODUCTION:
            return self
        secret = self.jwt_secret_key.get_secret_value()
        if len(secret) < MIN_PRODUCTION_SECRET_LENGTH or any(
            marker in secret.lower() for marker in INSECURE_SECRET_MARKERS
        ):
            raise ValueError(
                "JWT_SECRET_KEY must be a strong random value (>= 32 chars) in production"
            )
        if "*" in self.cors_origins:
            raise ValueError("Wildcard CORS origins are not permitted in production")
        if not self.log_json:
            raise ValueError("LOG_JSON must be enabled in production")
        if self.log_level == "DEBUG":
            raise ValueError("DEBUG logging must not be enabled in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment
