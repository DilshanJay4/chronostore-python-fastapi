"""Explicit state machines for orders, COD payments, shipments and returns.

Services must call `ensure_transition` before changing a status so every rule lives here.
See README "State models" for diagrams.
"""

from collections.abc import Mapping
from enum import StrEnum

from app.core.exceptions import InvalidStateTransitionError
from app.domain.enums import OrderStatus, PaymentStatus, ReturnStatus, ShipmentStatus

type TransitionMap[S: StrEnum] = Mapping[S, frozenset[S]]

ORDER_TRANSITIONS: TransitionMap[OrderStatus] = {
    OrderStatus.PLACED: frozenset({OrderStatus.CONFIRMED, OrderStatus.CANCELLED}),
    OrderStatus.CONFIRMED: frozenset({OrderStatus.SHIPPED, OrderStatus.CANCELLED}),
    OrderStatus.SHIPPED: frozenset({OrderStatus.DELIVERED, OrderStatus.DELIVERY_FAILED}),
    # A failed delivery is either re-attempted or the parcel comes back and the order ends.
    OrderStatus.DELIVERY_FAILED: frozenset({OrderStatus.SHIPPED, OrderStatus.CANCELLED}),
    OrderStatus.DELIVERED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
}

# Customers may cancel only before anything has left the warehouse.
CUSTOMER_CANCELLABLE_ORDER_STATUSES = frozenset({OrderStatus.PLACED, OrderStatus.CONFIRMED})

PAYMENT_TRANSITIONS: TransitionMap[PaymentStatus] = {
    PaymentStatus.PENDING: frozenset(
        {PaymentStatus.COLLECTED, PaymentStatus.FAILED, PaymentStatus.VOIDED}
    ),
    # A failed collection can be retried on a re-delivery, or voided if the order ends.
    PaymentStatus.FAILED: frozenset({PaymentStatus.PENDING, PaymentStatus.VOIDED}),
    PaymentStatus.COLLECTED: frozenset(),
    PaymentStatus.VOIDED: frozenset(),
}

SHIPMENT_TRANSITIONS: TransitionMap[ShipmentStatus] = {
    ShipmentStatus.PENDING: frozenset({ShipmentStatus.DISPATCHED, ShipmentStatus.CANCELLED}),
    ShipmentStatus.DISPATCHED: frozenset({ShipmentStatus.DELIVERED, ShipmentStatus.FAILED}),
    ShipmentStatus.FAILED: frozenset({ShipmentStatus.DISPATCHED, ShipmentStatus.RETURNED}),
    ShipmentStatus.DELIVERED: frozenset(),
    ShipmentStatus.RETURNED: frozenset(),
    ShipmentStatus.CANCELLED: frozenset(),
}

ACTIVE_SHIPMENT_STATUSES = frozenset(
    {ShipmentStatus.PENDING, ShipmentStatus.DISPATCHED, ShipmentStatus.FAILED}
)

RETURN_TRANSITIONS: TransitionMap[ReturnStatus] = {
    ReturnStatus.REQUESTED: frozenset(
        {ReturnStatus.APPROVED, ReturnStatus.REJECTED, ReturnStatus.CANCELLED}
    ),
    ReturnStatus.APPROVED: frozenset({ReturnStatus.RECEIVED}),
    # After inspection the return either awaits reimbursement or closes (nothing refundable).
    ReturnStatus.RECEIVED: frozenset({ReturnStatus.INSPECTED, ReturnStatus.CLOSED}),
    ReturnStatus.INSPECTED: frozenset({ReturnStatus.REFUNDED}),
    ReturnStatus.REJECTED: frozenset(),
    ReturnStatus.CANCELLED: frozenset(),
    ReturnStatus.REFUNDED: frozenset(),
    ReturnStatus.CLOSED: frozenset(),
}

# Returns in these states still "hold" item quantities against the order.
OPEN_OR_ACCEPTED_RETURN_STATUSES = frozenset(
    {
        ReturnStatus.REQUESTED,
        ReturnStatus.APPROVED,
        ReturnStatus.RECEIVED,
        ReturnStatus.INSPECTED,
        ReturnStatus.REFUNDED,
        ReturnStatus.CLOSED,
    }
)


def can_transition[S: StrEnum](transitions: TransitionMap[S], current: S, target: S) -> bool:
    return target in transitions.get(current, frozenset())


def ensure_transition[S: StrEnum](
    resource: str, transitions: TransitionMap[S], current: S, target: S
) -> None:
    if not can_transition(transitions, current, target):
        raise InvalidStateTransitionError(
            f"Cannot change {resource} status from '{current.value}' to '{target.value}'.",
            extra={"current_status": current.value, "requested_status": target.value},
        )
