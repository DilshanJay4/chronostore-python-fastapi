# ChronoStore Shared Contract Test Suite

This directory contains the **backend-agnostic HTTP contract test suite** for ChronoStore.
It verifies that any running ChronoStore backend implementation conforms to:
- [`chronostore-v1.yaml`](../contracts/openapi/chronostore-v1.yaml) (OpenAPI 3.1.0 specification)
- [`schemas/*.json`](../contracts/schemas/) (Standalone JSON Schema 2020-12 definitions)
- Domain state machines, LKR monetary formatting, RFC 9457 Problem Details, idempotency, and inventory concurrency rules.

## Prerequisites

The target backend must be running in Docker and accessible via HTTP, with its database migrated and seeded with the standard administrator account (`admin@chronostore.lk` / `Admin@Chrono2026`).

## Running Against Any Backend (via Docker)

From the `backend-mastery/` workspace root:

```bash
# Default: targets http://host.docker.internal:8000
docker compose -f chronostore-shared/contract-tests/compose.yaml run --rm contract-tests

# Custom port or target URL:
BASE_URL=http://host.docker.internal:8080 \
  docker compose -f chronostore-shared/contract-tests/compose.yaml run --rm contract-tests
```

## Running Standalone Inside an Individual Backend Repository

Each backend repository includes a synchronized snapshot at `contracts/reference/`:

```bash
docker compose -f contracts/reference/contract-tests/compose.yaml run --rm contract-tests
```

