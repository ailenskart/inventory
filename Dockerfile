# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System deps for building wheels (psycopg2, ortools, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY README.md .

# Install deps into a virtual env so we can copy it cleanly
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir .

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# libpq for psycopg2 at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy application code
COPY apps/ apps/
COPY ml/ ml/
COPY services/ services/
COPY schemas/ schemas/
COPY orchestration/ orchestration/
COPY data/ data/
COPY transform/ transform/
COPY scripts/ scripts/
COPY Makefile .
COPY pyproject.toml .

# Install the project in editable mode so module imports work
RUN pip install --no-cache-dir -e .

# Create data directory for DuckDB
RUN mkdir -p /app/data

# Non-root user
RUN groupadd -r lenskart && useradd -r -g lenskart -d /app lenskart \
    && chown -R lenskart:lenskart /app
USER lenskart

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Default: start API server
CMD ["uvicorn", "apps.api.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
