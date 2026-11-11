"""Top-level API v1 router composing all domain endpoints."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin_reports,
    auth,
    brands,
    cart,
    categories,
    inventory,
    orders,
    products,
    shipments,
    users,
)

api_router = APIRouter()

# Authentication & Users
api_router.include_router(auth.router)
api_router.include_router(users.router)

# Catalog
api_router.include_router(products.router)
api_router.include_router(brands.router)
api_router.include_router(categories.router)

# Cart & Checkout
api_router.include_router(cart.router)
api_router.include_router(orders.checkout_router)

# Orders & COD
api_router.include_router(orders.orders_router)
api_router.include_router(orders.admin_orders_router)

# Inventory
api_router.include_router(inventory.router)

# Shipments & Returns
api_router.include_router(shipments.shipments_router)
api_router.include_router(shipments.admin_shipments_router)
api_router.include_router(shipments.returns_router)
api_router.include_router(shipments.direct_returns_router)
api_router.include_router(shipments.admin_returns_router)

# Admin Reports & Auditing
api_router.include_router(admin_reports.router)
