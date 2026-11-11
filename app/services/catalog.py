"""Catalog service for brands, categories and products."""

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql import Select

from app.core.config import Settings
from app.core.exceptions import ConflictError, NotFoundError
from app.domain.enums import (
    AdjustmentReason,
    InventoryMovementType,
    ProductStatus,
)
from app.domain.pricing import stock_status
from app.models.entities import Brand, Category, InventoryItem, InventoryMovement, Product, User
from app.schemas.catalog import (
    BrandCreate,
    BrandUpdate,
    CategoryCreate,
    CategoryUpdate,
    ProductCreate,
    ProductFilterParams,
    ProductResponse,
    ProductUpdate,
)
from app.schemas.common import Page


class CatalogService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    # --- Brands ---
    def list_brands(self, include_inactive: bool = False) -> list[Brand]:
        stmt = select(Brand)
        if not include_inactive:
            stmt = stmt.where(Brand.is_active == True)  # noqa: E712
        return list(self.session.execute(stmt.order_by(Brand.name)).scalars().all())

    def get_brand(self, brand_id: uuid.UUID) -> Brand:
        brand = self.session.execute(select(Brand).where(Brand.id == brand_id)).scalar_one_or_none()
        if not brand:
            raise NotFoundError("Brand not found.")
        return brand

    def create_brand(self, data: BrandCreate) -> Brand:
        if self.session.execute(
            select(Brand).where(or_(Brand.name == data.name, Brand.slug == data.slug))
        ).scalar_one_or_none():
            raise ConflictError("A brand with this name or slug already exists.")
        brand = Brand(**data.model_dump())
        self.session.add(brand)
        self.session.commit()
        self.session.refresh(brand)
        return brand

    def update_brand(self, brand_id: uuid.UUID, data: BrandUpdate) -> Brand:
        brand = self.get_brand(brand_id)
        updates = data.model_dump(exclude_unset=True)
        if "name" in updates or "slug" in updates:
            existing = self.session.execute(
                select(Brand).where(
                    Brand.id != brand_id,
                    or_(
                        Brand.name == updates.get("name", brand.name),
                        Brand.slug == updates.get("slug", brand.slug),
                    ),
                )
            ).scalar_one_or_none()
            if existing:
                raise ConflictError("Another brand with this name or slug already exists.")

        for k, v in updates.items():
            setattr(brand, k, v)
        self.session.commit()
        self.session.refresh(brand)
        return brand

    # --- Categories ---
    def list_categories(self, include_inactive: bool = False) -> list[Category]:
        stmt = select(Category)
        if not include_inactive:
            stmt = stmt.where(Category.is_active == True)  # noqa: E712
        return list(self.session.execute(stmt.order_by(Category.name)).scalars().all())

    def get_category(self, category_id: uuid.UUID) -> Category:
        category = self.session.execute(
            select(Category).where(Category.id == category_id)
        ).scalar_one_or_none()
        if not category:
            raise NotFoundError("Category not found.")
        return category

    def create_category(self, data: CategoryCreate) -> Category:
        if self.session.execute(
            select(Category).where(or_(Category.name == data.name, Category.slug == data.slug))
        ).scalar_one_or_none():
            raise ConflictError("A category with this name or slug already exists.")
        category = Category(**data.model_dump())
        self.session.add(category)
        self.session.commit()
        self.session.refresh(category)
        return category

    def update_category(self, category_id: uuid.UUID, data: CategoryUpdate) -> Category:
        category = self.get_category(category_id)
        updates = data.model_dump(exclude_unset=True)
        if "name" in updates or "slug" in updates:
            existing = self.session.execute(
                select(Category).where(
                    Category.id != category_id,
                    or_(
                        Category.name == updates.get("name", category.name),
                        Category.slug == updates.get("slug", category.slug),
                    ),
                )
            ).scalar_one_or_none()
            if existing:
                raise ConflictError("Another category with this name or slug already exists.")

        for k, v in updates.items():
            setattr(category, k, v)
        self.session.commit()
        self.session.refresh(category)
        return category

    # --- Products ---
    def create_product(self, data: ProductCreate, actor: User | None = None) -> Product:
        if self.session.execute(
            select(Product).where(Product.sku == data.sku)
        ).scalar_one_or_none():
            raise ConflictError(f"Product with SKU '{data.sku}' already exists.")

        self.get_brand(data.brand_id)
        self.get_category(data.category_id)

        product = Product(
            sku=data.sku,
            name=data.name,
            model=data.model,
            description=data.description,
            brand_id=data.brand_id,
            category_id=data.category_id,
            movement_type=data.movement_type,
            case_material=data.case_material,
            strap_material=data.strap_material,
            water_resistance=data.water_resistance,
            dial_color=data.dial_color,
            image_urls=data.image_urls,
            price_lkr=data.price_lkr,
            status=data.status,
            low_stock_threshold=data.low_stock_threshold,
        )
        self.session.add(product)
        self.session.flush()

        inventory = InventoryItem(
            product_id=product.id,
            on_hand=data.initial_stock,
            reserved=0,
        )
        self.session.add(inventory)
        self.session.flush()

        if data.initial_stock > 0:
            movement = InventoryMovement(
                product_id=product.id,
                movement_type=InventoryMovementType.ADJUSTMENT,
                quantity_delta=data.initial_stock,
                reserved_delta=0,
                on_hand_after=data.initial_stock,
                reserved_after=0,
                reason=AdjustmentReason.RESTOCK,
                notes="Initial stock intake on creation",
                actor_id=actor.id if actor else None,
            )
            self.session.add(movement)

        self.session.commit()
        return self.get_product_by_id(product.id, is_admin=True)

    def update_product(self, product_id: uuid.UUID, data: ProductUpdate) -> Product:
        product = self.session.execute(
            select(Product).where(Product.id == product_id)
        ).scalar_one_or_none()
        if not product:
            raise NotFoundError("Product not found.")

        updates = data.model_dump(exclude_unset=True)
        if "brand_id" in updates:
            self.get_brand(updates["brand_id"])
        if "category_id" in updates:
            self.get_category(updates["category_id"])

        for k, v in updates.items():
            setattr(product, k, v)

        self.session.commit()
        return self.get_product_by_id(product.id, is_admin=True)

    def get_product_by_id(self, product_id: uuid.UUID, is_admin: bool = False) -> Product:
        stmt = (
            select(Product)
            .options(
                joinedload(Product.brand),
                joinedload(Product.category),
                joinedload(Product.inventory_item),
            )
            .where(Product.id == product_id)
        )
        if not is_admin:
            stmt = stmt.where(Product.status == ProductStatus.PUBLISHED)

        product = self.session.execute(stmt).scalar_one_or_none()
        if not product:
            raise NotFoundError("Product not found.")
        return product

    def _apply_product_filters(
        self, stmt: Select, params: ProductFilterParams, is_admin: bool
    ) -> Select:
        if not is_admin:
            stmt = stmt.where(Product.status == ProductStatus.PUBLISHED)
        elif params.status:
            stmt = stmt.where(Product.status == params.status)

        if params.brand_id:
            stmt = stmt.where(Product.brand_id == params.brand_id)
        if params.category_id:
            stmt = stmt.where(Product.category_id == params.category_id)
        if params.movement_type:
            stmt = stmt.where(Product.movement_type == params.movement_type)
        if params.min_price is not None:
            stmt = stmt.where(Product.price_lkr >= params.min_price)
        if params.max_price is not None:
            stmt = stmt.where(Product.price_lkr <= params.max_price)

        if params.search:
            pattern = f"%{params.search.strip()}%"
            stmt = stmt.where(
                or_(
                    Product.name.ilike(pattern),
                    Product.model.ilike(pattern),
                    Product.sku.ilike(pattern),
                    Product.description.ilike(pattern),
                )
            )
        return stmt

    def _apply_product_sorting(self, stmt: Select, sort_by: str) -> Select:
        if sort_by == "price_asc":
            return stmt.order_by(Product.price_lkr.asc(), Product.created_at.desc())
        if sort_by == "price_desc":
            return stmt.order_by(Product.price_lkr.desc(), Product.created_at.desc())
        if sort_by == "name_asc":
            return stmt.order_by(Product.name.asc())
        if sort_by == "name_desc":
            return stmt.order_by(Product.name.desc())
        return stmt.order_by(Product.created_at.desc())

    def list_products(
        self, params: ProductFilterParams, is_admin: bool = False
    ) -> Page[ProductResponse]:
        stmt = select(Product).options(
            joinedload(Product.brand),
            joinedload(Product.category),
            joinedload(Product.inventory_item),
        )
        stmt = self._apply_product_filters(stmt, params, is_admin)
        stmt = self._apply_product_sorting(stmt, params.sort_by)

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.session.execute(count_stmt).scalar_one()

        # Paginate
        paginated_stmt = stmt.offset(params.offset).limit(params.page_size)
        items = list(self.session.execute(paginated_stmt).scalars().all())

        product_responses = [self.to_response(p, is_admin=is_admin) for p in items]
        return Page.build(
            items=product_responses,
            page=params.page,
            page_size=params.page_size,
            total=total,
        )

    def to_response(self, product: Product, is_admin: bool = False) -> ProductResponse:
        inv = product.inventory_item
        avail = inv.available if inv else 0
        status = stock_status(avail, product.low_stock_threshold)
        return ProductResponse(
            id=product.id,
            sku=product.sku,
            name=product.name,
            model=product.model,
            description=product.description,
            brand_id=product.brand_id,
            brand_name=product.brand.name,
            category_id=product.category_id,
            category_name=product.category.name,
            movement_type=product.movement_type,
            case_material=product.case_material,
            strap_material=product.strap_material,
            water_resistance=product.water_resistance,
            dial_color=product.dial_color,
            image_urls=product.image_urls,
            price_lkr=product.price_lkr,
            status=product.status,
            stock_status=status,
            available_stock=avail if is_admin else None,
            created_at=product.created_at,
            updated_at=product.updated_at,
        )
