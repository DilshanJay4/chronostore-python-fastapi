"""Endpoints for wristwatch products."""

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
from app.domain.enums import ProductStatus, UserRole, WatchMovement
from app.models.entities import User
from app.schemas.catalog import (
    ProductCreate,
    ProductFilterParams,
    ProductResponse,
    ProductUpdate,
)
from app.schemas.common import Page
from app.services.catalog import CatalogService

router = APIRouter(prefix="/products", tags=["Products"])


def _check_admin(payload: dict | None) -> bool:
    return bool(payload and payload.get("role") == UserRole.ADMIN.value)


@router.get("", response_model=Page[ProductResponse], summary="List and filter wristwatch products")
def list_products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, description="Search term across name, SKU, model"),
    brand_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    movement_type: WatchMovement | None = None,
    min_price: float | None = Query(default=None, ge=0),
    max_price: float | None = Query(default=None, ge=0),
    status: ProductStatus | None = None,
    sort_by: str = Query(
        default="created_at",
        pattern=r"^(created_at|price_asc|price_desc|name_asc|name_desc)$",
    ),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Page[ProductResponse]:
    params = ProductFilterParams(
        page=page,
        page_size=page_size,
        search=search,
        brand_id=brand_id,
        category_id=category_id,
        movement_type=movement_type,
        min_price=min_price,  # type: ignore[arg-type]
        max_price=max_price,  # type: ignore[arg-type]
        status=status,
        sort_by=sort_by,
    )
    service = CatalogService(session, settings)
    return service.list_products(params, is_admin=False)


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Get wristwatch product details",
    responses=NOT_FOUND_RESPONSE,
)
def get_product(
    product_id: uuid.UUID,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProductResponse:
    service = CatalogService(session, settings)
    product = service.get_product_by_id(product_id, is_admin=False)
    return service.to_response(product, is_admin=False)


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new wristwatch product (Admin only)",
    responses=responses(AUTH_RESPONSES, CONFLICT_RESPONSE, VALIDATION_RESPONSE),
)
def create_product(
    data: ProductCreate,
    current_admin: User = Depends(require_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProductResponse:
    service = CatalogService(session, settings)
    product = service.create_product(data, actor=current_admin)
    return service.to_response(product, is_admin=True)


@router.patch(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Update a wristwatch product (Admin only)",
    responses=responses(AUTH_RESPONSES, NOT_FOUND_RESPONSE, CONFLICT_RESPONSE, VALIDATION_RESPONSE),
)
def update_product(
    product_id: uuid.UUID,
    data: ProductUpdate,
    _: User = Depends(require_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProductResponse:
    service = CatalogService(session, settings)
    product = service.update_product(product_id, data)
    return service.to_response(product, is_admin=True)
