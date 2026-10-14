# syntax=docker/dockerfile:1

# ── 1. Vue app: unit tests, type check, production build ────────────────────
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ .
RUN npx vitest run && npm run build

# ── 2. Python dependencies from the lock file ──────────────────────────────
FROM ghcr.io/astral-sh/uv:0.13.1-python3.14-trixie-slim AS deps
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv UV_PYTHON_DOWNLOADS=never
COPY api/pyproject.toml api/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

# ── 3. Runtime: one image for the API (uvicorn) and the simulator ──────────
FROM python:3.14-slim AS runtime
RUN useradd --uid 10001 --no-create-home app
WORKDIR /app
COPY --from=deps /app/.venv /app/.venv
COPY api/monitor ./monitor
COPY --from=web /web/dist ./static
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 STATIC_DIR=/app/static TZ=Europe/Berlin
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=30s --start-interval=2s \
  CMD python -c "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2).status != 200)"
CMD ["uvicorn", "monitor.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header", "--log-level", "warning"]
