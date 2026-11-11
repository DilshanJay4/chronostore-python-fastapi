"""Endpoints for watch brands."""

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
from app.schemas.catalog import BrandCreate, BrandResponse, BrandUpdate
from app.services.catalog import CatalogService

router = APIRouter(prefix="/brands", tags=["Brands"])


@router.get("", response_model=list[BrandResponse], summary="List watch brands")
def list_brands(
    include_inactive: bool = Query(default=False, description="Include inactive brands"),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[BrandResponse]:
    service = CatalogService(session, settings)
    return [BrandResponse.model_validate(b) for b in service.list_brands(include_inactive)]


@router.get(
    "/{brand_id}",
    response_model=BrandResponse,
    summary="Get brand details",
    responses=NOT_FOUND_RESPONSE,
)
def get_brand(
    brand_id: uuid.UUID,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BrandResponse:
    service = CatalogService(session, settings)
    return BrandResponse.model_validate(service.get_brand(brand_id))


@router.post(
    "",
    response_model=BrandResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new brand (Admin only)",
    responses=responses(AUTH_RESPONSES, CONFLICT_RESPONSE, VALIDATION_RESPONSE),
)
def create_brand(
    data: BrandCreate,
    _: User = Depends(require_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BrandResponse:
    service = CatalogService(session, settings)
    return BrandResponse.model_validate(service.create_brand(data))


@router.patch(
    "/{brand_id}",
    response_model=BrandResponse,
    summary="Update a brand (Admin only)",
    responses=responses(AUTH_RESPONSES, NOT_FOUND_RESPONSE, CONFLICT_RESPONSE, VALIDATION_RESPONSE),
)
def update_brand(
    brand_id: uuid.UUID,
    data: BrandUpdate,
    _: User = Depends(require_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BrandResponse:
    service = CatalogService(session, settings)
    return BrandResponse.model_validate(service.update_brand(brand_id, data))
