"""Endpoints for managing the customer's shopping cart."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.openapi import AUTH_RESPONSES, NOT_FOUND_RESPONSE, VALIDATION_RESPONSE, responses
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.entities import User
from app.schemas.cart import (
    CartItemAddRequest,
    CartItemUpdateRequest,
    CartResponse,
)
from app.services.cart import CartService

router = APIRouter(prefix="/cart", tags=["Cart"])


@router.get("", response_model=CartResponse, summary="Get current customer's shopping cart")
def get_cart(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CartResponse:
    service = CartService(session, settings)
    return service.get_cart_response(current_user.id)


@router.post(
    "/items",
    response_model=CartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add an item to the shopping cart",
    responses=responses(AUTH_RESPONSES, NOT_FOUND_RESPONSE, VALIDATION_RESPONSE),
)
def add_item_to_cart(
    data: CartItemAddRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CartResponse:
    service = CartService(session, settings)
    return service.add_item(current_user.id, data)


@router.patch(
    "/items/{item_id}",
    response_model=CartResponse,
    summary="Update quantity of an item in the shopping cart",
    responses=responses(AUTH_RESPONSES, NOT_FOUND_RESPONSE, VALIDATION_RESPONSE),
)
def update_cart_item(
    item_id: uuid.UUID,
    data: CartItemUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CartResponse:
    service = CartService(session, settings)
    return service.update_item_quantity(current_user.id, item_id, data)


@router.delete(
    "/items/{item_id}",
    response_model=CartResponse,
    summary="Remove an item from the shopping cart",
    responses=responses(AUTH_RESPONSES, NOT_FOUND_RESPONSE),
)
def remove_cart_item(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CartResponse:
    service = CartService(session, settings)
    return service.remove_item(current_user.id, item_id)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear all items from the shopping cart",
    responses=AUTH_RESPONSES,
)
def clear_cart(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    service = CartService(session, settings)
    service.clear_cart(current_user.id)
