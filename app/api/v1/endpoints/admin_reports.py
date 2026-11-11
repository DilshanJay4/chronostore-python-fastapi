"""Endpoints for administration reports and audit trail."""

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.openapi import AUTH_RESPONSES, VALIDATION_RESPONSE, responses
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.dependencies.auth import require_admin
from app.models.entities import User
from app.schemas.reports import (
    AuditLogResponse,
    BestSellingWatch,
    LowStockProductReport,
    OrdersByStatusReport,
    SalesReportResponse,
)
from app.services.reports import ReportService

router = APIRouter(prefix="/admin", tags=["Admin: Reports"])


def _default_start_date() -> date:
    return (datetime.now(UTC) - timedelta(days=30)).date()


def _default_end_date() -> date:
    return datetime.now(UTC).date()


@router.get(
    "/reports/sales",
    response_model=SalesReportResponse,
    summary="Daily sales and revenue report across validated date range (Admin only)",
    responses=responses(AUTH_RESPONSES, VALIDATION_RESPONSE),
)
def get_sales_report(
    start_date: date = Query(
        default_factory=_default_start_date,
        description="Start date (YYYY-MM-DD)",
    ),
    end_date: date = Query(
        default_factory=_default_end_date,
        description="End date (YYYY-MM-DD)",
    ),
    _: User = Depends(require_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SalesReportResponse:
    service = ReportService(session, settings)
    return service.sales_report(start_date, end_date)


@router.get(
    "/reports/orders",
    response_model=list[OrdersByStatusReport],
    summary="Order counts and monetary volume grouped by status (Admin only)",
    responses=AUTH_RESPONSES,
)
def get_orders_by_status(
    _: User = Depends(require_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[OrdersByStatusReport]:
    service = ReportService(session, settings)
    return service.orders_by_status()


@router.get(
    "/reports/best-sellers",
    response_model=list[BestSellingWatch],
    summary="Top selling wristwatch products by unit volume and revenue (Admin only)",
    responses=AUTH_RESPONSES,
)
def get_best_sellers(
    limit: int = Query(default=10, ge=1, le=50),
    _: User = Depends(require_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[BestSellingWatch]:
    service = ReportService(session, settings)
    return service.best_selling_watches(limit)


@router.get(
    "/reports/inventory",
    response_model=list[LowStockProductReport],
    summary="Low stock and out of stock product reports (Admin only)",
    responses=AUTH_RESPONSES,
)
def get_low_stock_report(
    _: User = Depends(require_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[LowStockProductReport]:
    service = ReportService(session, settings)
    return service.low_stock_report()


@router.get(
    "/audit-logs",
    response_model=list[AuditLogResponse],
    summary="View system audit trail for security-sensitive actions (Admin only)",
    responses=AUTH_RESPONSES,
)
def get_audit_logs(
    limit: int = Query(default=50, ge=1, le=100),
    _: User = Depends(require_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[AuditLogResponse]:
    service = ReportService(session, settings)
    return service.list_audit_logs(limit)
