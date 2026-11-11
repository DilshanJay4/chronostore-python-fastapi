# ChronoStore API

Production-ready REST API for an online wristwatch store operating in **Sri Lanka**. Built with FastAPI, PostgreSQL, SQLAlchemy 2.x, Pydantic v2, and managed with `uv`.

---

## 1. Architecture & Design Principles

ChronoStore is architected as a **modular monolith** with clear separation of HTTP handling, application services, domain models, and persistence.

```text
chronostore-python-fastapi/
├── app/
│   ├── main.py                     # ASGI application factory & lifespan
│   ├── api/
│   │   ├── health.py               # /health/live and /health/ready probes
│   │   ├── openapi.py              # OpenAPI documentation & tags
│   │   ├── router.py               # Combined API v1 routing
│   │   └── v1/endpoints/           # HTTP endpoints (auth, users, products, cart, orders, etc.)
│   ├── core/
│   │   ├── config.py               # pydantic-settings configuration & validation
│   │   ├── exceptions.py           # Problem Details RFC 9457 exception handlers
│   │   ├── logging.py              # Structured JSON logging & secret redaction
│   │   ├── middleware.py           # Pure ASGI correlation IDs, security headers, limits
│   │   ├── rate_limit.py           # In-memory sliding window rate limiter
│   │   ├── request_context.py      # ContextVar request ID propagation
│   │   └── security.py             # Argon2 hashing & PyJWT token handling
│   ├── db/
│   │   ├── base.py                 # DeclarativeBase, naming conventions & mixins
│   │   ├── session.py              # Engine, pool configuration & request-scoped session
│   │   ├── migration_state.py      # Migration revision checking for readiness probes
│   │   └── migrations/             # Alembic migration scripts
│   ├── domain/
│   │   ├── enums.py                # WatchMovement, OrderStatus, PaymentStatus, etc.
│   │   ├── pricing.py              # Decimal monetary math & half-up rounding in LKR
│   │   └── state_machines.py       # Explicit state machines (Orders, COD, Shipments, Returns)
│   ├── models/
│   │   └── entities.py             # SQLAlchemy 2.0 typed persistence models
│   ├── schemas/                    # Pydantic v2 validation and serialization schemas
│   ├── services/                   # Business domain services with explicit transaction boundaries
│   └── dependencies/               # FastAPI dependency injection (auth, db, rate limit)
├── tests/
│   ├── unit/                       # Pure unit tests (pricing, domain state machines, config)
│   ├── integration/                # PostgreSQL integration tests (concurrency, orders, auth)
│   └── api/                        # HTTP API and OpenAPI schema validation tests
├── Dockerfile                      # Multi-stage production build (non-root execution)
├── compose.yaml                    # Local multi-service environment (PostgreSQL + API + Migration)
├── pyproject.toml                  # uv package definitions
└── ruff.toml                       # Ruff linter and formatter configuration
```

---

## 2. Core Business Features

- **Store Currency:** Exclusively in **Sri Lankan Rupees (LKR)**. All calculations use `Decimal` with `ROUND_HALF_UP` to prevent floating-point inaccuracies.
- **Product Catalog:** Wristwatch catalog with search, filtering by brand, category, movement (quartz, automatic, manual), price range, and sorting.
- **Customer Accounts & Security:**
  - Secure registration and authentication with **Argon2id** password hashing.
  - JWT access tokens with strict verification (issuer, audience, expiry, algorithm).
  - Refresh tokens stored as SHA-256 digests with automatic rotation and replay attack detection.
  - Customer profile and address management (with default address handling).
  - In-memory sliding window rate limiting on sensitive auth endpoints.
- **Shopping Cart:**
  - Cart totals calculated strictly server-side (unit prices and subtotals).
  - Inventory availability validation and warning flags for discontinued/low stock items.
- **Inventory & Concurrency:**
  - Row-level locking (`SELECT ... FOR UPDATE`) during checkout to prevent overselling under high concurrency.
  - Stock reservations during order placement and automatic release upon order cancellation.
  - Audit trail of stock adjustments and movements.
- **Checkout & Idempotency:**
  - Idempotent order placement via `Idempotency-Key` header with persistent response replay.
  - Delivery address snapshot and product SKU/price snapshots for permanent order integrity.
