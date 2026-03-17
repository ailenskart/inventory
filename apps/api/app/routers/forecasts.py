"""Forecast API endpoints."""

from datetime import date

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()


class ForecastRequest(BaseModel):
    store_ids: list[str] | None = None
    sku_ids: list[str] | None = None
    horizon_weeks: int = 4
    start_date: date | None = None


class ForecastResponse(BaseModel):
    store_id: str
    sku_id: str
    week: str
    forecast_qty: float
    lower_bound: float
    upper_bound: float
    model_version: str


@router.post("/generate", response_model=list[ForecastResponse])
def generate_forecasts(request: ForecastRequest):
    """Generate demand forecasts at SKU x Store x Week granularity."""
    # TODO: Wire to ml/forecasting pipeline
    return [
        ForecastResponse(
            store_id="STORE_001",
            sku_id="SKU_001",
            week="2024-W01",
            forecast_qty=12.5,
            lower_bound=8.0,
            upper_bound=17.0,
            model_version="baseline-v0.1",
        )
    ]


@router.get("/latest")
def get_latest_forecasts(
    store_id: str | None = Query(None),
    sku_id: str | None = Query(None),
    limit: int = Query(100, le=1000),
):
    """Retrieve latest stored forecasts."""
    # TODO: Query from forecast results table
    return {"forecasts": [], "count": 0}
