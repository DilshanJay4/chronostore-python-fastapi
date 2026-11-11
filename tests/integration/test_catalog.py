from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ConflictError
from app.domain.enums import ProductStatus, StockStatus, WatchMovement
from app.schemas.catalog import (
    BrandCreate,
    CategoryCreate,
    ProductCreate,
    ProductFilterParams,
)
from app.services.catalog import CatalogService

pytestmark = pytest.mark.db


def test_catalog_lifecycle_and_filtering(db_session: Session) -> None:
    settings = get_settings()
    service = CatalogService(db_session, settings)

    # 1. Brands
    seiko = service.create_brand(
        BrandCreate(name="Seiko", slug="seiko", description="Japanese precision")
    )
    tissot = service.create_brand(
        BrandCreate(name="Tissot", slug="tissot", description="Swiss tradition")
    )
    with pytest.raises(ConflictError):
        service.create_brand(BrandCreate(name="Seiko", slug="seiko-2"))

    # 2. Categories
    diver = service.create_category(CategoryCreate(name="Diver", slug="diver"))
    dress = service.create_category(CategoryCreate(name="Dress", slug="dress"))

    # 3. Products
    p1_entity = service.create_product(
        ProductCreate(
            sku="SKX007K",
            name="Seiko SKX007 Diver",
            model="SKX007",
            description="Legendary 200m ISO diver automatic watch.",
            brand_id=seiko.id,
            category_id=diver.id,
            movement_type=WatchMovement.AUTOMATIC,
            case_material="Stainless Steel",
            strap_material="Rubber",
            water_resistance="200m",
            dial_color="Black",
            price_lkr=Decimal("125000.00"),
            status=ProductStatus.PUBLISHED,
            initial_stock=10,
            low_stock_threshold=3,
        )
    )
    p1 = service.to_response(p1_entity, is_admin=True)
    assert p1.stock_status == StockStatus.IN_STOCK
    assert p1.available_stock == 10

    p2_entity = service.create_product(
        ProductCreate(
            sku="PRX-AUTO",
            name="Tissot PRX Powermatic 80",
            model="PRX",
            description="Integrated bracelet sports watch with 80hr power reserve.",
            brand_id=tissot.id,
            category_id=dress.id,
            movement_type=WatchMovement.AUTOMATIC,
            case_material="Stainless Steel",
            strap_material="Stainless Steel",
            water_resistance="100m",
            dial_color="Blue",
            price_lkr=Decimal("245000.00"),
            status=ProductStatus.PUBLISHED,
            initial_stock=2,
            low_stock_threshold=5,
        )
    )
    p2 = service.to_response(p2_entity, is_admin=True)
    assert p2.stock_status == StockStatus.LOW_STOCK

    # 4. Filter by brand
    page = service.list_products(ProductFilterParams(brand_id=seiko.id))
    assert page.total == 1
    assert page.items[0].sku == "SKX007K"

    # 5. Filter by price range
    page_price = service.list_products(ProductFilterParams(min_price=Decimal("200000.00")))
    assert page_price.total == 1
    assert page_price.items[0].sku == "PRX-AUTO"

    # 6. Search
    page_search = service.list_products(ProductFilterParams(search="legendary"))
    assert page_search.total == 1
    assert page_search.items[0].name == "Seiko SKX007 Diver"
