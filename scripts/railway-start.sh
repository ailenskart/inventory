#!/usr/bin/env bash
###############################################################################
# Railway.app startup script
#
# Runs data bootstrap on first deploy, then starts the API server.
# Uses lite mode to keep memory usage low and startup fast.
###############################################################################

set -euo pipefail

DB_PATH="${LENSKART_DB_PATH:-/app/data/dev.duckdb}"
export LENSKART_DATA_LITE="${LENSKART_DATA_LITE:-1}"

echo "=== Lenskart Retail Intelligence — Railway Startup ==="

# Always rebuild data on deploy to pick up latest generator changes
if [ -f "$DB_PATH" ]; then
    echo "Removing stale database to force fresh bootstrap..."
    rm -f "$DB_PATH" "${DB_PATH}.wal"
fi

if [ ! -f "$DB_PATH" ]; then
    echo "[1/4] Generating synthetic data (lite=$LENSKART_DATA_LITE)..."
    python data/synthetic/generate.py || {
        echo "WARNING: Data generation failed, starting API without data"
    }

    if ls data/synthetic/*.csv 1>/dev/null 2>&1; then
        echo "[2/4] Loading dbt seeds..."
        python data/load_seeds.py || echo "WARNING: Seed loading failed"

        echo "[3/4] Running dbt pipeline..."
        cd transform/dbt
        dbt seed --profiles-dir . --full-refresh || echo "WARNING: dbt seed failed"
        dbt run --profiles-dir . || echo "WARNING: dbt run failed"
        cd /app

        echo "[4/4] Running ML pipelines..."
        python scripts/demo_e2e.py --skip-data-foundation || echo "WARNING: ML pipeline completed with warnings"
    else
        echo "No CSV files found, skipping dbt and ML steps"
    fi

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
