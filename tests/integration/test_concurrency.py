import concurrent.futures
import threading
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.domain.enums import ProductStatus, WatchMovement
from app.models.entities import InventoryItem
from app.schemas.cart import CartItemAddRequest
from app.schemas.catalog import BrandCreate, CategoryCreate, ProductCreate
from app.schemas.orders import CheckoutRequest
from app.schemas.users import AddressCreate, UserRegisterRequest
from app.services.auth import AuthService
from app.services.cart import CartService
from app.services.catalog import CatalogService
from app.services.orders import OrderService
from app.services.users import UserService

pytestmark = pytest.mark.db


def test_concurrent_checkouts_prevent_overselling(db_session: Session) -> None:
    """Critical concurrency test:
    Two customers attempt to checkout the very last available watch at the exact same moment.
    PostgreSQL row-level locking (SELECT ... FOR UPDATE) ensures only one succeeds and the other
    receives a 409 Conflict without overselling or negative inventory.
    """
    settings = get_settings()
    auth_service = AuthService(db_session, settings)
    cat_service = CatalogService(db_session, settings)
    user_service = UserService(db_session, settings)

    # Setup Product with EXACTLY 1 unit in stock
    brand = cat_service.create_brand(BrandCreate(name="Rolex", slug="rolex"))
    category = cat_service.create_category(CategoryCreate(name="Luxury", slug="luxury"))
    product = cat_service.create_product(
        ProductCreate(
            sku="SUB-DATE-126610",
            name="Rolex Submariner Date",
            model="Submariner",
            description="Oystersteel 41mm luxury dive watch with Cerachrom bezel.",
            brand_id=brand.id,
            category_id=category.id,
            movement_type=WatchMovement.AUTOMATIC,
            case_material="Oystersteel",
            strap_material="Oystersteel",
            water_resistance="300m",
            dial_color="Black",
            price_lkr=Decimal("4500000.00"),
            status=ProductStatus.PUBLISHED,
            initial_stock=1,  # Only 1 in stock!
        )
    )

    # Create two distinct customers
    customer_a = auth_service.register(
        UserRegisterRequest(
            email="buyer_a@example.lk",
            password="Password123!",
            full_name="Customer Alpha",
        )
    )
    addr_a = user_service.add_address(
        customer_a.id,
        AddressCreate(
            recipient_name="Customer Alpha",
            phone="0771112222",
            street_line1="1 A Street",
            city="Colombo",
            postal_code="00100",
            province="Western",
            country_code="LK",
        ),
    )

    customer_b = auth_service.register(
        UserRegisterRequest(
            email="buyer_b@example.lk",
            password="Password123!",
            full_name="Customer Beta",
        )
    )
    addr_b = user_service.add_address(
        customer_b.id,
        AddressCreate(
            recipient_name="Customer Beta",
            phone="0773334444",
            street_line1="2 B Street",
            city="Colombo",
            postal_code="00100",
            province="Western",
            country_code="LK",
        ),
    )

    # Both add the 1 item to their carts
    cart_service = CartService(db_session, settings)
    cart_service.add_item(customer_a.id, CartItemAddRequest(product_id=product.id, quantity=1))
    cart_service.add_item(customer_b.id, CartItemAddRequest(product_id=product.id, quantity=1))

    # Setup separate database engines and sessions for concurrent threads
    db_url = settings.database_url.get_secret_value()
    engine = create_engine(db_url, pool_size=5, max_overflow=5)
    session_maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    results = []
    errors = []
    start_barrier = threading.Barrier(2)

    def attempt_checkout(user_id: uuid.UUID, address_id: uuid.UUID):
        session = session_maker()
        try:
            start_barrier.wait()  # synchronize concurrent execution
            svc = OrderService(session, settings)
            order, _ = svc.checkout(
                user_id=user_id,
                data=CheckoutRequest(shipping_address_id=address_id),
            )
            results.append((user_id, order.id))
        except Exception as exc:  # noqa: BLE001
            errors.append((user_id, type(exc).__name__, str(exc)))
        finally:
            session.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(attempt_checkout, customer_a.id, addr_a.id)
        f2 = executor.submit(attempt_checkout, customer_b.id, addr_b.id)
        f1.result()
        f2.result()

    engine.dispose()

    # Exactly ONE must succeed and ONE must fail with ConflictError
    assert len(results) == 1, f"Expected exactly 1 success, got {len(results)}"
    assert len(errors) == 1, f"Expected exactly 1 error, got {len(errors)}"
    assert errors[0][1] == "ConflictError"
    assert "Insufficient stock" in errors[0][2]

    # Verify database invariants
    db_session.rollback()
    inv = db_session.execute(
        select(InventoryItem).where(InventoryItem.product_id == product.id)
    ).scalar_one()
    assert inv.on_hand == 1
    assert inv.reserved == 1
    assert inv.available == 0
