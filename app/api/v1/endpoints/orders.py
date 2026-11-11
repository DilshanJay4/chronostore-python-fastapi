"""Endpoints for checkout and customer order operations."""

import uuid

from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.orm import Session

from app.api.openapi import (
    AUTH_RESPONSES,
    CONFLICT_RESPONSE,
    NOT_FOUND_RESPONSE,
    VALIDATION_RESPONSE,
    responses,
)
from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_admin
from app.domain.enums import UserRole
from app.models.entities import User
from app.schemas.orders import (
    CheckoutRequest,
    OrderCancelRequest,
    OrderResponse,
    PaymentCollectRequest,
    PaymentResponse,
)
from app.services.orders import OrderService

checkout_router = APIRouter(prefix="/checkout", tags=["Checkout"])
orders_router = APIRouter(prefix="/orders", tags=["Orders"])
admin_orders_router = APIRouter(prefix="/admin/orders", tags=["Admin: Orders"])


@checkout_router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Checkout from customer cart with idempotency support",
    responses=responses(AUTH_RESPONSES, NOT_FOUND_RESPONSE, CONFLICT_RESPONSE, VALIDATION_RESPONSE),
)
async def checkout(
    request: Request,
    response: Response,
    data: CheckoutRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> OrderResponse:
    body_raw = await request.body()
    service = OrderService(session, settings)
    order_resp, replayed = service.checkout(
        user_id=current_user.id,
        data=data,
        idempotency_key=idempotency_key,
        request_body_raw=body_raw,
    )
    if replayed:
        response.headers["Idempotent-Replayed"] = "true"
        response.status_code = status.HTTP_200_OK
    return order_resp


@orders_router.get("", response_model=list[OrderResponse], summary="List customer's orders")
def list_my_orders(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[OrderResponse]:
    service = OrderService(session, settings)
    return service.list_orders(user_id=current_user.id, is_admin=False)


@orders_router.get(
    "/{order_id}",
    response_model=OrderResponse,
    summary="Get customer order details",
    responses=responses(AUTH_RESPONSES, NOT_FOUND_RESPONSE),
)
def get_order(
    order_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> OrderResponse:
    service = OrderService(session, settings)
    is_admin = current_user.role == UserRole.ADMIN
    return service.get_order_by_id(order_id, user_id=current_user.id, is_admin=is_admin)


@orders_router.post(
    "/{order_id}/cancel",
    response_model=OrderResponse,
    summary="Cancel order before shipment",
    responses=responses(AUTH_RESPONSES, NOT_FOUND_RESPONSE, CONFLICT_RESPONSE, VALIDATION_RESPONSE),
)
def cancel_my_order(
    order_id: uuid.UUID,
    data: OrderCancelRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> OrderResponse:
    service = OrderService(session, settings)
    is_admin = current_user.role == UserRole.ADMIN
    return service.cancel_order(order_id, user=current_user, data=data, is_admin=is_admin)


@orders_router.get(
    "/{order_id}/payment",
    response_model=PaymentResponse,
    summary="Get order payment status",
    responses=responses(AUTH_RESPONSES, NOT_FOUND_RESPONSE),
)
def get_order_payment(
    order_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PaymentResponse:
    service = OrderService(session, settings)
    is_admin = current_user.role == UserRole.ADMIN
    order = service.get_order_by_id(order_id, user_id=current_user.id, is_admin=is_admin)
    if not order.payment:
        raise NotFoundError("Payment record not found.")
    return order.payment


@admin_orders_router.post(
    "/{order_id}/payment/collect",
    response_model=OrderResponse,
    summary="Record Cash on Delivery payment collection (Admin only)",
    responses=responses(AUTH_RESPONSES, NOT_FOUND_RESPONSE, CONFLICT_RESPONSE, VALIDATION_RESPONSE),
)
def record_cod_collection(
    order_id: uuid.UUID,
    data: PaymentCollectRequest,
    current_admin: User = Depends(require_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> OrderResponse:
    service = OrderService(session, settings)
    return service.record_cod_collection(order_id, current_admin, data)
