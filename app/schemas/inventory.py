"""Schemas for inventory management and stock movements."""

import uuid
from datetime import datetime

from pydantic import Field

from app.domain.enums import AdjustmentReason, InventoryMovementType, StockStatus
from app.schemas.common import APIModel, RequestModel


class InventoryAdjustmentRequest(RequestModel):
    product_id: uuid.UUID
    quantity_delta: int = Field(description="Positive to add stock, negative to subtract stock.")
    reason: AdjustmentReason
    notes: str | None = Field(default=None, max_length=255)


class InventoryItemResponse(APIModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_sku: str
    product_name: str
    brand_name: str
    on_hand: int
    reserved: int
    available: int
    low_stock_threshold: int
    stock_status: StockStatus
    updated_at: datetime


class InventoryMovementResponse(APIModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_sku: str
    product_name: str
    movement_type: InventoryMovementType
    quantity_delta: int
    reserved_delta: int
    on_hand_after: int
    reserved_after: int
    reason: AdjustmentReason | None
    notes: str | None
    reference_id: uuid.UUID | None
    actor_id: uuid.UUID | None
    created_at: datetime
