# syntax=docker/dockerfile:1.7
# ---------- build stage: resolve dependencies with uv into a virtualenv ----------
FROM python:3.14-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ---------- runtime stage: slim image, non-root user, no build tooling ----------
FROM python:3.14-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000

RUN groupadd --system --gid 10001 chronostore \
    && useradd --system --uid 10001 --gid chronostore --home-dir /app --shell /usr/sbin/nologin chronostore

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=chronostore:chronostore alembic.ini ./
COPY --chown=chronostore:chronostore app ./app

USER chronostore
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2).status == 200 else 1)"]

# TLS is terminated by the reverse proxy; trust its X-Forwarded-* headers only from
# addresses configured in FORWARDED_ALLOW_IPS.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips=${FORWARDED_ALLOW_IPS:-127.0.0.1} --no-access-log --no-server-header"]
