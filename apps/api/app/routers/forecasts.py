"""Forecast API endpoints.

Provides:
- GET /forecasts/store/{store_id}: Forecasts for a specific store
- GET /forecasts/sku/{sku_id}: Forecasts for a specific SKU across stores
- GET /forecasts/latest: Latest stored forecasts with filtering
- POST /forecasts/run: Trigger on-demand forecast generation
"""

import logging
import os
from datetime import date

import duckdb
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("LENSKART_DB_PATH", "data/dev.duckdb")
FORECAST_TABLE = "main_ml.demand_forecasts"


class ForecastRequest(BaseModel):
    store_ids: list[str] | None = None
    sku_ids: list[str] | None = None
    horizon_weeks: int = 4
    target_column: str = "total_qty_sold"


class ForecastRecord(BaseModel):
    store_id: str
    sku_id: str
    forecast_week: str
    point_forecast: float
    lower_bound: float
    upper_bound: float
    model_used: str
    model_version: str
    reason_code: str | None = None
    category: str | None = None
    sku_type: str | None = None


class ForecastSummary(BaseModel):
    total_forecasts: int
    stores: int
    skus: int
    forecast_date: str | None = None


class RunResponse(BaseModel):
    status: str
    message: str
    summary: ForecastSummary | None = None


def _get_connection(read_only: bool = True):
    """Get DuckDB connection."""
    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=503, detail="Database not available")
    return duckdb.connect(DB_PATH, read_only=read_only)


def _has_forecasts() -> bool:
    """Check if forecast table exists."""
    try:
        con = _get_connection()
        con.execute(f"SELECT 1 FROM {FORECAST_TABLE} LIMIT 1")  # noqa: S608
        con.close()
        return True
    except Exception:
        return False


@router.get("/store/{store_id}", response_model=list[ForecastRecord])
def get_store_forecasts(
    store_id: str,
    limit: int = Query(100, le=1000),
):
    """Get demand forecasts for a specific store."""
    if not _has_forecasts():
        raise HTTPException(status_code=404, detail="No forecasts available. Run POST /forecasts/run first.")

    con = _get_connection()
    results = con.execute(f"""
        SELECT store_id, sku_id, forecast_week::varchar as forecast_week,
               point_forecast, lower_bound, upper_bound,
               model_used, model_version,
               reason_code, category, sku_type
        FROM {FORECAST_TABLE}
        WHERE store_id = $1
        ORDER BY forecast_week, sku_id
        LIMIT $2
    """, [store_id, limit]).fetchdf()  # noqa: S608
    con.close()

    if results.empty:
        raise HTTPException(status_code=404, detail=f"No forecasts for store {store_id}")

    return results.to_dict(orient="records")


@router.get("/sku/{sku_id}", response_model=list[ForecastRecord])
def get_sku_forecasts(
    sku_id: str,
    limit: int = Query(100, le=1000),
):
    """Get demand forecasts for a specific SKU across all stores."""
    if not _has_forecasts():
        raise HTTPException(status_code=404, detail="No forecasts available. Run POST /forecasts/run first.")

    con = _get_connection()
    results = con.execute(f"""
        SELECT store_id, sku_id, forecast_week::varchar as forecast_week,
               point_forecast, lower_bound, upper_bound,
               model_used, model_version,
               reason_code, category, sku_type
        FROM {FORECAST_TABLE}
        WHERE sku_id = $1
        ORDER BY forecast_week, store_id
        LIMIT $2
    """, [sku_id, limit]).fetchdf()  # noqa: S608
    con.close()

    if results.empty:
        raise HTTPException(status_code=404, detail=f"No forecasts for SKU {sku_id}")

    return results.to_dict(orient="records")


@router.get("/latest", response_model=dict)
def get_latest_forecasts(
    store_id: str | None = Query(None),
    sku_id: str | None = Query(None),
    category: str | None = Query(None),
    limit: int = Query(100, le=1000),
):
    """Retrieve latest stored forecasts with optional filters."""
    if not _has_forecasts():
        return {"forecasts": [], "count": 0, "message": "No forecasts available"}

    con = _get_connection()

    conditions = []
    params = []
    param_idx = 1

    if store_id:
        conditions.append(f"store_id = ${param_idx}")
        params.append(store_id)
        param_idx += 1

    if sku_id:
        conditions.append(f"sku_id = ${param_idx}")
        params.append(sku_id)
        param_idx += 1

    if category:
        conditions.append(f"category = ${param_idx}")
        params.append(category)
        param_idx += 1

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    results = con.execute(f"""
        SELECT store_id, sku_id, forecast_week::varchar as forecast_week,
               point_forecast, lower_bound, upper_bound,
               model_used, model_version, reason_code, category, sku_type
        FROM {FORECAST_TABLE}
        {where_clause}
        ORDER BY forecast_week DESC, store_id, sku_id
        LIMIT ${param_idx}
    """, params + [limit]).fetchdf()  # noqa: S608
    con.close()

    return {
        "forecasts": results.to_dict(orient="records"),
        "count": len(results),
    }


@router.post("/run", response_model=RunResponse)
def trigger_forecast_run(request: ForecastRequest):
    """Trigger on-demand forecast generation.

    Runs the batch inference pipeline and writes results to DuckDB.
    """
    try:
        from ml.forecasting.config import ForecastConfig
        from ml.forecasting.predict import run_inference_pipeline

        config = ForecastConfig(
            db_path=DB_PATH,
            horizon_weeks=request.horizon_weeks,
            target_column=request.target_column,
        )

        forecasts = run_inference_pipeline(config, write_to_db=True)

        if forecasts.empty:
            return RunResponse(
                status="error",
                message="No forecasts generated — check data availability",
            )

        return RunResponse(
            status="success",
            message=f"Generated {len(forecasts)} forecasts",
            summary=ForecastSummary(
                total_forecasts=len(forecasts),
                stores=int(forecasts["store_id"].nunique()),
                skus=int(forecasts["sku_id"].nunique()),
                forecast_date=str(forecasts["forecast_date"].iloc[0]) if "forecast_date" in forecasts.columns else None,
            ),
        )
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Forecasting dependencies not available: {e}")
    except Exception as e:
        logger.exception("Forecast run failed")
        raise HTTPException(status_code=500, detail=str(e))