- **Cash on Delivery (COD) Payments:**
  - Explicit separation between Order state and Payment state.
  - COD payment lifecycle (`pending` -> `collected`, `failed`, or `voided`).
  - Restricted COD collection recording for authorized staff with audit logging.
- **Fulfillment & Shipments:**
  - Shipment creation with carrier and tracking references.
  - Explicit shipment state machine (`pending` -> `dispatched` -> `delivered` / `failed` -> `returned`).
  - Automatic inventory deduction upon physical parcel dispatch.
  - Automatic return-to-sender restocking if courier delivery fails permanently.
- **Returns & Controlled Restocking:**
  - Returns eligible only for delivered and COD-collected orders within the return window (default 14 days).
  - Multi-stage return review: Request -> Admin Review -> Physical Receipt -> Inspection.
  - Restocking happens **only** if inspected items are confirmed as `resellable`.
  - Offline refund recording (bank transfer or cash) with audit trail.
- **Administration & Reporting:**
  - Daily sales and revenue reporting across validated date ranges with Sri Lanka (`Asia/Colombo`) timezone conversion.
  - Order volume breakdown by status.
  - Best-selling watches report.
  - Low-stock and out-of-stock inventory alerts.
  - System audit log for all financial and operational changes.

---

## 3. Technology Stack

- **Python:** 3.14
- **Web Framework:** FastAPI (v0.115+)
- **Validation:** Pydantic v2 & `pydantic-settings`
- **Database:** PostgreSQL 17 with `psycopg` (binary driver v3)
- **ORM:** SQLAlchemy 2.x typed declarative models
- **Migrations:** Alembic
- **Package Management:** `uv`
- **Authentication:** PyJWT (symmetric HMAC), Argon2id (`pwdlib`)
- **Logging:** `structlog` with JSON output and automatic secret redaction
- **Containerization:** Docker & Docker Compose

---

## 4. Setup and Local Development

### Prerequisites
- Docker and Docker Compose
- `uv` (or Python 3.14+)

### Quickstart with Docker Compose

1. Clone and enter the repository:
   ```bash
   cd chronostore-python-fastapi
   ```

2. Create a local `.env` file from the example:
   ```bash
   cp .env.example .env
   # Edit .env and set strong secrets or passwords for local use
   ```

3. Launch PostgreSQL, run migrations, and start the API:
   ```bash
   docker compose up -d
   ```

4. Verify health probes:
   ```bash
   curl http://127.0.0.1:8000/health/live
   curl http://127.0.0.1:8000/health/ready
   ```

5. Access interactive API documentation:
   - **Swagger UI:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
   - **ReDoc:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
   - **OpenAPI Schema:** [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json)

---

## 5. Running Tests and Code Quality

Run tests and linter using `uv`:

```bash
# Run lint and formatting check
uv run ruff check .
uv run ruff format --check .

# Run complete test suite (unit + PostgreSQL integration + concurrency)
uv run pytest -v
```

---

## 6. Security and Observability

- **Structured JSON Logging:** Logs are emitted as structured JSON on stdout with request IDs, response durations, and client IPs. Sensitive keys (`password`, `token`, `authorization`, `database_url`, `idempotency_key`) and embedded bearer tokens are scrubbed recursively.
- **Problem Details RFC 9457:** Consistent, structured error responses with standard status codes, unique error URIs, application error codes, and correlation request IDs.
- **Idempotency Protection:** Replaying requests with the same `Idempotency-Key` returns the stored response with an `Idempotent-Replayed: true` header. Submitting a different payload with the same key returns `409 Conflict`.
- **Database Integrity:** PostgreSQL constraints back application logic (`CHECK (on_hand >= reserved)`, `CHECK (price_lkr >= 0)`, `CHECK (total_lkr = subtotal_lkr + shipping_fee_lkr)`).

---

## 7. Operational Limitations & Production Notes

- **Reverse Proxy / TLS Termination:** Production deployments must terminate TLS at an edge reverse proxy (e.g. Nginx, Traefik, AWS ALB) and configure `FORWARDED_ALLOW_IPS` to pass client IPs securely.
- **Distributed Rate Limiting:** The included sliding window rate limiter is in-memory. For multi-replica horizontal scaling, backing rate limits with a shared Redis store is recommended.
- **Database Migrations:** Schema upgrades in production should be executed via a controlled job (such as Kubernetes migration job or Docker compose `migrate` runner) before traffic routing.

