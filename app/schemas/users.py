"""Pydantic schemas for authentication and user management."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import EmailStr, Field

from app.domain.enums import UserRole
from app.schemas.common import APIModel, RequestModel


class UserRegisterRequest(RequestModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=150)
    phone: str | None = Field(default=None, max_length=30)


class LoginRequest(RequestModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(APIModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int
    refresh_token: str


class RefreshTokenRequest(RequestModel):
    refresh_token: str = Field(min_length=16)


class LogoutRequest(RequestModel):
    refresh_token: str = Field(min_length=16)


class UserResponse(APIModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    phone: str | None
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserProfileUpdate(RequestModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    phone: str | None = Field(default=None, max_length=30)


class AddressCreate(RequestModel):
    label: str = Field(default="Home", min_length=1, max_length=50)
    recipient_name: str = Field(min_length=2, max_length=150)
    phone: str = Field(min_length=5, max_length=30)
    street_line1: str = Field(min_length=3, max_length=255)
    street_line2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=2, max_length=100)
    postal_code: str = Field(min_length=3, max_length=20)
    province: str = Field(min_length=2, max_length=100)
    country_code: Annotated[str, Field(default="LK", min_length=2, max_length=2)]
    is_default: bool = False


class AddressUpdate(RequestModel):
    label: str | None = Field(default=None, min_length=1, max_length=50)
    recipient_name: str | None = Field(default=None, min_length=2, max_length=150)
    phone: str | None = Field(default=None, min_length=5, max_length=30)
    street_line1: str | None = Field(default=None, min_length=3, max_length=255)
    street_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, min_length=2, max_length=100)
    postal_code: str | None = Field(default=None, min_length=3, max_length=20)
    province: str | None = Field(default=None, min_length=2, max_length=100)
    is_default: bool | None = None


class AddressResponse(APIModel):
    id: uuid.UUID
    label: str
    recipient_name: str
    phone: str
    street_line1: str
    street_line2: str | None
    city: str
    postal_code: str
    province: str
    country_code: str
    is_default: bool
    created_at: datetime
    updated_at: datetime
