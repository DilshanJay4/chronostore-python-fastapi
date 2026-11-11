"""Schemas for shipments and order returns."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.domain.enums import (
    InspectionOutcome,
    RefundMethod,
    ReturnReason,
    ReturnStatus,
    ShipmentStatus,
)
from app.schemas.common import APIModel, MoneyAmount, RequestModel


class ShipmentCreateRequest(RequestModel):
    tracking_number: str = Field(min_length=3, max_length=64)
    carrier: str = Field(default="Certis Lanka", min_length=2, max_length=100)
    notes: str | None = Field(default=None, max_length=255)


class ShipmentStatusUpdateRequest(RequestModel):
    status: ShipmentStatus
    notes: str | None = Field(default=None, max_length=255)


class ShipmentStatusHistoryResponse(APIModel):
    from_status: ShipmentStatus | None
    to_status: ShipmentStatus
    notes: str | None
    created_at: datetime


class ShipmentResponse(APIModel):
    id: uuid.UUID
    order_id: uuid.UUID
    tracking_number: str
    carrier: str
    status: ShipmentStatus
    dispatched_at: datetime | None
    delivered_at: datetime | None
    notes: str | None
    status_history: list[ShipmentStatusHistoryResponse]
    created_at: datetime
    updated_at: datetime


class ReturnItemRequest(RequestModel):
    order_item_id: uuid.UUID
    quantity: int = Field(ge=1)


class ReturnRequestCreate(RequestModel):
    reason: ReturnReason
    customer_notes: str = Field(min_length=5)
    items: list[ReturnItemRequest] = Field(min_length=1)


class ReturnReviewRequest(RequestModel):
    approved: bool
    admin_notes: str | None = Field(default=None, max_length=500)


class ReturnInspectRequest(RequestModel):
    outcome: InspectionOutcome
    notes: str | None = Field(default=None, max_length=500)
    restock_resellable: bool = True


class ReturnRefundRequest(RequestModel):
    refund_amount_lkr: Decimal = Field(gt=0, decimal_places=2)
    refund_method: RefundMethod = RefundMethod.BANK_TRANSFER
    refund_reference: str = Field(min_length=3, max_length=100)


class ReturnItemResponse(APIModel):
    id: uuid.UUID
    order_item_id: uuid.UUID
    quantity: int


class ReturnResponse(APIModel):
    id: uuid.UUID
    order_id: uuid.UUID
    status: ReturnStatus
    reason: ReturnReason
    customer_notes: str
    admin_notes: str | None
    inspection_outcome: InspectionOutcome | None
    inspection_notes: str | None
    inspected_at: datetime | None
    restocked: bool
    restocked_at: datetime | None
    refund_amount_lkr: MoneyAmount | None
    refund_method: RefundMethod | None
    refund_reference: str | None
    refunded_at: datetime | None
    items: list[ReturnItemResponse]
    created_at: datetime
    updated_at: datetime
