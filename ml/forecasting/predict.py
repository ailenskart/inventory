"""Batch inference pipeline for demand forecasting.

Generates forecasts for all active SKU × Store combinations and writes
results back to DuckDB for downstream consumption.

Usage:
    python -m ml.forecasting.predict
    python -m ml.forecasting.predict --horizon 8 --output data/forecasts.csv
"""

import argparse
import logging
import os
import sys
from datetime import datetime

import duckdb
import pandas as pd

from ml.forecasting.baseline import (
    create_ensemble_forecast,
    fit_and_forecast_with_quantiles,
    get_production_models,
)
from ml.forecasting.config import ForecastConfig
from ml.forecasting.data_loader import (
    apply_stockout_censoring,
    load_demand_data,
    prepare_statsforecast_df,
)

logger = logging.getLogger(__name__)


def run_inference_pipeline(
    config: ForecastConfig,
    output_path: str | None = None,
    write_to_db: bool = True,
) -> pd.DataFrame:
    """Run batch inference and return forecast DataFrame.

    Args:
        config: Forecast configuration
        output_path: Optional CSV output path
        write_to_db: Whether to write results back to DuckDB

    Returns:
        DataFrame with columns:
        - store_id, sku_id, forecast_week
        - point_forecast, lower_bound, upper_bound
        - model_used, forecast_date, reason_code
    """
    logger.info("=" * 60)
    logger.info("Demand Intelligence Engine v1 — Batch Inference")
    logger.info("=" * 60)

    # Load and prepare data
    demand_df = load_demand_data(config)
    if demand_df.empty:
        logger.error("No demand data found")
        return pd.DataFrame()

    demand_df = apply_stockout_censoring(demand_df, config)
    sf_df = prepare_statsforecast_df(demand_df, config)

    if sf_df.empty:
        logger.error("No valid series for forecasting")
        return pd.DataFrame()

    # Generate forecasts
    models = get_production_models(config)
    forecasts = fit_and_forecast_with_quantiles(sf_df, config, models)
    forecasts = create_ensemble_forecast(forecasts)

    # Format output
    output = _format_forecast_output(forecasts, demand_df, config)

    # Write outputs
    if output_path:
        output.to_csv(output_path, index=False)
        logger.info(f"Forecasts written to {output_path}")

    if write_to_db:
        _write_forecasts_to_db(output, config)

    logger.info(f"Inference complete: {len(output)} forecast rows for "
                f"{output['store_id'].nunique()} stores, "
                f"{output['sku_id'].nunique()} SKUs")
    return output


def _format_forecast_output(
    forecasts: pd.DataFrame,
    demand_df: pd.DataFrame,
    config: ForecastConfig,
) -> pd.DataFrame:
    """Format raw StatsForecast output into standard forecast table."""
    df = forecasts.copy()

    # Parse unique_id back to store_id + sku_id
    id_split = df["unique_id"].str.split("__", n=1, expand=True)
    df["store_id"] = id_split[0]
    df["sku_id"] = id_split[1]

    # Select best available model for point forecast
    model_cols = [c for c in df.columns
                  if c not in ("unique_id", "ds", "store_id", "sku_id")
                  and not c.startswith("lo-") and not c.startswith("hi-")]

    # Prefer Ensemble, then AutoETS, then first available
    point_col = "Ensemble"
    if point_col not in df.columns:
        for fallback in ["AutoETS", "SeasonalNaive", "CrostonOptimized"]:
            if fallback in df.columns:
                point_col = fallback
                break
        else:
            point_col = model_cols[0] if model_cols else None

    if point_col is None:
        logger.error("No model columns found in forecasts")
        return pd.DataFrame()

    # Find confidence interval columns
    lo_cols = [c for c in df.columns if c.startswith("lo-")]
    hi_cols = [c for c in df.columns if c.startswith("hi-")]

    output = pd.DataFrame({
        "store_id": df["store_id"],
        "sku_id": df["sku_id"],
        "forecast_week": df["ds"],
        "point_forecast": df[point_col].clip(lower=0).round(1),
        "lower_bound": df[lo_cols[0]].clip(lower=0).round(1) if lo_cols else (df[point_col] * 0.7).clip(lower=0).round(1),
        "upper_bound": df[hi_cols[0]].clip(lower=0).round(1) if hi_cols else (df[point_col] * 1.3).clip(lower=0).round(1),
        "model_used": point_col,
        "forecast_date": datetime.now().date(),
        "model_version": "v1.0",
    })

    # Add SKU context
    sku_map = demand_df[["store_id", "sku_id", "sku_type", "category",
                          "fulfillment_type", "is_display_only"]].drop_duplicates()
    output = output.merge(sku_map, on=["store_id", "sku_id"], how="left")

    # Reason codes
    output["reason_code"] = "standard_forecast"
    if "is_display_only" in output.columns:
        output.loc[output["is_display_only"] == 1, "reason_code"] = "display_only_trial_demand"

    return output


def _write_forecasts_to_db(forecasts: pd.DataFrame, config: ForecastConfig):
    """Write forecasts to DuckDB for downstream consumption."""
    con = duckdb.connect(config.db_path)

    # Create schema if needed
    con.execute("CREATE SCHEMA IF NOT EXISTS main_ml")

    # Create or replace forecasts table
    con.execute("DROP TABLE IF EXISTS main_ml.demand_forecasts")
    con.execute("""
        CREATE TABLE main_ml.demand_forecasts AS
        SELECT * FROM forecasts
    """)

    count = con.execute("SELECT count(*) FROM main_ml.demand_forecasts").fetchone()[0]
    con.close()

    logger.info(f"Written {count} forecasts to main_ml.demand_forecasts")


def main():
    parser = argparse.ArgumentParser(description="Run batch demand forecast inference")
    parser.add_argument("--db-path", default="data/dev.duckdb")
    parser.add_argument("--horizon", type=int, default=4)
    parser.add_argument("--target", default="total_qty_sold")
    parser.add_argument("--output", type=str, default=None, help="CSV output path")
    parser.add_argument("--no-db-write", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = ForecastConfig(
        db_path=args.db_path,
        horizon_weeks=args.horizon,
        target_column=args.target,
    )

    result = run_inference_pipeline(
        config,
        output_path=args.output,
        write_to_db=not args.no_db_write,
    )

    if result.empty:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
