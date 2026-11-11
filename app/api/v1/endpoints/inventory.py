"""Endpoints for administrator inventory controls."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.openapi import (
    AUTH_RESPONSES,
    CONFLICT_RESPONSE,
    NOT_FOUND_RESPONSE,
    VALIDATION_RESPONSE,
    responses,
)
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.dependencies.auth import require_admin
from app.models.entities import User
from app.schemas.inventory import (
    InventoryAdjustmentRequest,
    InventoryItemResponse,
    InventoryMovementResponse,
)
from app.services.inventory import InventoryService

router = APIRouter(prefix="/admin/inventory", tags=["Admin: Inventory"])


@router.get(
    "",
    response_model=list[InventoryItemResponse],
    summary="List inventory levels for all products (Admin only)",
    responses=AUTH_RESPONSES,
)
def list_inventory(
    _: User = Depends(require_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[InventoryItemResponse]:
    service = InventoryService(session, settings)
    return service.list_inventory()


@router.post(
    "/adjustments",
    response_model=InventoryItemResponse,
    summary="Adjust product stock with recorded reason (Admin only)",
    responses=responses(AUTH_RESPONSES, NOT_FOUND_RESPONSE, CONFLICT_RESPONSE, VALIDATION_RESPONSE),
)
def adjust_inventory(
    data: InventoryAdjustmentRequest,
    current_admin: User = Depends(require_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> InventoryItemResponse:
    service = InventoryService(session, settings)
    return service.adjust_stock(data, actor=current_admin)


@router.get(
    "/movements",
    response_model=list[InventoryMovementResponse],
    summary="Audit stock movement history (Admin only)",
    responses=AUTH_RESPONSES,
)
def list_movements(
    product_id: uuid.UUID | None = Query(default=None),
    _: User = Depends(require_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[InventoryMovementResponse]:
    service = InventoryService(session, settings)
    return service.list_movements(product_id=product_id)
