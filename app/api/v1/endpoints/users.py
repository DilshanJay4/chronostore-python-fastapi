"""Endpoints for authenticated user profile and address book."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.openapi import AUTH_RESPONSES, NOT_FOUND_RESPONSE, VALIDATION_RESPONSE, responses
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.entities import User
from app.schemas.users import (
    AddressCreate,
    AddressResponse,
    AddressUpdate,
    UserProfileUpdate,
    UserResponse,
)
from app.services.users import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
    responses=AUTH_RESPONSES,
)
def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Update current user profile",
    responses=responses(AUTH_RESPONSES, VALIDATION_RESPONSE),
)
def update_me(
    data: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserResponse:
    service = UserService(session, settings)
    updated = service.update_profile(current_user, data)
    return UserResponse.model_validate(updated)


@router.get(
    "/me/addresses",
    response_model=list[AddressResponse],
    summary="List saved customer delivery addresses",
    responses=AUTH_RESPONSES,
)
def list_addresses(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[AddressResponse]:
    service = UserService(session, settings)
    addresses = service.get_addresses(current_user.id)
    return [AddressResponse.model_validate(a) for a in addresses]


@router.post(
    "/me/addresses",
    response_model=AddressResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new delivery address",
    responses=responses(AUTH_RESPONSES, VALIDATION_RESPONSE),
)
def add_address(
    data: AddressCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AddressResponse:
    service = UserService(session, settings)
    address = service.add_address(current_user.id, data)
    return AddressResponse.model_validate(address)


@router.patch(
    "/me/addresses/{address_id}",
    response_model=AddressResponse,
    summary="Update a saved address",
    responses=responses(AUTH_RESPONSES, NOT_FOUND_RESPONSE, VALIDATION_RESPONSE),
)
def update_address(
    address_id: uuid.UUID,
    data: AddressUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AddressResponse:
    service = UserService(session, settings)
    address = service.update_address(current_user.id, address_id, data)
    return AddressResponse.model_validate(address)


@router.delete(
    "/me/addresses/{address_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a saved address",
    responses=responses(AUTH_RESPONSES, NOT_FOUND_RESPONSE),
)
def delete_address(
    address_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    service = UserService(session, settings)
    service.delete_address(current_user.id, address_id)

