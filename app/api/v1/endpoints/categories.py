"""Endpoints for product categories."""

import uuid

from fastapi import APIRouter, Depends, Query, status
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
from app.schemas.catalog import CategoryCreate, CategoryResponse, CategoryUpdate
from app.services.catalog import CatalogService

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.get("", response_model=list[CategoryResponse], summary="List categories")
def list_categories(
    include_inactive: bool = Query(default=False, description="Include inactive categories"),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[CategoryResponse]:
    service = CatalogService(session, settings)
    return [CategoryResponse.model_validate(c) for c in service.list_categories(include_inactive)]


@router.get(
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Get category details",
    responses=NOT_FOUND_RESPONSE,
)
def get_category(
    category_id: uuid.UUID,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CategoryResponse:
    service = CatalogService(session, settings)
    return CategoryResponse.model_validate(service.get_category(category_id))


@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a category (Admin only)",
    responses=responses(AUTH_RESPONSES, CONFLICT_RESPONSE, VALIDATION_RESPONSE),
)
def create_category(
    data: CategoryCreate,
    _: User = Depends(require_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CategoryResponse:
    service = CatalogService(session, settings)
    return CategoryResponse.model_validate(service.create_category(data))


@router.patch(
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Update a category (Admin only)",
    responses=responses(AUTH_RESPONSES, NOT_FOUND_RESPONSE, CONFLICT_RESPONSE, VALIDATION_RESPONSE),
)
def update_category(
    category_id: uuid.UUID,
    data: CategoryUpdate,
    _: User = Depends(require_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CategoryResponse:
    service = CatalogService(session, settings)
    return CategoryResponse.model_validate(service.update_category(category_id, data))
