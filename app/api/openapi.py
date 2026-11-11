"""OpenAPI metadata: description, tag catalogue and reusable error responses."""

from typing import Any

from app.schemas.common import ProblemDetail

API_DESCRIPTION = """
**ChronoStore** is an online wristwatch store serving customers across **Sri Lanka**.
This API powers the storefront and back-office.

### Capabilities
* **Catalog** - brands, categories and wristwatch products (movement, materials, water
  resistance, dial colour, images) with search, filtering, sorting and pagination.
* **Accounts** - registration, OAuth2 password login issuing short-lived JWT access tokens
  and rotating refresh tokens, profiles and delivery addresses.
* **Cart & checkout** - server-priced carts and idempotent checkout (`Idempotency-Key`).
* **Orders & Cash on Delivery** - order history, cancellation and explicit COD payment states.
* **Inventory** - stock reservation that prevents overselling, adjustments and movement history.
* **Fulfilment & returns** - shipments with tracking and status history, return review,
  inspection and controlled restocking.
* **Administration & reports** - sales, order, best-seller and inventory reports, audit log.

### Conventions
* All monetary amounts are in **LKR** and serialised as decimal strings (e.g. `"125000.00"`).
* All timestamps are timezone-aware **UTC** in ISO 8601 format. Report date ranges are
  calendar dates interpreted in the store's timezone (`Asia/Colombo`).
* Errors use **RFC 9457 Problem Details** (`application/problem+json`) with a stable `code`.
* Every response carries an `X-Request-ID` header; supply your own to correlate requests.
* Collections are paginated with `page` (≥ 1) and `page_size` (1-100).

### Authentication
Use **Authorize** with your email and password (OAuth2 password flow), or send
`Authorization: Bearer <access_token>`. Admin endpoints require the `admin` role.
"""

OPENAPI_TAGS: list[dict[str, Any]] = [
    {"name": "Auth", "description": "Registration, login and token lifecycle."},
    {"name": "Users", "description": "The authenticated user's profile and addresses."},
    {"name": "Products", "description": "Wristwatch catalogue."},
    {"name": "Brands", "description": "Watch brands."},
    {"name": "Categories", "description": "Product categories."},
    {"name": "Cart", "description": "The authenticated customer's shopping cart."},
    {"name": "Checkout", "description": "Idempotent order placement from the cart."},
    {"name": "Orders", "description": "Customer order history, cancellation and payment."},
    {"name": "Shipments", "description": "Shipment tracking for customers."},
    {"name": "Returns", "description": "Customer return requests."},
    {"name": "Admin: Orders", "description": "Order confirmation, cancellation and COD."},
    {"name": "Admin: Shipments", "description": "Fulfilment and shipment status changes."},
    {"name": "Admin: Returns", "description": "Return review, receipt, inspection, refund."},
    {"name": "Admin: Inventory", "description": "Stock levels, adjustments and movements."},
    {"name": "Admin: Reports", "description": "Sales, order and inventory reporting."},
    {"name": "Admin: Users", "description": "User administration and role management."},
    {"name": "Admin: Audit", "description": "Audit trail of sensitive operations."},
    {"name": "Health", "description": "Liveness and readiness probes."},
]

_PROBLEM_CONTENT = {"application/problem+json": {"schema": ProblemDetail.model_json_schema()}}


def _problem(description: str) -> dict[str, Any]:
    return {"model": ProblemDetail, "description": description}


VALIDATION_RESPONSE = {422: _problem("Request validation or business rule failed.")}
AUTH_RESPONSES = {
    401: _problem("Missing, invalid or expired access token."),
    403: _problem("Authenticated but not permitted."),
}
NOT_FOUND_RESPONSE = {404: _problem("Resource not found (or not visible to the caller).")}
CONFLICT_RESPONSE = {409: _problem("Conflicts with the current state of the resource.")}
RATE_LIMIT_RESPONSE = {429: _problem("Rate limit exceeded; see `Retry-After`.")}


def responses(*groups: dict[int, dict[str, Any]]) -> dict[int | str, dict[str, Any]]:
    merged: dict[int | str, dict[str, Any]] = {}
    for group in groups:
        merged.update(group)
    return merged
