"""Pydantic schemas for brands, categories, and wristwatch products."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import Field

from app.domain.enums import ProductStatus, StockStatus, WatchMovement
from app.schemas.common import APIModel, MoneyAmount, PageParams, RequestModel


class BrandCreate(RequestModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str | None = None
    website_url: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class BrandUpdate(RequestModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(
        default=None, min_length=1, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    description: str | None = None
    website_url: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class BrandResponse(APIModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    website_url: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CategoryCreate(RequestModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str | None = None
    is_active: bool = True


class CategoryUpdate(RequestModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(
        default=None, min_length=1, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    description: str | None = None
    is_active: bool | None = None


class CategoryResponse(APIModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProductCreate(RequestModel):
    sku: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9\-_]+$")
    name: str = Field(min_length=2, max_length=200)
    model: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=10)
    brand_id: uuid.UUID
    category_id: uuid.UUID
    movement_type: WatchMovement
    case_material: str = Field(min_length=2, max_length=80)
    strap_material: str = Field(min_length=2, max_length=80)
    water_resistance: str = Field(min_length=2, max_length=50)
    dial_color: str = Field(min_length=2, max_length=50)
    image_urls: list[str] = Field(default_factory=list)
    price_lkr: Decimal = Field(gt=0, decimal_places=2)
    status: ProductStatus = ProductStatus.DRAFT
    low_stock_threshold: int = Field(default=5, ge=0)
    initial_stock: int = Field(default=0, ge=0)


class ProductUpdate(RequestModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    model: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, min_length=10)
    brand_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    movement_type: WatchMovement | None = None
    case_material: str | None = Field(default=None, min_length=2, max_length=80)
    strap_material: str | None = Field(default=None, min_length=2, max_length=80)
    water_resistance: str | None = Field(default=None, min_length=2, max_length=50)
    dial_color: str | None = Field(default=None, min_length=2, max_length=50)
    image_urls: list[str] | None = None
    price_lkr: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    status: ProductStatus | None = None
    low_stock_threshold: int | None = Field(default=None, ge=0)


class ProductResponse(APIModel):
    id: uuid.UUID
    sku: str
    name: str
    model: str
    description: str
    brand_id: uuid.UUID
    brand_name: str
    category_id: uuid.UUID
    category_name: str
    movement_type: WatchMovement
    case_material: str
    strap_material: str
    water_resistance: str
    dial_color: str
    image_urls: list[str]
    price_lkr: MoneyAmount
    currency: str = "LKR"
    status: ProductStatus
    stock_status: StockStatus
    available_stock: int | None = None  # Full count visible to admin or detail
    created_at: datetime
    updated_at: datetime


class ProductFilterParams(PageParams):
    search: str | None = None
    brand_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    movement_type: WatchMovement | None = None
    min_price: Decimal | None = Field(default=None, ge=0)
    max_price: Decimal | None = Field(default=None, ge=0)
    status: ProductStatus | None = None
    sort_by: Annotated[
        str,
        Field(
            default="created_at",
            pattern=r"^(created_at|price_asc|price_desc|name_asc|name_desc)$",
        ),
    ]
