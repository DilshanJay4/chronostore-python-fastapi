"""Schemas for cart and cart items."""

import uuid

from pydantic import Field

from app.schemas.common import APIModel, Money, MoneyAmount, RequestModel


class CartItemAddRequest(RequestModel):
    product_id: uuid.UUID
    quantity: int = Field(default=1, ge=1, le=10)


class CartItemUpdateRequest(RequestModel):
    quantity: int = Field(ge=1, le=10)


class CartItemResponse(APIModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_sku: str
    product_name: str
    brand_name: str
    unit_price_lkr: MoneyAmount
    quantity: int
    line_total_lkr: MoneyAmount
    is_available: bool
    stock_warning: str | None = None


class CartResponse(APIModel):
    id: uuid.UUID
    items: list[CartItemResponse]
    subtotal: Money
    shipping_fee: Money
    total: Money
    currency: str = "LKR"
    item_count: int
    has_unavailable_items: bool
