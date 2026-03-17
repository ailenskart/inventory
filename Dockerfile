FROM python:3.11-slim

# System deps (build + runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev libpq5 curl git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (cached layer)
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir .

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

# Install project in editable mode for module imports
RUN pip install --no-cache-dir -e .

# Create writable data directory
RUN mkdir -p /app/data /app/transform/dbt/seeds /app/transform/dbt/target

# Railway uses PORT env var
ENV PORT=8000
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=300s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Start: bootstrap data then run API
CMD ["bash", "scripts/railway-start.sh"]
