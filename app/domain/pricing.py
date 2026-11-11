"""Pure pricing rules. All amounts are `Decimal` LKR rounded to cents (half-up)."""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.domain.enums import StockStatus

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def quantize_money(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def line_total(unit_price: Decimal, quantity: int) -> Decimal:
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if unit_price < 0:
        raise ValueError("unit_price must not be negative")
    return quantize_money(unit_price * quantity)


def shipping_fee(subtotal: Decimal, *, flat_fee: Decimal, free_threshold: Decimal) -> Decimal:
    """Flat island-wide delivery fee, waived at or above the free-shipping threshold."""
    if subtotal <= ZERO:
        return ZERO
    return ZERO if subtotal >= free_threshold else quantize_money(flat_fee)


@dataclass(frozen=True, slots=True)
class Totals:
    subtotal: Decimal
    shipping_fee: Decimal
    total: Decimal


def calculate_totals(
    lines: Iterable[tuple[Decimal, int]], *, flat_fee: Decimal, free_threshold: Decimal
) -> Totals:
    subtotal = quantize_money(sum((line_total(p, q) for p, q in lines), ZERO))
    fee = shipping_fee(subtotal, flat_fee=flat_fee, free_threshold=free_threshold)
    return Totals(subtotal=subtotal, shipping_fee=fee, total=quantize_money(subtotal + fee))


def stock_status(available: int, low_stock_threshold: int) -> StockStatus:
    if available <= 0:
        return StockStatus.OUT_OF_STOCK
    if available <= low_stock_threshold:
        return StockStatus.LOW_STOCK
    return StockStatus.IN_STOCK
