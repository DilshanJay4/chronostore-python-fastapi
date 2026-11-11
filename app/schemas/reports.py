"""Schemas for back-office administration and reporting."""

import uuid
from datetime import date, datetime

from app.domain.enums import OrderStatus, StockStatus
from app.schemas.common import APIModel, MoneyAmount


class SalesReportItem(APIModel):
    date: date
    order_count: int
    gross_sales_lkr: MoneyAmount
    shipping_collected_lkr: MoneyAmount
    net_sales_lkr: MoneyAmount


class SalesReportResponse(APIModel):
    start_date: date
    end_date: date
    total_orders: int
    total_revenue_lkr: MoneyAmount
    currency: str = "LKR"
    daily_breakdown: list[SalesReportItem]


class OrdersByStatusReport(APIModel):
    status: OrderStatus
    count: int
    total_amount_lkr: MoneyAmount


class BestSellingWatch(APIModel):
    product_id: uuid.UUID | None
    sku: str
    product_name: str
    brand_name: str
    units_sold: int
    revenue_lkr: MoneyAmount


class LowStockProductReport(APIModel):
    product_id: uuid.UUID
    sku: str
    name: str
    brand_name: str
    on_hand: int
    reserved: int
    available: int
    threshold: int
    stock_status: StockStatus


class AuditLogResponse(APIModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None
    action: str
    resource_type: str
    resource_id: uuid.UUID
    changes: dict | None
    created_at: datetime
