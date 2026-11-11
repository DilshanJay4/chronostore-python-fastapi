"""Shopping cart business service: server-calculated totals, availability checks."""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.core.exceptions import BusinessRuleViolationError, NotFoundError
from app.domain.enums import ProductStatus
from app.domain.pricing import calculate_totals, quantize_money
from app.models.entities import Cart, CartItem, Product
from app.schemas.cart import (
    CartItemAddRequest,
    CartItemResponse,
    CartItemUpdateRequest,
    CartResponse,
)
from app.schemas.common import money


class CartService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def get_or_create_cart(self, user_id: uuid.UUID) -> Cart:
        cart = self.session.execute(
            select(Cart).where(Cart.user_id == user_id)
        ).scalar_one_or_none()
        if not cart:
            cart = Cart(user_id=user_id)
            self.session.add(cart)
            self.session.commit()
            self.session.refresh(cart)
        return cart

    def get_cart_response(self, user_id: uuid.UUID) -> CartResponse:
        cart = self.get_or_create_cart(user_id)
        # Fetch items with products, brands and inventory
        items = list(
            self.session.execute(
                select(CartItem)
                .options(
                    joinedload(CartItem.product).joinedload(Product.brand),
                    joinedload(CartItem.product).joinedload(Product.inventory_item),
                )
                .where(CartItem.cart_id == cart.id)
                .order_by(CartItem.created_at.asc())
            )
            .scalars()
            .all()
        )

        item_responses: list[CartItemResponse] = []
        valid_lines: list[tuple[Decimal, int]] = []
        has_unavailable = False
        total_items = 0

        for item in items:
            product = item.product
            inv = product.inventory_item if product else None
            available_stock = inv.available if inv else 0
            is_published = product and product.status == ProductStatus.PUBLISHED

            is_available = is_published and available_stock >= item.quantity
            stock_warning = None
            if not is_published:
                is_available = False
                stock_warning = "This watch is currently discontinued or unavailable."
                has_unavailable = True
            elif available_stock < item.quantity:
                is_available = False
                has_unavailable = True
                stock_warning = f"Only {available_stock} in stock (requested {item.quantity})."

            line_sum = (
                quantize_money(product.price_lkr * item.quantity) if product else Decimal("0.00")
            )
            if is_available and product:
                valid_lines.append((product.price_lkr, item.quantity))
                total_items += item.quantity

            item_responses.append(
                CartItemResponse(
                    id=item.id,
                    product_id=product.id,
                    product_sku=product.sku,
                    product_name=product.name,
                    brand_name=product.brand.name,
                    unit_price_lkr=product.price_lkr,
                    quantity=item.quantity,
                    line_total_lkr=line_sum,
                    is_available=is_available,
                    stock_warning=stock_warning,
                )
            )

        calc = calculate_totals(
            valid_lines,
            flat_fee=self.settings.shipping_flat_fee_lkr,
            free_threshold=self.settings.free_shipping_threshold_lkr,
        )

        return CartResponse(
            id=cart.id,
            items=item_responses,
            subtotal=money(calc.subtotal),
            shipping_fee=money(calc.shipping_fee),
            total=money(calc.total),
            currency=self.settings.currency,
            item_count=total_items,
            has_unavailable_items=has_unavailable,
        )

    def add_item(self, user_id: uuid.UUID, data: CartItemAddRequest) -> CartResponse:
        cart = self.get_or_create_cart(user_id)
        product = self.session.execute(
            select(Product)
            .options(joinedload(Product.inventory_item))
            .where(Product.id == data.product_id)
        ).scalar_one_or_none()

        if not product or product.status != ProductStatus.PUBLISHED:
            raise NotFoundError("Product not found or currently unavailable.")

        inv = product.inventory_item
        available = inv.available if inv else 0
        if available < data.quantity:
            raise BusinessRuleViolationError(
                f"Insufficient stock available. Only {available} available."
            )

        existing_item = self.session.execute(
            select(CartItem).where(
                CartItem.cart_id == cart.id, CartItem.product_id == data.product_id
            )
        ).scalar_one_or_none()

        if existing_item:
            new_qty = existing_item.quantity + data.quantity
            if new_qty > self.settings.max_cart_item_quantity:
                raise BusinessRuleViolationError(
                    f"Maximum quantity per item is {self.settings.max_cart_item_quantity}."
                )
            if available < new_qty:
                raise BusinessRuleViolationError(
                    f"Cannot add {data.quantity} more. Only {available} available in total."
                )
            existing_item.quantity = new_qty
        else:
            # Check maximum lines limit
            current_lines = (
                self.session.execute(select(CartItem).where(CartItem.cart_id == cart.id))
                .scalars()
                .all()
            )
            if len(current_lines) >= self.settings.max_cart_lines:
                raise BusinessRuleViolationError(
                    f"Cart cannot exceed {self.settings.max_cart_lines} unique products."
                )

            new_item = CartItem(
                cart_id=cart.id,
                product_id=data.product_id,
                quantity=data.quantity,
            )
            self.session.add(new_item)

        self.session.commit()
        return self.get_cart_response(user_id)

    def update_item_quantity(
        self, user_id: uuid.UUID, item_id: uuid.UUID, data: CartItemUpdateRequest
    ) -> CartResponse:
        cart = self.get_or_create_cart(user_id)
        item = self.session.execute(
            select(CartItem)
            .options(joinedload(CartItem.product).joinedload(Product.inventory_item))
            .where(CartItem.id == item_id, CartItem.cart_id == cart.id)
        ).scalar_one_or_none()

        if not item:
            raise NotFoundError("Cart item not found.")

        if data.quantity > self.settings.max_cart_item_quantity:
            raise BusinessRuleViolationError(
                f"Maximum quantity per item is {self.settings.max_cart_item_quantity}."
            )

        inv = item.product.inventory_item if item.product else None
        avail = inv.available if inv else 0
        if avail < data.quantity:
            raise BusinessRuleViolationError(
                f"Requested quantity {data.quantity} exceeds available stock ({avail})."
            )

        item.quantity = data.quantity
        self.session.commit()
        return self.get_cart_response(user_id)

    def remove_item(self, user_id: uuid.UUID, item_id: uuid.UUID) -> CartResponse:
        cart = self.get_or_create_cart(user_id)
        item = self.session.execute(
            select(CartItem).where(CartItem.id == item_id, CartItem.cart_id == cart.id)
        ).scalar_one_or_none()
        if not item:
            raise NotFoundError("Cart item not found.")

        self.session.delete(item)
        self.session.commit()
        return self.get_cart_response(user_id)

    def clear_cart(self, user_id: uuid.UUID) -> None:
        cart = self.get_or_create_cart(user_id)
        for item in (
            self.session.execute(select(CartItem).where(CartItem.cart_id == cart.id))
            .scalars()
            .all()
        ):
            self.session.delete(item)
        self.session.commit()
