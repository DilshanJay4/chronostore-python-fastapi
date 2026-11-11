from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain.enums import (
    InspectionOutcome,
    ProductStatus,
    RefundMethod,
    ReturnReason,
    ReturnStatus,
    ShipmentStatus,
    UserRole,
    WatchMovement,
)
from app.models.entities import InventoryItem
from app.schemas.cart import CartItemAddRequest
from app.schemas.catalog import BrandCreate, CategoryCreate, ProductCreate
from app.schemas.fulfillment import (
    ReturnInspectRequest,
    ReturnItemRequest,
    ReturnRefundRequest,
    ReturnRequestCreate,
    ReturnReviewRequest,
    ShipmentCreateRequest,
    ShipmentStatusUpdateRequest,
)
from app.schemas.orders import CheckoutRequest, PaymentCollectRequest
from app.schemas.users import AddressCreate, UserRegisterRequest
from app.services.auth import AuthService
from app.services.cart import CartService
from app.services.catalog import CatalogService
from app.services.fulfillment import FulfillmentService
from app.services.orders import OrderService
from app.services.users import UserService

pytestmark = pytest.mark.db


def test_fulfillment_and_return_lifecycle(db_session: Session) -> None:
    settings = get_settings()
    auth_service = AuthService(db_session, settings)
    cat_service = CatalogService(db_session, settings)
    cart_service = CartService(db_session, settings)
    order_service = OrderService(db_session, settings)
    ful_service = FulfillmentService(db_session, settings)
    user_service = UserService(db_session, settings)

    admin = auth_service.register(
        UserRegisterRequest(
            email="ops_admin@chronostore.lk",
            password="AdminPassword123!",
            full_name="Operations Manager",
        ),
        role=UserRole.ADMIN,
    )
    customer = auth_service.register(
        UserRegisterRequest(
            email="watch_collector@example.lk",
            password="CollectorPass123!",
            full_name="Kamal Gunaratne",
        )
    )

    addr = user_service.add_address(
        customer.id,
        AddressCreate(
            label="Home",
            recipient_name="Kamal Gunaratne",
            phone="0719876543",
            street_line1="55 Havelock Road",
            city="Colombo",
            postal_code="00500",
            province="Western",
            country_code="LK",
        ),
    )

    brand = cat_service.create_brand(BrandCreate(name="Orient", slug="orient"))
    category = cat_service.create_category(CategoryCreate(name="Automatic", slug="auto"))
    product = cat_service.create_product(
        ProductCreate(
            sku="ORIENT-BAMBINO-V4",
            name="Orient Bambino Version 4",
            model="Bambino",
            description="Classic domed crystal dress watch with hacking and hand-winding.",
            brand_id=brand.id,
            category_id=category.id,
            movement_type=WatchMovement.AUTOMATIC,
            case_material="Stainless Steel",
            strap_material="Leather",
            water_resistance="30m",
            dial_color="Emerald Green",
            price_lkr=Decimal("78000.00"),
            status=ProductStatus.PUBLISHED,
            initial_stock=5,
        )
    )

    # 1. Customer places order
    cart_service.add_item(customer.id, CartItemAddRequest(product_id=product.id, quantity=1))
    order, _ = order_service.checkout(customer.id, CheckoutRequest(shipping_address_id=addr.id))

    # 2. Ops Admin creates shipment
    shipment = ful_service.create_shipment(
        order.id,
        ShipmentCreateRequest(
            tracking_number="CERTIS-LK-998822",
            carrier="Certis Lanka",
            notes="Fragile glass handle with care",
        ),
        admin=admin,
    )
    assert shipment.status == ShipmentStatus.PENDING

    # 3. Ops Admin dispatches shipment
    dispatched = ful_service.update_shipment_status(
        shipment.id,
        ShipmentStatusUpdateRequest(
            status=ShipmentStatus.DISPATCHED, notes="Handed over to Certis courier"
        ),
        admin=admin,
    )
    assert dispatched.status == ShipmentStatus.DISPATCHED

    # Inventory check after dispatch: on_hand reduced from 5 to 4, reserved reduced from 1 to 0
    inv = db_session.execute(
        select(InventoryItem).where(InventoryItem.product_id == product.id)
    ).scalar_one()
    assert inv.on_hand == 4
    assert inv.reserved == 0

    # 4. Ops Admin marks shipment DELIVERED
    delivered = ful_service.update_shipment_status(
        shipment.id,
        ShipmentStatusUpdateRequest(status=ShipmentStatus.DELIVERED, notes="Delivered to customer"),
        admin=admin,
    )
    assert delivered.status == ShipmentStatus.DELIVERED

    # 5. Mark COD collected
    order_service.record_cod_collection(
        order.id,
        admin=admin,
        data=PaymentCollectRequest(
            collection_reference="REC-COD-COL-9988", notes="Full COD collected"
        ),
    )

    # 6. Customer requests return
    order_ref = order_service.get_order_by_id(order.id, is_admin=True)
    order_item_id = order_ref.items[0].id

    ret_req = ful_service.request_return(
        order.id,
        user=customer,
        data=ReturnRequestCreate(
            reason=ReturnReason.DEFECTIVE,
            customer_notes="Watch gains 5 minutes per day, mechanism seems faulty.",
            items=[ReturnItemRequest(order_item_id=order_item_id, quantity=1)],
        ),
    )
    assert ret_req.status == ReturnStatus.REQUESTED

    # 7. Admin reviews and approves return
    approved = ful_service.review_return(
        ret_req.id,
        ReturnReviewRequest(approved=True, admin_notes="Authorized for inspection at workshop."),
        admin=admin,
    )
    assert approved.status == ReturnStatus.APPROVED

    # 8. Warehouse receives return parcel
    received = ful_service.receive_return(ret_req.id, admin=admin)
    assert received.status == ReturnStatus.RECEIVED

    # 9. Inspection and restocking
    inspected = ful_service.inspect_return(
        ret_req.id,
        ReturnInspectRequest(
            outcome=InspectionOutcome.RESELLABLE,
            notes="Watch was magnetized; demagnetized and confirmed within specs (+4s/d).",
            restock_resellable=True,
        ),
        admin=admin,
    )
    assert inspected.status == ReturnStatus.INSPECTED
    assert inspected.restocked is True

    # Inventory restocked: on_hand back to 5
    db_session.refresh(inv)
    assert inv.on_hand == 5

    # 10. Record customer reimbursement / refund
    refunded = ful_service.record_refund(
        ret_req.id,
        ReturnRefundRequest(
            refund_amount_lkr=Decimal("78000.00"),
            refund_method=RefundMethod.BANK_TRANSFER,
            refund_reference="BOC-TXN-99881122",
        ),
        admin=admin,
    )
    assert refunded.status == ReturnStatus.REFUNDED
    assert refunded.refund_amount_lkr == Decimal("78000.00")
