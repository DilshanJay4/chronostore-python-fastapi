from decimal import Decimal

import pytest

from app.core.exceptions import InvalidStateTransitionError
from app.domain.enums import OrderStatus, PaymentStatus, ReturnStatus, ShipmentStatus, StockStatus
from app.domain.pricing import calculate_totals, line_total, shipping_fee, stock_status
from app.domain.state_machines import (
    CUSTOMER_CANCELLABLE_ORDER_STATUSES,
    ORDER_TRANSITIONS,
    PAYMENT_TRANSITIONS,
    RETURN_TRANSITIONS,
    SHIPMENT_TRANSITIONS,
    can_transition,
    ensure_transition,
)

FLAT = Decimal("500.00")
FREE_AT = Decimal("50000.00")


def test_order_transitions() -> None:
    assert can_transition(ORDER_TRANSITIONS, OrderStatus.PLACED, OrderStatus.CONFIRMED)
    assert can_transition(ORDER_TRANSITIONS, OrderStatus.PLACED, OrderStatus.CANCELLED)
    assert can_transition(ORDER_TRANSITIONS, OrderStatus.CONFIRMED, OrderStatus.SHIPPED)
    assert can_transition(ORDER_TRANSITIONS, OrderStatus.SHIPPED, OrderStatus.DELIVERED)
    assert can_transition(ORDER_TRANSITIONS, OrderStatus.SHIPPED, OrderStatus.DELIVERY_FAILED)
    assert can_transition(ORDER_TRANSITIONS, OrderStatus.DELIVERY_FAILED, OrderStatus.SHIPPED)
    assert can_transition(ORDER_TRANSITIONS, OrderStatus.DELIVERY_FAILED, OrderStatus.CANCELLED)

    assert not can_transition(ORDER_TRANSITIONS, OrderStatus.CANCELLED, OrderStatus.CONFIRMED)
    assert not can_transition(ORDER_TRANSITIONS, OrderStatus.DELIVERED, OrderStatus.SHIPPED)
    assert not can_transition(ORDER_TRANSITIONS, OrderStatus.PLACED, OrderStatus.DELIVERED)

    with pytest.raises(InvalidStateTransitionError):
        ensure_transition("order", ORDER_TRANSITIONS, OrderStatus.CANCELLED, OrderStatus.CONFIRMED)


def test_customer_cancellation_allowed_only_early() -> None:
    assert OrderStatus.PLACED in CUSTOMER_CANCELLABLE_ORDER_STATUSES
    assert OrderStatus.CONFIRMED in CUSTOMER_CANCELLABLE_ORDER_STATUSES
    assert OrderStatus.SHIPPED not in CUSTOMER_CANCELLABLE_ORDER_STATUSES
    assert OrderStatus.DELIVERED not in CUSTOMER_CANCELLABLE_ORDER_STATUSES


def test_cod_payment_transitions() -> None:
    assert can_transition(PAYMENT_TRANSITIONS, PaymentStatus.PENDING, PaymentStatus.COLLECTED)
    assert can_transition(PAYMENT_TRANSITIONS, PaymentStatus.PENDING, PaymentStatus.FAILED)
    assert can_transition(PAYMENT_TRANSITIONS, PaymentStatus.PENDING, PaymentStatus.VOIDED)
    assert can_transition(PAYMENT_TRANSITIONS, PaymentStatus.FAILED, PaymentStatus.PENDING)
    assert can_transition(PAYMENT_TRANSITIONS, PaymentStatus.FAILED, PaymentStatus.VOIDED)
    assert not can_transition(PAYMENT_TRANSITIONS, PaymentStatus.COLLECTED, PaymentStatus.VOIDED)


def test_shipment_transitions() -> None:
    assert can_transition(SHIPMENT_TRANSITIONS, ShipmentStatus.PENDING, ShipmentStatus.DISPATCHED)
    assert can_transition(SHIPMENT_TRANSITIONS, ShipmentStatus.DISPATCHED, ShipmentStatus.DELIVERED)
    assert can_transition(SHIPMENT_TRANSITIONS, ShipmentStatus.DISPATCHED, ShipmentStatus.FAILED)
    assert can_transition(SHIPMENT_TRANSITIONS, ShipmentStatus.FAILED, ShipmentStatus.RETURNED)
    assert not can_transition(
        SHIPMENT_TRANSITIONS, ShipmentStatus.DELIVERED, ShipmentStatus.PENDING
    )


def test_return_transitions() -> None:
    assert can_transition(RETURN_TRANSITIONS, ReturnStatus.REQUESTED, ReturnStatus.APPROVED)
    assert can_transition(RETURN_TRANSITIONS, ReturnStatus.REQUESTED, ReturnStatus.REJECTED)
    assert can_transition(RETURN_TRANSITIONS, ReturnStatus.APPROVED, ReturnStatus.RECEIVED)
    assert can_transition(RETURN_TRANSITIONS, ReturnStatus.RECEIVED, ReturnStatus.INSPECTED)
    assert can_transition(RETURN_TRANSITIONS, ReturnStatus.INSPECTED, ReturnStatus.REFUNDED)
    assert not can_transition(RETURN_TRANSITIONS, ReturnStatus.REJECTED, ReturnStatus.APPROVED)


def test_line_total_multiplies_and_quantizes() -> None:
    assert line_total(Decimal("12500.50"), 3) == Decimal("37501.50")
    with pytest.raises(ValueError, match="quantity must be positive"):
        line_total(Decimal("10.00"), 0)
    with pytest.raises(ValueError, match="unit_price must not be negative"):
        line_total(Decimal("-5.00"), 1)


def test_shipping_fee_waived_at_threshold() -> None:
    assert shipping_fee(Decimal("0.00"), flat_fee=FLAT, free_threshold=FREE_AT) == Decimal("0.00")
    assert shipping_fee(Decimal("49999.99"), flat_fee=FLAT, free_threshold=FREE_AT) == FLAT
    assert shipping_fee(Decimal("50000.00"), flat_fee=FLAT, free_threshold=FREE_AT) == Decimal(
        "0.00"
    )
    assert shipping_fee(Decimal("120000.00"), flat_fee=FLAT, free_threshold=FREE_AT) == Decimal(
        "0.00"
    )


def test_calculate_totals() -> None:
    lines = [(Decimal("10000.00"), 2), (Decimal("5000.50"), 1)]
    totals = calculate_totals(lines, flat_fee=FLAT, free_threshold=FREE_AT)
    assert totals.subtotal == Decimal("25000.50")
    assert totals.shipping_fee == FLAT
    assert totals.total == Decimal("25500.50")

    big_lines = [(Decimal("60000.00"), 1)]
    big_totals = calculate_totals(big_lines, flat_fee=FLAT, free_threshold=FREE_AT)
    assert big_totals.shipping_fee == Decimal("0.00")
    assert big_totals.total == Decimal("60000.00")


def test_stock_status_buckets() -> None:
    assert stock_status(0, 5) == StockStatus.OUT_OF_STOCK
    assert stock_status(-1, 5) == StockStatus.OUT_OF_STOCK
    assert stock_status(3, 5) == StockStatus.LOW_STOCK
    assert stock_status(5, 5) == StockStatus.LOW_STOCK
    assert stock_status(6, 5) == StockStatus.IN_STOCK
