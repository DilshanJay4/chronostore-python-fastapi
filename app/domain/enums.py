"""Domain enumerations shared by models, schemas and services."""

from enum import StrEnum


class UserRole(StrEnum):
    CUSTOMER = "customer"
    ADMIN = "admin"


class WatchMovement(StrEnum):
    QUARTZ = "quartz"
    AUTOMATIC = "automatic"
    MANUAL = "manual"


class ProductStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DISCONTINUED = "discontinued"


class StockStatus(StrEnum):
    IN_STOCK = "in_stock"
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"


class InventoryMovementType(StrEnum):
    ADJUSTMENT = "adjustment"
    RESERVATION = "reservation"
    RESERVATION_RELEASE = "reservation_release"
    DISPATCH = "dispatch"
    RETURN_TO_SENDER_RESTOCK = "return_to_sender_restock"
    RETURN_RESTOCK = "return_restock"


class AdjustmentReason(StrEnum):
    RESTOCK = "restock"
    DAMAGE = "damage"
    LOSS = "loss"
    COUNT_CORRECTION = "count_correction"
    OTHER = "other"


class OrderStatus(StrEnum):
    PLACED = "placed"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    DELIVERY_FAILED = "delivery_failed"
    CANCELLED = "cancelled"


class PaymentMethod(StrEnum):
    CASH_ON_DELIVERY = "cash_on_delivery"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    COLLECTED = "collected"
    FAILED = "failed"
    VOIDED = "voided"


class ShipmentStatus(StrEnum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETURNED = "returned"
    CANCELLED = "cancelled"


class ReturnStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    RECEIVED = "received"
    INSPECTED = "inspected"
    REFUNDED = "refunded"
    CLOSED = "closed"


class ReturnReason(StrEnum):
    DEFECTIVE = "defective"
    DAMAGED_IN_TRANSIT = "damaged_in_transit"
    WRONG_ITEM = "wrong_item"
    NOT_AS_DESCRIBED = "not_as_described"
    CHANGED_MIND = "changed_mind"
    OTHER = "other"


class InspectionOutcome(StrEnum):
    RESELLABLE = "resellable"  # refunded and restocked
    DAMAGED = "damaged"  # refunded, written off (not restocked)
    REJECTED = "rejected"  # not refunded, not restocked (returned to the customer)


class RefundMethod(StrEnum):
    BANK_TRANSFER = "bank_transfer"
    CASH = "cash"
