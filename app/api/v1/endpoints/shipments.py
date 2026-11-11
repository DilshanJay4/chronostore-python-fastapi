"""Endpoints for shipments and return workflows."""

import uuid

from fastapi import APIRouter, Depends, status
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
from app.dependencies.auth import get_current_user, require_admin
from app.models.entities import User
from app.schemas.fulfillment import (
    ReturnInspectRequest,
    ReturnRefundRequest,
    ReturnRequestCreate,
    ReturnResponse,
    ReturnReviewRequest,
    ShipmentCreateRequest,
    ShipmentResponse,
    ShipmentStatusUpdateRequest,
)
from app.services.fulfillment import FulfillmentService

shipments_router = APIRouter(prefix="/orders/{order_id}/shipments", tags=["Shipments"])
admin_shipments_router = APIRouter(prefix="/admin", tags=["Admin: Shipments"])
returns_router = APIRouter(prefix="/orders/{order_id}/returns", tags=["Returns"])
direct_returns_router = APIRouter(prefix="/returns", tags=["Returns"])
admin_returns_router = APIRouter(prefix="/admin/returns", tags=["Admin: Returns"])


@shipments_router.get(
    "",
    response_model=list[ShipmentResponse],
    summary="List shipments and tracking for an order",
    responses=AUTH_RESPONSES,
)
def get_order_shipments(
    order_id: uuid.UUID,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[ShipmentResponse]:
    service = FulfillmentService(session, settings)
    return service.get_order_shipments(order_id)


@admin_shipments_router.post(
    "/orders/{order_id}/shipments",
    response_model=ShipmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create shipment for order (Admin only)",
    responses=responses(AUTH_RESPONSES, CONFLICT_RESPONSE, VALIDATION_RESPONSE),
)
def create_shipment(
    order_id: uuid.UUID,
    data: ShipmentCreateRequest,
    current_admin: User = Depends(require_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ShipmentResponse:
    service = FulfillmentService(session, settings)
    return service.create_shipment(order_id, data, current_admin)


@admin_shipments_router.patch(
    "/shipments/{shipment_id}/status",
    response_model=ShipmentResponse,
    summary="Update shipment status and tracking events (Admin only)",
    responses=responses(AUTH_RESPONSES, NOT_FOUND_RESPONSE, CONFLICT_RESPONSE),
)
def update_shipment_status(
    shipment_id: uuid.UUID,
    data: ShipmentStatusUpdateRequest,
    current_admin: User = Depends(require_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ShipmentResponse:
    service = FulfillmentService(session, settings)
    return service.update_shipment_status(shipment_id, data, current_admin)


@returns_router.post(
    "",
    response_model=ReturnResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request a return for an order",
    responses=responses(AUTH_RESPONSES, VALIDATION_RESPONSE),
)
def request_return(
    order_id: uuid.UUID,
    data: ReturnRequestCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ReturnResponse:
    service = FulfillmentService(session, settings)
    return service.request_return(order_id, current_user, data)


@direct_returns_router.get(
    "/{return_id}",
    response_model=ReturnResponse,
    summary="Get return request details",
    responses=responses(AUTH_RESPONSES, NOT_FOUND_RESPONSE),
)
def get_return(
    return_id: uuid.UUID,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ReturnResponse:
    service = FulfillmentService(session, settings)
    return service.get_return_by_id(return_id)


@admin_returns_router.post(
    "/{return_id}/review",
    response_model=ReturnResponse,
    summary="Approve or reject a customer return request (Admin only)",
    responses=responses(AUTH_RESPONSES, NOT_FOUND_RESPONSE, CONFLICT_RESPONSE),
)
def review_return(
    return_id: uuid.UUID,
    data: ReturnReviewRequest,
    current_admin: User = Depends(require_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ReturnResponse:
    service = FulfillmentService(session, settings)
    return service.review_return(return_id, data, current_admin)


@admin_returns_router.post(
    "/{return_id}/receive",
    response_model=ReturnResponse,
    summary="Confirm physical receipt of returned package (Admin only)",
    responses=responses(AUTH_RESPONSES, NOT_FOUND_RESPONSE, CONFLICT_RESPONSE),
)
def receive_return(
    return_id: uuid.UUID,
    current_admin: User = Depends(require_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ReturnResponse:
    service = FulfillmentService(session, settings)
    return service.receive_return(return_id, current_admin)


@admin_returns_router.post(
    "/{return_id}/inspect",
    response_model=ReturnResponse,
    summary="Record product inspection results and trigger restocking if resellable (Admin only)",
    responses=responses(AUTH_RESPONSES, NOT_FOUND_RESPONSE, CONFLICT_RESPONSE),
)
def inspect_return(
    return_id: uuid.UUID,
    data: ReturnInspectRequest,
    current_admin: User = Depends(require_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ReturnResponse:
    service = FulfillmentService(session, settings)
    return service.inspect_return(return_id, data, current_admin)


@admin_returns_router.post(
    "/{return_id}/refund",
    response_model=ReturnResponse,
    summary="Record offline bank transfer / cash refund for returned items (Admin only)",
    responses=responses(AUTH_RESPONSES, NOT_FOUND_RESPONSE, CONFLICT_RESPONSE),
)
def record_return_refund(
    return_id: uuid.UUID,
    data: ReturnRefundRequest,
    current_admin: User = Depends(require_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ReturnResponse:
    service = FulfillmentService(session, settings)
    return service.record_refund(return_id, data, current_admin)
