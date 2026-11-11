"""Fulfillment service: shipments, dispatch, delivery, and return lifecycle."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.core.exceptions import (
    BusinessRuleViolationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from app.domain.enums import (
    AdjustmentReason,
    InspectionOutcome,
    InventoryMovementType,
    OrderStatus,
    PaymentStatus,
    ReturnStatus,
    ShipmentStatus,
    UserRole,
)
from app.domain.state_machines import (
    ACTIVE_SHIPMENT_STATUSES,
    RETURN_TRANSITIONS,
    SHIPMENT_TRANSITIONS,
    ensure_transition,
)
from app.models.entities import (
    AuditLog,
    InventoryItem,
    InventoryMovement,
    Order,
    ReturnItem,
    ReturnRequest,
    Shipment,
    ShipmentStatusHistory,
    User,
)
from app.schemas.fulfillment import (
    ReturnInspectRequest,
    ReturnRefundRequest,
    ReturnRequestCreate,
    ReturnResponse,
    ReturnReviewRequest,
    ShipmentCreateRequest,
    ShipmentResponse,
    ShipmentStatusUpdateRequest,
)


class FulfillmentService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    # --- Shipments ---
    def create_shipment(
        self, order_id: uuid.UUID, data: ShipmentCreateRequest, admin: User
    ) -> ShipmentResponse:
        order = self.session.execute(
            select(Order).where(Order.id == order_id).with_for_update()
        ).scalar_one_or_none()

        if not order:
            raise NotFoundError("Order not found.")

        if order.status not in (OrderStatus.PLACED, OrderStatus.CONFIRMED):
            raise BusinessRuleViolationError(
                f"Cannot create shipment for order in '{order.status.value}' status."
            )

        active = [s for s in order.shipments if s.status in ACTIVE_SHIPMENT_STATUSES]
        if active:
            raise ConflictError("An active shipment already exists for this order.")

        # Verify tracking number uniqueness
        existing_trk = self.session.execute(
            select(Shipment).where(Shipment.tracking_number == data.tracking_number)
        ).scalar_one_or_none()
        if existing_trk:
            raise ConflictError(f"Tracking number '{data.tracking_number}' is already assigned.")

        shipment = Shipment(
            order_id=order.id,
            tracking_number=data.tracking_number,
            carrier=data.carrier,
            status=ShipmentStatus.PENDING,
            notes=data.notes,
        )
        self.session.add(shipment)
        self.session.flush()

        history = ShipmentStatusHistory(
            shipment_id=shipment.id,
            from_status=None,
            to_status=ShipmentStatus.PENDING,
            notes="Shipment created",
            changed_by_id=admin.id,
        )
        self.session.add(history)

        # Transition order to confirmed if it was placed
        if order.status == OrderStatus.PLACED:
            order.status = OrderStatus.CONFIRMED
            order.confirmed_at = datetime.now(UTC)

        self.session.commit()
        return self.get_shipment_by_id(shipment.id)

    def _handle_dispatch(
        self, order: Order, shipment: Shipment, admin: User, now: datetime
    ) -> None:
        shipment.dispatched_at = now
        if order.status in (OrderStatus.PLACED, OrderStatus.CONFIRMED):
            order.status = OrderStatus.SHIPPED

        for oi in order.items:
            if oi.product_id:
                inv = self.session.execute(
                    select(InventoryItem)
                    .where(InventoryItem.product_id == oi.product_id)
                    .with_for_update()
                ).scalar_one_or_none()
                if inv:
                    inv.on_hand -= oi.quantity
                    inv.reserved -= oi.quantity
                    movement = InventoryMovement(
                        product_id=oi.product_id,
                        movement_type=InventoryMovementType.DISPATCH,
                        quantity_delta=-oi.quantity,
                        reserved_delta=-oi.quantity,
                        on_hand_after=inv.on_hand,
                        reserved_after=inv.reserved,
                        notes=f"Dispatched in shipment {shipment.tracking_number}",
                        reference_id=order.id,
                        actor_id=admin.id,
                    )
                    self.session.add(movement)

    def _handle_return_to_sender(
        self, order: Order, shipment: Shipment, admin: User, now: datetime
    ) -> None:
        for oi in order.items:
            if oi.product_id:
                inv = self.session.execute(
                    select(InventoryItem)
                    .where(InventoryItem.product_id == oi.product_id)
                    .with_for_update()
                ).scalar_one_or_none()
                if inv:
                    inv.on_hand += oi.quantity
                    movement = InventoryMovement(
                        product_id=oi.product_id,
                        movement_type=InventoryMovementType.RETURN_TO_SENDER_RESTOCK,
                        quantity_delta=oi.quantity,
                        reserved_delta=0,
                        on_hand_after=inv.on_hand,
                        reserved_after=inv.reserved,
                        reason=AdjustmentReason.RESTOCK,
                        notes=f"Restocked after return to sender: {shipment.tracking_number}",
                        reference_id=order.id,
                        actor_id=admin.id,
                    )
                    self.session.add(movement)
        order.status = OrderStatus.CANCELLED
        order.cancellation_reason = "Returned by courier after failed delivery."
        order.cancelled_at = now

    def update_shipment_status(
        self, shipment_id: uuid.UUID, data: ShipmentStatusUpdateRequest, admin: User
    ) -> ShipmentResponse:
        shipment = self.session.execute(
            select(Shipment).where(Shipment.id == shipment_id).with_for_update()
        ).scalar_one_or_none()

        if not shipment:
            raise NotFoundError("Shipment not found.")

        old_status = shipment.status
        new_status = data.status
        ensure_transition("shipment", SHIPMENT_TRANSITIONS, old_status, new_status)

        now = datetime.now(UTC)
        order = shipment.order

        if new_status == ShipmentStatus.DISPATCHED:
            self._handle_dispatch(order, shipment, admin, now)
        elif new_status == ShipmentStatus.DELIVERED:
            shipment.delivered_at = now
            order.status = OrderStatus.DELIVERED
        elif new_status == ShipmentStatus.FAILED:
            order.status = OrderStatus.DELIVERY_FAILED
        elif new_status == ShipmentStatus.RETURNED:
            self._handle_return_to_sender(order, shipment, admin, now)

        shipment.status = new_status
        history = ShipmentStatusHistory(
            shipment_id=shipment.id,
            from_status=old_status,
            to_status=new_status,
            notes=data.notes,
            changed_by_id=admin.id,
        )
        self.session.add(history)
        self.session.commit()
        return self.get_shipment_by_id(shipment.id)

    def get_shipment_by_id(self, shipment_id: uuid.UUID) -> ShipmentResponse:
        shipment = (
            self.session.execute(
                select(Shipment)
                .options(joinedload(Shipment.status_history))
                .where(Shipment.id == shipment_id)
            )
            .unique()
            .scalar_one_or_none()
        )
        if not shipment:
            raise NotFoundError("Shipment not found.")
        return ShipmentResponse.model_validate(shipment)

    def get_order_shipments(
        self, order_id: uuid.UUID, user: User | None = None
    ) -> list[ShipmentResponse]:
        order = self.session.execute(select(Order).where(Order.id == order_id)).scalar_one_or_none()
        if not order:
            raise NotFoundError("Order not found.")
        if user and user.role != UserRole.ADMIN and order.user_id != user.id:
            raise PermissionDeniedError("You do not have permission to view this order's shipments.")

        shipments = list(
            self.session.execute(
                select(Shipment)
                .options(joinedload(Shipment.status_history))
                .where(Shipment.order_id == order_id)
                .order_by(Shipment.created_at.desc())
            )
            .unique()
            .scalars()
            .all()
        )
        return [ShipmentResponse.model_validate(s) for s in shipments]

    # --- Returns ---
    def request_return(
        self, order_id: uuid.UUID, user: User, data: ReturnRequestCreate
    ) -> ReturnResponse:
        order = (
            self.session.execute(
                select(Order)
                .options(joinedload(Order.items), joinedload(Order.payment))
                .where(Order.id == order_id)
            )
            .unique()
            .scalar_one_or_none()
        )

        if not order:
            raise NotFoundError("Order not found.")
        if user.role != UserRole.ADMIN and order.user_id != user.id:
            raise PermissionDeniedError("You do not have permission to request a return for this order.")

        if order.status != OrderStatus.DELIVERED:
            raise BusinessRuleViolationError("Returns can only be requested for delivered orders.")

        if not order.payment or order.payment.status != PaymentStatus.COLLECTED:
            raise BusinessRuleViolationError(
                "Cannot request return: COD payment has not been marked as collected."
            )

        # Check return window
        now = datetime.now(UTC)
        window = timedelta(days=self.settings.return_window_days)
        # Use shipment delivery timestamp or order updated_at
        delivery_time = order.updated_at
        if now - delivery_time > window:
            raise BusinessRuleViolationError(
                f"Return window of {self.settings.return_window_days} days has expired."
            )

        order_items_by_id = {item.id: item for item in order.items}
        for item_req in data.items:
            if item_req.order_item_id not in order_items_by_id:
                raise BusinessRuleViolationError(
                    f"Item {item_req.order_item_id} does not belong to this order."
                )
            if item_req.quantity > order_items_by_id[item_req.order_item_id].quantity:
                raise BusinessRuleViolationError(
                    f"Return quantity {item_req.quantity} exceeds ordered quantity."
                )

        ret = ReturnRequest(
            order_id=order.id,
            user_id=user.id,
            status=ReturnStatus.REQUESTED,
            reason=data.reason,
            customer_notes=data.customer_notes,
        )
        self.session.add(ret)
        self.session.flush()

        for it in data.items:
            ri = ReturnItem(
                return_request_id=ret.id,
                order_item_id=it.order_item_id,
                quantity=it.quantity,
            )
            self.session.add(ri)

        self.session.commit()
        return self.get_return_by_id(ret.id)

    def review_return(
        self, return_id: uuid.UUID, data: ReturnReviewRequest, admin: User
    ) -> ReturnResponse:
        ret = self.session.execute(
            select(ReturnRequest).where(ReturnRequest.id == return_id).with_for_update()
        ).scalar_one_or_none()
        if not ret:
            raise NotFoundError("Return request not found.")

        target = ReturnStatus.APPROVED if data.approved else ReturnStatus.REJECTED
        ensure_transition("return", RETURN_TRANSITIONS, ret.status, target)

        ret.status = target
        ret.admin_notes = data.admin_notes

        audit = AuditLog(
            actor_id=admin.id,
            action=f"return.{target.value}",
            resource_type="return_request",
            resource_id=ret.id,
            changes={"approved": data.approved, "notes": data.admin_notes},
        )
        self.session.add(audit)

        self.session.commit()
        return self.get_return_by_id(ret.id)

    def receive_return(self, return_id: uuid.UUID, admin: User) -> ReturnResponse:
        ret = self.session.execute(
            select(ReturnRequest).where(ReturnRequest.id == return_id).with_for_update()
        ).scalar_one_or_none()
        if not ret:
            raise NotFoundError("Return request not found.")

        ensure_transition("return", RETURN_TRANSITIONS, ret.status, ReturnStatus.RECEIVED)
        ret.status = ReturnStatus.RECEIVED
        self.session.commit()
        return self.get_return_by_id(ret.id)

    def inspect_return(
        self, return_id: uuid.UUID, data: ReturnInspectRequest, admin: User
    ) -> ReturnResponse:
        ret = self.session.execute(
            select(ReturnRequest).where(ReturnRequest.id == return_id).with_for_update()
        ).scalar_one_or_none()

        if not ret:
            raise NotFoundError("Return request not found.")

        ensure_transition("return", RETURN_TRANSITIONS, ret.status, ReturnStatus.INSPECTED)

        now = datetime.now(UTC)
        ret.status = ReturnStatus.INSPECTED
        ret.inspection_outcome = data.outcome
        ret.inspection_notes = data.notes
        ret.inspected_at = now
        ret.inspected_by_id = admin.id

        # Restock only if outcome is resellable and flag is set
        if data.outcome == InspectionOutcome.RESELLABLE and data.restock_resellable:
            for item in ret.items:
                oi = item.order_item
                if oi.product_id:
                    inv = self.session.execute(
                        select(InventoryItem)
                        .where(InventoryItem.product_id == oi.product_id)
                        .with_for_update()
                    ).scalar_one_or_none()
                    if inv:
                        inv.on_hand += item.quantity
                        movement = InventoryMovement(
                            product_id=oi.product_id,
                            movement_type=InventoryMovementType.RETURN_RESTOCK,
                            quantity_delta=item.quantity,
                            reserved_delta=0,
                            on_hand_after=inv.on_hand,
                            reserved_after=inv.reserved,
                            reason=AdjustmentReason.RESTOCK,
                            notes=f"Restocked from inspected return {ret.id}",
                            reference_id=ret.id,
                            actor_id=admin.id,
                        )
                        self.session.add(movement)
            ret.restocked = True
            ret.restocked_at = now

        self.session.commit()
        return self.get_return_by_id(ret.id)

    def record_refund(
        self, return_id: uuid.UUID, data: ReturnRefundRequest, admin: User
    ) -> ReturnResponse:
        ret = self.session.execute(
            select(ReturnRequest).where(ReturnRequest.id == return_id).with_for_update()
        ).scalar_one_or_none()

        if not ret:
            raise NotFoundError("Return request not found.")

        ensure_transition("return", RETURN_TRANSITIONS, ret.status, ReturnStatus.REFUNDED)

        ret.status = ReturnStatus.REFUNDED
        ret.refund_amount_lkr = data.refund_amount_lkr
        ret.refund_method = data.refund_method
        ret.refund_reference = data.refund_reference
        ret.refunded_at = datetime.now(UTC)
        ret.refunded_by_id = admin.id

        audit = AuditLog(
            actor_id=admin.id,
            action="return.refund",
            resource_type="return_request",
            resource_id=ret.id,
            changes={
                "amount": str(data.refund_amount_lkr),
                "method": data.refund_method.value,
                "reference": data.refund_reference,
            },
        )
        self.session.add(audit)

        self.session.commit()
        return self.get_return_by_id(ret.id)

    def get_return_by_id(
        self, return_id: uuid.UUID, user: User | None = None
    ) -> ReturnResponse:
        ret = (
            self.session.execute(
                select(ReturnRequest)
                .options(joinedload(ReturnRequest.items))
                .where(ReturnRequest.id == return_id)
            )
            .unique()
            .scalar_one_or_none()
        )
        if not ret:
            raise NotFoundError("Return request not found.")
        if user and user.role != UserRole.ADMIN and ret.user_id != user.id:
            raise PermissionDeniedError("You do not have permission to view this return request.")
        return ReturnResponse.model_validate(ret)
