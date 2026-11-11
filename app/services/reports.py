"""Business reporting and administration service."""

from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.core.exceptions import BusinessRuleViolationError
from app.domain.enums import OrderStatus
from app.domain.pricing import quantize_money, stock_status
from app.models.entities import AuditLog, InventoryItem, Order, OrderItem, Product
from app.schemas.reports import (
    AuditLogResponse,
    BestSellingWatch,
    LowStockProductReport,
    OrdersByStatusReport,
    SalesReportItem,
    SalesReportResponse,
)


class ReportService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.tz = ZoneInfo(settings.business_timezone)

    def sales_report(self, start_date: date, end_date: date) -> SalesReportResponse:
        if start_date > end_date:
            raise BusinessRuleViolationError("start_date cannot be after end_date.")

        # Convert date range to UTC timestamps according to Sri Lanka business timezone
        start_dt = datetime.combine(start_date, time.min, tzinfo=self.tz)
        end_dt = datetime.combine(end_date, time.max, tzinfo=self.tz)

        # Sales are recognized for placed/confirmed/shipped/delivered orders (exclude cancelled)
        valid_statuses = [
            OrderStatus.PLACED,
            OrderStatus.CONFIRMED,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
        ]

        orders = list(
            self.session.execute(
                select(Order).where(
                    Order.created_at >= start_dt,
                    Order.created_at <= end_dt,
                    Order.status.in_(valid_statuses),
                )
            )
            .scalars()
            .all()
        )

        daily_map: dict[date, dict] = {}
        curr = start_date
        while curr <= end_date:
            daily_map[curr] = {
                "orders": 0,
                "gross": Decimal("0.00"),
                "shipping": Decimal("0.00"),
                "net": Decimal("0.00"),
            }
            curr = date.fromordinal(curr.toordinal() + 1)

        total_rev = Decimal("0.00")
        for o in orders:
            local_day = o.created_at.astimezone(self.tz).date()
            if local_day in daily_map:
                daily_map[local_day]["orders"] += 1
                daily_map[local_day]["gross"] += o.total_lkr
                daily_map[local_day]["shipping"] += o.shipping_fee_lkr
                daily_map[local_day]["net"] += o.subtotal_lkr
                total_rev += o.total_lkr

        breakdown = [
            SalesReportItem(
                date=day,
                order_count=data["orders"],
                gross_sales_lkr=quantize_money(data["gross"]),
                shipping_collected_lkr=quantize_money(data["shipping"]),
                net_sales_lkr=quantize_money(data["net"]),
            )
            for day, data in sorted(daily_map.items())
        ]

        return SalesReportResponse(
            start_date=start_date,
            end_date=end_date,
            total_orders=len(orders),
            total_revenue_lkr=quantize_money(total_rev),
            currency="LKR",
            daily_breakdown=breakdown,
        )

    def orders_by_status(self) -> list[OrdersByStatusReport]:
        results = self.session.execute(
            select(
                Order.status,
                func.count(Order.id).label("count"),
                func.coalesce(func.sum(Order.total_lkr), Decimal("0.00")).label("total"),
            ).group_by(Order.status)
        ).all()

        return [
            OrdersByStatusReport(
                status=row.status,
                count=row.count,
                total_amount_lkr=quantize_money(row.total),
            )
            for row in results
        ]

    def best_selling_watches(self, limit: int = 10) -> list[BestSellingWatch]:
        results = self.session.execute(
            select(
                OrderItem.product_id,
                OrderItem.product_sku,
                OrderItem.product_name,
                OrderItem.brand_name,
                func.sum(OrderItem.quantity).label("units_sold"),
                func.sum(OrderItem.line_total_lkr).label("revenue"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .where(Order.status != OrderStatus.CANCELLED)
            .group_by(
                OrderItem.product_id,
                OrderItem.product_sku,
                OrderItem.product_name,
                OrderItem.brand_name,
            )
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(limit)
        ).all()

        return [
            BestSellingWatch(
                product_id=row.product_id,
                sku=row.product_sku,
                product_name=row.product_name,
                brand_name=row.brand_name,
                units_sold=row.units_sold,
                revenue_lkr=quantize_money(row.revenue),
            )
            for row in results
        ]

    def low_stock_report(self) -> list[LowStockProductReport]:
        items = list(
            self.session.execute(
                select(InventoryItem)
                .options(joinedload(InventoryItem.product).joinedload(Product.brand))
                .join(Product, Product.id == InventoryItem.product_id)
                .where(
                    (InventoryItem.on_hand - InventoryItem.reserved) <= Product.low_stock_threshold
                )
            )
            .scalars()
            .all()
        )

        reports = []
        for i in items:
            p = i.product
            status = stock_status(i.available, p.low_stock_threshold)
            reports.append(
                LowStockProductReport(
                    product_id=p.id,
                    sku=p.sku,
                    name=p.name,
                    brand_name=p.brand.name,
                    on_hand=i.on_hand,
                    reserved=i.reserved,
                    available=i.available,
                    threshold=p.low_stock_threshold,
                    stock_status=status,
                )
            )
        return reports

    def list_audit_logs(self, limit: int = 50) -> list[AuditLogResponse]:
        logs = list(
            self.session.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit))
            .scalars()
            .all()
        )
        return [AuditLogResponse.model_validate(log) for log in logs]
