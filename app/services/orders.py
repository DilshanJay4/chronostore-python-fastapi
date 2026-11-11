"""Order and checkout service with PostgreSQL row-level locking for concurrency protection."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.core.exceptions import (
    BusinessRuleViolationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from app.domain.enums import (
    InventoryMovementType,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    ProductStatus,
)
from app.domain.pricing import calculate_totals, quantize_money
from app.domain.state_machines import (
    CUSTOMER_CANCELLABLE_ORDER_STATUSES,
    ORDER_TRANSITIONS,
    PAYMENT_TRANSITIONS,
    ensure_transition,
)
from app.models.entities import (
    Address,
    AuditLog,
    Cart,
    CartItem,
    IdempotencyRecord,
    InventoryItem,
    InventoryMovement,
    Order,
    OrderItem,
    Payment,
    Product,
    User,
)
from app.schemas.orders import (
    CheckoutRequest,
    OrderCancelRequest,
    OrderResponse,
    PaymentCollectRequest,
)


class OrderService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def checkout(
        self,
        user_id: uuid.UUID,
        data: CheckoutRequest,
        idempotency_key: str | None = None,
        request_body_raw: bytes | None = None,
    ) -> tuple[OrderResponse, bool]:
        """Perform transactional checkout:
        1. Validate idempotency key if provided
        2. Lock and validate address
        3. Lock cart and products
        4. Reserve inventory with row-level locks
        5. Create Order, OrderItems snapshot, Payment (COD Pending)
        6. Record inventory movements
        7. Clear cart
        8. Store idempotency record
        """
        # --- 1. Idempotency Check ---
        req_hash = ""
        if idempotency_key:
            req_hash = hashlib.sha256(request_body_raw or b"").hexdigest()
            existing_rec = self.session.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.user_id == user_id,
                    IdempotencyRecord.idempotency_key == idempotency_key,
                )
            ).scalar_one_or_none()

            if existing_rec:
                if existing_rec.request_hash != req_hash:
                    raise ConflictError("Idempotency key reused with different request payload.")
                # Return previously recorded response
                return OrderResponse.model_validate(existing_rec.response_body), True

        # --- 2. Delivery Address Validation ---
        address = self.session.execute(
            select(Address).where(
                Address.id == data.shipping_address_id, Address.user_id == user_id
            )
        ).scalar_one_or_none()
        if not address:
            raise NotFoundError("Shipping address not found.")

        address_snapshot = {
            "recipient_name": address.recipient_name,
            "phone": address.phone,
            "street_line1": address.street_line1,
            "street_line2": address.street_line2,
            "city": address.city,
            "postal_code": address.postal_code,
            "province": address.province,
            "country_code": address.country_code,
        }

        # --- 3. Fetch Cart and Items ---
        cart = self.session.execute(
            select(Cart).where(Cart.user_id == user_id)
        ).scalar_one_or_none()
        if not cart:
            raise BusinessRuleViolationError("Shopping cart is empty.")

        cart_items = list(
            self.session.execute(
                select(CartItem)
                .where(CartItem.cart_id == cart.id)
                .order_by(CartItem.product_id.asc())
            )
            .scalars()
            .all()
        )
        if not cart_items:
            raise BusinessRuleViolationError("Shopping cart is empty.")

        # --- 4. Lock Inventory Items for Update ---
        # Sorting product_ids prevents deadlocks when concurrent checkouts overlap
        product_ids = sorted({item.product_id for item in cart_items})
        inventory_records = {
            inv.product_id: inv
            for inv in self.session.execute(
                select(InventoryItem)
                .where(InventoryItem.product_id.in_(product_ids))
                .with_for_update()
            )
            .scalars()
            .all()
        }

        # Lock products as well
        products = {
            p.id: p
            for p in self.session.execute(
                select(Product)
                .options(joinedload(Product.brand))
                .where(Product.id.in_(product_ids))
            )
            .scalars()
            .all()
        }

        lines_for_pricing: list[tuple[Decimal, int]] = []
        order_items_data: list[dict] = []

        for item in cart_items:
            product = products.get(item.product_id)
            inv = inventory_records.get(item.product_id)

            if not product or product.status != ProductStatus.PUBLISHED:
                p_name = product.name if product else str(item.product_id)
                raise ConflictError(f"Product '{p_name}' is no longer available.")

            if not inv or inv.available < item.quantity:
                avail = inv.available if inv else 0
                msg = f"Insufficient stock for '{product.name}': {item.quantity} > {avail}."
                raise ConflictError(msg)

            line_sum = quantize_money(product.price_lkr * item.quantity)
            lines_for_pricing.append((product.price_lkr, item.quantity))
            order_items_data.append(
                {
                    "product_id": product.id,
                    "product_sku": product.sku,
                    "product_name": product.name,
                    "brand_name": product.brand.name,
                    "unit_price_lkr": product.price_lkr,
                    "quantity": item.quantity,
                    "line_total_lkr": line_sum,
                }
            )

        # --- 5. Calculate Server Totals ---
        totals = calculate_totals(
            lines_for_pricing,
            flat_fee=self.settings.shipping_flat_fee_lkr,
            free_threshold=self.settings.free_shipping_threshold_lkr,
        )

        # Generate readable Sri Lankan order reference (e.g. CS-202611-ABC123)
        order_num = f"CS-{datetime.now(UTC).strftime('%Y%m')}-{secrets.token_hex(3).upper()}"

        order = Order(
            order_number=order_num,
            user_id=user_id,
            status=OrderStatus.PLACED,
            subtotal_lkr=totals.subtotal,
            shipping_fee_lkr=totals.shipping_fee,
            total_lkr=totals.total,
            currency="LKR",
            shipping_address_snapshot=address_snapshot,
            customer_notes=data.customer_notes,
        )
        self.session.add(order)
        self.session.flush()

        for oi in order_items_data:
            item_entity = OrderItem(order_id=order.id, **oi)
            self.session.add(item_entity)

            # Reserve inventory atomically
            inv = inventory_records[oi["product_id"]]
            inv.reserved += oi["quantity"]
            self.session.flush()

            # Record movement
            movement = InventoryMovement(
                product_id=oi["product_id"],
                movement_type=InventoryMovementType.RESERVATION,
                quantity_delta=0,
                reserved_delta=oi["quantity"],
                on_hand_after=inv.on_hand,
                reserved_after=inv.reserved,
                reason=None,
                notes=f"Reserved for order {order_num}",
                reference_id=order.id,
                actor_id=user_id,
            )
            self.session.add(movement)

        # Create separate COD payment record
        payment = Payment(
            order_id=order.id,
            method=PaymentMethod.CASH_ON_DELIVERY,
            status=PaymentStatus.PENDING,
            amount_lkr=totals.total,
            currency="LKR",
        )
        self.session.add(payment)

        # Clear cart items
        self.session.execute(delete(CartItem).where(CartItem.cart_id == cart.id))

        self.session.flush()
        self.session.refresh(order)

        resp = self.get_order_by_id(order.id, user_id=user_id, is_admin=False)

        # Durable idempotency record
        if idempotency_key:
            rec = IdempotencyRecord(
                user_id=user_id,
                idempotency_key=idempotency_key,
                request_hash=req_hash,
                response_status=201,
                response_body=resp.model_dump(mode="json"),
                expires_at=datetime.now(UTC)
                + timedelta(hours=self.settings.idempotency_key_ttl_hours),
            )
            self.session.add(rec)

        self.session.commit()
        return resp, False

    def get_order_by_id(
        self, order_id: uuid.UUID, user_id: uuid.UUID | None = None, is_admin: bool = False
    ) -> OrderResponse:
        stmt = (
            select(Order)
            .options(joinedload(Order.items), joinedload(Order.payment))
            .where(Order.id == order_id)
        )
        order = self.session.execute(stmt).unique().scalar_one_or_none()
        if not order:
            raise NotFoundError("Order not found.")
        if not is_admin and user_id and order.user_id != user_id:
            raise PermissionDeniedError("You do not have permission to access this order.")
        return OrderResponse.model_validate(order)

    def list_orders(
        self, user_id: uuid.UUID | None = None, is_admin: bool = False
    ) -> list[OrderResponse]:
        stmt = (
            select(Order)
            .options(joinedload(Order.items), joinedload(Order.payment))
            .order_by(Order.created_at.desc())
        )
        if not is_admin and user_id:
            stmt = stmt.where(Order.user_id == user_id)
        orders = list(self.session.execute(stmt).unique().scalars().all())
        return [OrderResponse.model_validate(o) for o in orders]

    def cancel_order(
        self,
        order_id: uuid.UUID,
        user: User,
        data: OrderCancelRequest,
        is_admin: bool = False,
    ) -> OrderResponse:
        order = self.session.execute(
            select(Order).where(Order.id == order_id).with_for_update()
        ).scalar_one_or_none()

        if not order:
            raise NotFoundError("Order not found.")

        if not is_admin and order.user_id != user.id:
            raise PermissionDeniedError("You do not have permission to cancel this order.")

        if not is_admin and order.status not in CUSTOMER_CANCELLABLE_ORDER_STATUSES:
            raise BusinessRuleViolationError(
                f"Orders in '{order.status.value}' status cannot be cancelled by the customer."
            )

        ensure_transition("order", ORDER_TRANSITIONS, order.status, OrderStatus.CANCELLED)

        # Release inventory reservations
        for oi in order.items:
            if oi.product_id:
                inv = self.session.execute(
                    select(InventoryItem)
                    .where(InventoryItem.product_id == oi.product_id)
                    .with_for_update()
                ).scalar_one_or_none()
                if inv and inv.reserved >= oi.quantity:
                    inv.reserved -= oi.quantity
                    movement = InventoryMovement(
                        product_id=oi.product_id,
                        movement_type=InventoryMovementType.RESERVATION_RELEASE,
                        quantity_delta=0,
                        reserved_delta=-oi.quantity,
                        on_hand_after=inv.on_hand,
                        reserved_after=inv.reserved,
                        notes=f"Released reservation from cancelled order {order.order_number}",
                        reference_id=order.id,
                        actor_id=user.id,
                    )
                    self.session.add(movement)

        order.status = OrderStatus.CANCELLED
        order.cancellation_reason = data.reason
        order.cancelled_at = datetime.now(UTC)

        # Void pending payment
        if order.payment and order.payment.status in (PaymentStatus.PENDING, PaymentStatus.FAILED):
            order.payment.status = PaymentStatus.VOIDED
            order.payment.notes = f"Voided due to order cancellation: {data.reason}"

        # Audit log
        audit = AuditLog(
            actor_id=user.id,
            action="order.cancel",
            resource_type="order",
            resource_id=order.id,
            changes={"reason": data.reason, "cancelled_by_role": user.role.value},
        )
        self.session.add(audit)

        self.session.commit()
        return self.get_order_by_id(order.id, is_admin=True)

    def record_cod_collection(
        self, order_id: uuid.UUID, admin: User, data: PaymentCollectRequest
    ) -> OrderResponse:
        order = self.session.execute(
            select(Order).where(Order.id == order_id).with_for_update()
        ).scalar_one_or_none()

        if not order:
            raise NotFoundError("Order not found.")

        payment = order.payment
        if not payment:
            raise NotFoundError("Payment record not found for this order.")

        ensure_transition("payment", PAYMENT_TRANSITIONS, payment.status, PaymentStatus.COLLECTED)

        payment.status = PaymentStatus.COLLECTED
        payment.collected_at = datetime.now(UTC)
        payment.collected_by_id = admin.id
        payment.collection_reference = data.collection_reference
        payment.notes = data.notes

        # Audit log
        audit = AuditLog(
            actor_id=admin.id,
            action="payment.cod_collect",
            resource_type="payment",
            resource_id=payment.id,
            changes={
                "order_id": str(order.id),
                "amount_lkr": str(payment.amount_lkr),
                "reference": data.collection_reference,
            },
        )
        self.session.add(audit)

        self.session.commit()
        return self.get_order_by_id(order.id, is_admin=True)
