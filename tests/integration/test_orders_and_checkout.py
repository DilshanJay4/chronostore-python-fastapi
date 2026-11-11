from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain.enums import (
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    ProductStatus,
    UserRole,
    WatchMovement,
)
from app.models.entities import InventoryItem
from app.schemas.cart import CartItemAddRequest
from app.schemas.catalog import BrandCreate, CategoryCreate, ProductCreate
from app.schemas.orders import CheckoutRequest, PaymentCollectRequest
from app.services.auth import AuthService
from app.services.cart import CartService
from app.services.catalog import CatalogService
from app.services.orders import OrderService
from app.services.users import UserService

pytestmark = pytest.mark.db


def test_checkout_order_creation_inventory_reservation_and_cod(
    db_session: Session,
) -> None:
    settings = get_settings()
    auth_service = AuthService(db_session, settings)
    cat_service = CatalogService(db_session, settings)
    cart_service = CartService(db_session, settings)
    order_service = OrderService(db_session, settings)

    # 1. Setup Admin and Customer
    from app.schemas.users import AddressCreate, UserRegisterRequest

    admin = auth_service.register(
        UserRegisterRequest(
            email="admin@chronostore.lk",
            password="AdminPassword123!",
            full_name="Admin User",
        ),
        role=UserRole.ADMIN,
    )

    customer = auth_service.register(
        UserRegisterRequest(
            email="buyer@example.lk",
            password="BuyerPassword123!",
            full_name="Dilshan Perera",
        )
    )

    user_service = UserService(db_session, settings)
    addr = user_service.add_address(
        customer.id,
        AddressCreate(
            label="Home",
            recipient_name="Dilshan Perera",
            phone="0771234567",
            street_line1="10 Duplication Road",
            city="Colombo",
            postal_code="00400",
            province="Western",
            country_code="LK",
        ),
    )

    # 2. Create Brand, Category, Product with initial stock of 3
    brand = cat_service.create_brand(BrandCreate(name="Casio", slug="casio"))
    category = cat_service.create_category(CategoryCreate(name="Chronograph", slug="chronograph"))
    product = cat_service.create_product(
        ProductCreate(
            sku="EDIFICE-EFR",
            name="Casio Edifice EFR-S108D",
            model="EFR-S108D",
            description="Slim sapphire crystal octagonal sports chronograph.",
            brand_id=brand.id,
            category_id=category.id,
            movement_type=WatchMovement.QUARTZ,
            case_material="Stainless Steel",
            strap_material="Stainless Steel",
            water_resistance="100m",
            dial_color="Turquoise",
            price_lkr=Decimal("45000.00"),
            status=ProductStatus.PUBLISHED,
            initial_stock=3,
        )
    )

    # 3. Customer adds 2 watches to cart
    cart_service.add_item(customer.id, CartItemAddRequest(product_id=product.id, quantity=2))
    cart = cart_service.get_cart_response(customer.id)
    assert cart.item_count == 2
    # 45,000 * 2 = 90,000 >= 50,000 threshold -> Shipping is FREE
    assert cart.subtotal.amount == Decimal("90000.00")
    assert cart.shipping_fee.amount == Decimal("0.00")
    assert cart.total.amount == Decimal("90000.00")

    # 4. Checkout with Idempotency Key
    idempotency_key = "test-checkout-idem-key-123"
    order, replayed = order_service.checkout(
        user_id=customer.id,
        data=CheckoutRequest(shipping_address_id=addr.id, customer_notes="Please ring bell."),
        idempotency_key=idempotency_key,
        request_body_raw=b'{"shipping_address_id": "test"}',
    )
    assert not replayed
    assert order.status == OrderStatus.PLACED
    assert order.total_lkr == Decimal("90000.00")
    assert len(order.items) == 1
    assert order.items[0].product_sku == "EDIFICE-EFR"
    assert order.items[0].quantity == 2
    assert order.payment.status == PaymentStatus.PENDING
    assert order.payment.method == PaymentMethod.CASH_ON_DELIVERY

    # Cart should now be empty
    cart_after = cart_service.get_cart_response(customer.id)
    assert cart_after.item_count == 0

    # Stock verification: on_hand=3, reserved=2, available=1
    inv = db_session.execute(
        select(InventoryItem).where(InventoryItem.product_id == product.id)
    ).scalar_one()
    assert inv.on_hand == 3
    assert inv.reserved == 2
    assert inv.available == 1

    # 5. Idempotent retry returns identical order response
    order_retry, replayed_retry = order_service.checkout(
        user_id=customer.id,
        data=CheckoutRequest(shipping_address_id=addr.id, customer_notes="Please ring bell."),
        idempotency_key=idempotency_key,
        request_body_raw=b'{"shipping_address_id": "test"}',
    )
    assert replayed_retry is True
    assert order_retry.id == order.id

    # 6. Admin records COD collection
    updated_order = order_service.record_cod_collection(
        order.id,
        admin=admin,
        data=PaymentCollectRequest(
            collection_reference="REC-COL-00991", notes="Collected full cash on delivery"
        ),
    )
    assert updated_order.payment.status == PaymentStatus.COLLECTED
    assert updated_order.payment.collection_reference == "REC-COL-00991"
