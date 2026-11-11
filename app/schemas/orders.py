"""Schemas for checkout, orders, order items, and COD payments."""

import uuid
from datetime import datetime

from pydantic import Field

from app.domain.enums import OrderStatus, PaymentMethod, PaymentStatus
from app.schemas.common import APIModel, MoneyAmount, RequestModel


class CheckoutRequest(RequestModel):
    shipping_address_id: uuid.UUID
    customer_notes: str | None = Field(default=None, max_length=500)


class OrderItemResponse(APIModel):
    id: uuid.UUID
    product_id: uuid.UUID | None
    product_sku: str
    product_name: str
    brand_name: str
    unit_price_lkr: MoneyAmount
    quantity: int
    line_total_lkr: MoneyAmount


class PaymentResponse(APIModel):
    id: uuid.UUID
    order_id: uuid.UUID
    method: PaymentMethod
    status: PaymentStatus
    amount_lkr: MoneyAmount
    currency: str
    collected_at: datetime | None
    collection_reference: str | None
    notes: str | None


class OrderResponse(APIModel):
    id: uuid.UUID
    order_number: str
    status: OrderStatus
    subtotal_lkr: MoneyAmount
    shipping_fee_lkr: MoneyAmount
    total_lkr: MoneyAmount
    currency: str
    shipping_address_snapshot: dict
    customer_notes: str | None
    cancellation_reason: str | None
    cancelled_at: datetime | None
    confirmed_at: datetime | None
    items: list[OrderItemResponse]
    payment: PaymentResponse | None = None
    created_at: datetime
    updated_at: datetime


class OrderCancelRequest(RequestModel):
    reason: str = Field(min_length=3, max_length=255)


class PaymentCollectRequest(RequestModel):
    collection_reference: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=255)
