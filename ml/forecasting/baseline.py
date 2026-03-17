"""Baseline demand forecasting using StatsForecast.

Forecasts at SKU x Store x Week granularity.
Supports both display demand (trials) and physical sell-through.
"""

import pandas as pd
from statsforecast import StatsForecast
from statsforecast.models import AutoETS, CrostonOptimized, SeasonalNaive


def prepare_forecast_input(weekly_sales: pd.DataFrame) -> pd.DataFrame:
    """Prepare data in StatsForecast format: unique_id, ds, y."""
    df = weekly_sales.copy()
    df["unique_id"] = df["store_id"] + "_" + df["sku_id"]
    df = df.rename(columns={"week_start": "ds", "total_qty_sold": "y"})
    df["ds"] = pd.to_datetime(df["ds"])
    return df[["unique_id", "ds", "y"]].sort_values(["unique_id", "ds"])


def run_baseline_forecast(df: pd.DataFrame, horizon: int = 4) -> pd.DataFrame:
    """Run baseline forecast with multiple models.

    Uses:
    - SeasonalNaive as benchmark
    - AutoETS for smooth demand patterns
    - CrostonOptimized for intermittent demand (common in eyewear retail)
    """
    models = [
        SeasonalNaive(season_length=52),
        AutoETS(season_length=52),
        CrostonOptimized(),
    ]

    sf = StatsForecast(models=models, freq="W", n_jobs=-1)
    forecasts = sf.forecast(df=df, h=horizon)
    return forecasts.reset_index()


def select_best_model(forecasts: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    """Select best model per series based on historical accuracy.

    TODO: Implement cross-validation and model selection logic.
    For now, defaults to AutoETS.
    """
    if "AutoETS" in forecasts.columns:
        forecasts["selected_forecast"] = forecasts["AutoETS"]
        forecasts["selected_model"] = "AutoETS"
    return forecasts
