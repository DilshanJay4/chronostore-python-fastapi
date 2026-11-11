"""All persistence models for ChronoStore.

Foreign keys use CASCADE or RESTRICT explicitly; critical invariants (e.g. non-negative
inventory, valid totals) are backed by CHECK constraints in addition to application logic.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    Base,
    CreatedAtMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_column,
    money_column,
)
from app.domain.enums import (
    AdjustmentReason,
    InspectionOutcome,
    InventoryMovementType,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    ProductStatus,
    RefundMethod,
    ReturnReason,
    ReturnStatus,
    ShipmentStatus,
    UserRole,
    WatchMovement,
)

# SQLite in unit tests does not have JSONB; fallback to JSON representation if ever needed.
JSONType = JSONB().with_variant(Text(), "sqlite")


# =====================================================================================
# Users, Addresses, Refresh Tokens
# =====================================================================================


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    role: Mapped[UserRole] = enum_column(UserRole, default=UserRole.CUSTOMER, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    addresses: Mapped[list[Address]] = relationship(
        "Address", back_populates="user", cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
    cart: Mapped[Cart | None] = relationship(
        "Cart", back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    orders: Mapped[list[Order]] = relationship("Order", back_populates="user")


class Address(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "addresses"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(50), default="Home", nullable=False)
    recipient_name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    street_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    street_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    province: Mapped[str] = mapped_column(String(100), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), default="LK", nullable=False)
    is_default: Mapped[bool] = mapped_column(default=False, nullable=False)

    user: Mapped[User] = relationship("User", back_populates="addresses")


class RefreshToken(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Stored as SHA-256 hex digest so a database leak does not expose plaintext refresh tokens.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="refresh_tokens")


# =====================================================================================
# Catalog: Brands, Categories, Products
# =====================================================================================


class Brand(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "brands"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    products: Mapped[list[Product]] = relationship("Product", back_populates="brand")


class Category(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    products: Mapped[list[Product]] = relationship("Product", back_populates="category")


class Product(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    brand_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("brands.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    movement_type: Mapped[WatchMovement] = enum_column(WatchMovement, nullable=False)
    case_material: Mapped[str] = mapped_column(String(80), nullable=False)
    strap_material: Mapped[str] = mapped_column(String(80), nullable=False)
    water_resistance: Mapped[str] = mapped_column(String(50), nullable=False)
    dial_color: Mapped[str] = mapped_column(String(50), nullable=False)
    image_urls: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)

    price_lkr: Mapped[Decimal] = money_column(nullable=False)
    status: Mapped[ProductStatus] = enum_column(
        ProductStatus, default=ProductStatus.DRAFT, nullable=False, index=True
    )
    low_stock_threshold: Mapped[int] = mapped_column(default=5, nullable=False)

    brand: Mapped[Brand] = relationship("Brand", back_populates="products")
    category: Mapped[Category] = relationship("Category", back_populates="products")
    inventory_item: Mapped[InventoryItem | None] = relationship(
        "InventoryItem", back_populates="product", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        CheckConstraint("price_lkr >= 0", name="ck_product_price_non_negative"),
        CheckConstraint(
            "low_stock_threshold >= 0", name="ck_product_low_stock_threshold_non_negative"
        ),
        Index("ix_products_brand_status", "brand_id", "status"),
        Index("ix_products_category_status", "category_id", "status"),
        Index("ix_products_movement_status", "movement_type", "status"),
    )


# =====================================================================================
# Inventory
# =====================================================================================


class InventoryItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "inventory_items"

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    on_hand: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    product: Mapped[Product] = relationship("Product", back_populates="inventory_item")

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved

    __table_args__ = (
        CheckConstraint("on_hand >= 0", name="ck_inventory_on_hand_non_negative"),
        CheckConstraint("reserved >= 0", name="ck_inventory_reserved_non_negative"),
        CheckConstraint("on_hand >= reserved", name="ck_inventory_reserved_within_on_hand"),
    )


class InventoryMovement(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "inventory_movements"

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    movement_type: Mapped[InventoryMovementType] = enum_column(
        InventoryMovementType, nullable=False, index=True
    )
    quantity_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_delta: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    on_hand_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_after: Mapped[int] = mapped_column(Integer, nullable=False)

    reason: Mapped[AdjustmentReason | None] = enum_column(AdjustmentReason, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


# =====================================================================================
# Cart
# =====================================================================================


class Cart(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "carts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    user: Mapped[User] = relationship("User", back_populates="cart")
    items: Mapped[list[CartItem]] = relationship(
        "CartItem", back_populates="cart", cascade="all, delete-orphan"
    )


class CartItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "cart_items"

    cart_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("carts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    cart: Mapped[Cart] = relationship("Cart", back_populates="items")
    product: Mapped[Product] = relationship("Product")

    __table_args__ = (
        UniqueConstraint("cart_id", "product_id", name="uq_cart_product"),
        CheckConstraint("quantity > 0", name="ck_cart_item_quantity_positive"),
    )


# =====================================================================================
# Orders & COD Payments
# =====================================================================================


class Order(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "orders"

    order_number: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[OrderStatus] = enum_column(
        OrderStatus, default=OrderStatus.PLACED, nullable=False, index=True
    )

    subtotal_lkr: Mapped[Decimal] = money_column(nullable=False)
    shipping_fee_lkr: Mapped[Decimal] = money_column(nullable=False)
    total_lkr: Mapped[Decimal] = money_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="LKR", nullable=False)

    shipping_address_snapshot: Mapped[dict] = mapped_column(JSONType, nullable=False)
    customer_notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="orders")
    items: Mapped[list[OrderItem]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )
    payment: Mapped[Payment] = relationship(
        "Payment", back_populates="order", cascade="all, delete-orphan", uselist=False
    )
    shipments: Mapped[list[Shipment]] = relationship(
        "Shipment", back_populates="order", cascade="all, delete-orphan"
    )
    returns: Mapped[list[ReturnRequest]] = relationship("ReturnRequest", back_populates="order")

    __table_args__ = (
        CheckConstraint("subtotal_lkr >= 0", name="ck_order_subtotal_non_negative"),
        CheckConstraint("shipping_fee_lkr >= 0", name="ck_order_shipping_non_negative"),
        CheckConstraint("total_lkr >= 0", name="ck_order_total_non_negative"),
        CheckConstraint(
            "total_lkr = subtotal_lkr + shipping_fee_lkr", name="ck_order_total_equals_parts"
        ),
        Index("ix_orders_user_created", "user_id", "created_at"),
    )


class OrderItem(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "order_items"

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Immutable snapshots taken at checkout.
    product_sku: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    brand_name: Mapped[str] = mapped_column(String(100), nullable=False)
    unit_price_lkr: Mapped[Decimal] = money_column(nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total_lkr: Mapped[Decimal] = money_column(nullable=False)

    order: Mapped[Order] = relationship("Order", back_populates="items")
    product: Mapped[Product | None] = relationship("Product")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_item_quantity_positive"),
        CheckConstraint("unit_price_lkr >= 0", name="ck_order_item_unit_price_non_negative"),
        CheckConstraint(
            "line_total_lkr = unit_price_lkr * quantity", name="ck_order_item_line_total_math"
        ),
    )


class Payment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "payments"

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
        index=True,
    )
    method: Mapped[PaymentMethod] = enum_column(
        PaymentMethod, default=PaymentMethod.CASH_ON_DELIVERY, nullable=False
    )
    status: Mapped[PaymentStatus] = enum_column(
        PaymentStatus, default=PaymentStatus.PENDING, nullable=False, index=True
    )
    amount_lkr: Mapped[Decimal] = money_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="LKR", nullable=False)

    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    collection_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)

    order: Mapped[Order] = relationship("Order", back_populates="payment")
    collected_by: Mapped[User | None] = relationship("User")

    __table_args__ = (CheckConstraint("amount_lkr >= 0", name="ck_payment_amount_non_negative"),)


# =====================================================================================
# Idempotency
# =====================================================================================


class IdempotencyRecord(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "idempotency_records"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict] = mapped_column(JSONType, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_idempotency_user_key"),
    )


# =====================================================================================
# Fulfilment: Shipments & History
# =====================================================================================


class Shipment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "shipments"

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    tracking_number: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    carrier: Mapped[str] = mapped_column(String(100), default="Certis Lanka", nullable=False)
    status: Mapped[ShipmentStatus] = enum_column(
        ShipmentStatus, default=ShipmentStatus.PENDING, nullable=False, index=True
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)

    order: Mapped[Order] = relationship("Order", back_populates="shipments")
    status_history: Mapped[list[ShipmentStatusHistory]] = relationship(
        "ShipmentStatusHistory",
        back_populates="shipment",
        cascade="all, delete-orphan",
        order_by="ShipmentStatusHistory.created_at",
    )


class ShipmentStatusHistory(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "shipment_status_history"

    shipment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[ShipmentStatus | None] = enum_column(
        ShipmentStatus, constraint_name="shipment_status_from", nullable=True
    )
    to_status: Mapped[ShipmentStatus] = enum_column(
        ShipmentStatus, constraint_name="shipment_status_to", nullable=False
    )
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    shipment: Mapped[Shipment] = relationship("Shipment", back_populates="status_history")


# =====================================================================================
# Returns & Restocking
# =====================================================================================


class ReturnRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "return_requests"

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[ReturnStatus] = enum_column(
        ReturnStatus, default=ReturnStatus.REQUESTED, nullable=False, index=True
    )
    reason: Mapped[ReturnReason] = enum_column(ReturnReason, nullable=False)
    customer_notes: Mapped[str] = mapped_column(Text, nullable=False)
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Inspection outcome determines refund eligibility and whether stock is resalable.
    inspection_outcome: Mapped[InspectionOutcome | None] = enum_column(
        InspectionOutcome, nullable=True
    )
    inspection_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    inspected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    inspected_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    restocked: Mapped[bool] = mapped_column(default=False, nullable=False)
    restocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    refund_amount_lkr: Mapped[Decimal | None] = money_column(nullable=True)
    refund_method: Mapped[RefundMethod | None] = enum_column(RefundMethod, nullable=True)
    refund_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    order: Mapped[Order] = relationship("Order", back_populates="returns")
    user: Mapped[User] = relationship("User", foreign_keys=[user_id])
    inspected_by: Mapped[User | None] = relationship("User", foreign_keys=[inspected_by_id])
    refunded_by: Mapped[User | None] = relationship("User", foreign_keys=[refunded_by_id])
    items: Mapped[list[ReturnItem]] = relationship(
        "ReturnItem", back_populates="return_request", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_returns_user_status", "user_id", "status"),
        Index("ix_returns_order_status", "order_id", "status"),
    )


class ReturnItem(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "return_items"

    return_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("return_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("order_items.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    return_request: Mapped[ReturnRequest] = relationship("ReturnRequest", back_populates="items")
    order_item: Mapped[OrderItem] = relationship("OrderItem")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_return_item_quantity_positive"),
        UniqueConstraint("return_request_id", "order_item_id", name="uq_return_request_order_item"),
    )


# =====================================================================================
# Audit Log
# =====================================================================================


class AuditLog(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "audit_logs"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    changes: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
