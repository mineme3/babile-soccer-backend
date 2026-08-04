# ── Stage 1: Build ──────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install deps first (layer cache)
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# ── Stage 2: Runtime ────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# libpq for asyncpg, curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY app/ app/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Admin is auto-seeded on first startup via main.py lifespan
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*'"]
