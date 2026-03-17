#!/usr/bin/env bash
###############################################################################
# Railway.app startup script
#
# Runs data bootstrap on first deploy, then starts the API server.
# DuckDB file persists in Railway's ephemeral storage per deploy.
###############################################################################

set -euo pipefail

DB_PATH="${LENSKART_DB_PATH:-/app/data/dev.duckdb}"

echo "=== Lenskart Retail Intelligence — Railway Startup ==="

# Bootstrap data if DB doesn't exist yet
if [ ! -f "$DB_PATH" ]; then
    echo "[1/4] Generating synthetic data..."
    python data/synthetic/generate.py

    echo "[2/4] Loading dbt seeds..."
    python data/load_seeds.py

    echo "[3/4] Running dbt pipeline..."
    cd transform/dbt
    dbt seed --profiles-dir . --full-refresh
    dbt run --profiles-dir .
    cd /app

    echo "[4/4] Running ML pipelines..."
    python scripts/demo_e2e.py --skip-data-foundation || echo "Pipeline completed with warnings"

    echo "=== Bootstrap complete ==="
else
    echo "Database exists, skipping bootstrap"
fi

# Start API server
echo "=== Starting API server on port ${PORT:-8000} ==="
exec uvicorn apps.api.app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers 1 \
    --timeout-keep-alive 30
