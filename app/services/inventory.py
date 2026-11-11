"""Inventory business service: stock adjustments, movement auditing, level reporting."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.core.exceptions import BusinessRuleViolationError, NotFoundError
from app.domain.enums import InventoryMovementType
from app.domain.pricing import stock_status
from app.models.entities import AuditLog, InventoryItem, InventoryMovement, Product, User
from app.schemas.inventory import (
    InventoryAdjustmentRequest,
    InventoryItemResponse,
    InventoryMovementResponse,
)


class InventoryService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def adjust_stock(self, data: InventoryAdjustmentRequest, actor: User) -> InventoryItemResponse:
        item = self.session.execute(
            select(InventoryItem)
            .options(joinedload(InventoryItem.product).joinedload(Product.brand))
            .where(InventoryItem.product_id == data.product_id)
            .with_for_update()
        ).scalar_one_or_none()

        if not item:
            raise NotFoundError("Product or inventory record not found.")

        new_on_hand = item.on_hand + data.quantity_delta
        if new_on_hand < 0:
            raise BusinessRuleViolationError(
                f"Cannot reduce stock by {-data.quantity_delta}. Current on-hand is {item.on_hand}."
            )
        if new_on_hand < item.reserved:
            msg = f"Cannot reduce on-hand below reserved quantities ({item.reserved} reserved)."
            raise BusinessRuleViolationError(msg)

        item.on_hand = new_on_hand

        movement = InventoryMovement(
            product_id=data.product_id,
            movement_type=InventoryMovementType.ADJUSTMENT,
            quantity_delta=data.quantity_delta,
            reserved_delta=0,
            on_hand_after=item.on_hand,
            reserved_after=item.reserved,
            reason=data.reason,
            notes=data.notes,
            actor_id=actor.id,
        )
        self.session.add(movement)

        # Audit log
        audit = AuditLog(
            actor_id=actor.id,
            action="inventory.adjust",
            resource_type="product",
            resource_id=data.product_id,
            changes={
                "delta": data.quantity_delta,
                "reason": data.reason.value,
                "notes": data.notes,
                "new_on_hand": new_on_hand,
            },
        )
        self.session.add(audit)

        self.session.commit()
        return self._to_response(item)

    def list_inventory(self) -> list[InventoryItemResponse]:
        items = list(
            self.session.execute(
                select(InventoryItem)
                .options(joinedload(InventoryItem.product).joinedload(Product.brand))
                .order_by(InventoryItem.updated_at.desc())
            )
            .scalars()
            .all()
        )
        return [self._to_response(i) for i in items]

    def list_movements(
        self, product_id: uuid.UUID | None = None
    ) -> list[InventoryMovementResponse]:
        stmt = (
            select(InventoryMovement)
            .options(joinedload(InventoryMovement.product_id))  # simple join
            .order_by(InventoryMovement.created_at.desc())
        )
        if product_id:
            stmt = stmt.where(InventoryMovement.product_id == product_id)

        # Fetch with product info
        movements = list(self.session.execute(stmt).scalars().all())
        results = []
        for m in movements:
            product = self.session.execute(
                select(Product).where(Product.id == m.product_id)
            ).scalar_one_or_none()
            results.append(
                InventoryMovementResponse(
                    id=m.id,
                    product_id=m.product_id,
                    product_sku=product.sku if product else "UNKNOWN",
                    product_name=product.name if product else "UNKNOWN",
                    movement_type=m.movement_type,
                    quantity_delta=m.quantity_delta,
                    reserved_delta=m.reserved_delta,
                    on_hand_after=m.on_hand_after,
                    reserved_after=m.reserved_after,
                    reason=m.reason,
                    notes=m.notes,
                    reference_id=m.reference_id,
                    actor_id=m.actor_id,
                    created_at=m.created_at,
                )
            )
        return results

    def _to_response(self, item: InventoryItem) -> InventoryItemResponse:
        product = item.product
        status = stock_status(item.available, product.low_stock_threshold)
        return InventoryItemResponse(
            id=item.id,
            product_id=item.product_id,
            product_sku=product.sku,
            product_name=product.name,
            brand_name=product.brand.name,
            on_hand=item.on_hand,
            reserved=item.reserved,
            available=item.available,
            low_stock_threshold=product.low_stock_threshold,
            stock_status=status,
            updated_at=item.updated_at,
        )
