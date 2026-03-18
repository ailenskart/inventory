"""Rolling forecast sharing for vendors.

Generates 8–12 week rolling forecast visibility by vendor,
aggregated at SKU-family or SKU level. Vendors use this to
plan capacity and raw material procurement.
"""

import logging
from datetime import date, timedelta

import pandas as pd

logger = logging.getLogger(__name__)


def generate_rolling_forecast(
    demand_forecasts: pd.DataFrame,
    sku_vendor_map: pd.DataFrame,
    horizon_weeks: int = 12,
    start_date: date | None = None,
) -> pd.DataFrame:
    """Generate rolling forecast by vendor × SKU for the given horizon.

    Args:
        demand_forecasts: DataFrame with store_id, sku_id, forecast_week, point_forecast.
        sku_vendor_map: DataFrame with sku_id, vendor_id, category, sku_family.
        horizon_weeks: Number of weeks to share (8–12).
        start_date: Start date for forecast window (defaults to today).

    Returns:
        DataFrame with vendor_id, sku_id, sku_family, week_offset, forecast_week,
        total_forecast_qty, store_count.
    """
    if start_date is None:
        start_date = date.today()

    if demand_forecasts.empty or sku_vendor_map.empty:
        return pd.DataFrame()

    # Merge vendor info onto forecasts
    merged = demand_forecasts.merge(
        sku_vendor_map[["sku_id", "vendor_id", "category"]],
        on="sku_id",
        how="inner",
    )

    if merged.empty:
        logger.warning("No matching SKU-vendor pairs in forecast data")
        return pd.DataFrame()

    # Aggregate across stores: total forecast per vendor × sku × week
    grouped = (
        merged.groupby(["vendor_id", "sku_id", "category"])
        .agg(
            total_forecast_qty=("point_forecast", "sum"),
            store_count=("store_id", "nunique"),
            avg_forecast_per_store=("point_forecast", "mean"),
        )
        .reset_index()
    )

    # Add week metadata
    grouped["horizon_weeks"] = horizon_weeks
    grouped["forecast_start_date"] = start_date.isoformat()
    grouped["forecast_end_date"] = (
        start_date + timedelta(weeks=horizon_weeks)
    ).isoformat()

    logger.info(
        f"Generated rolling forecast: {len(grouped)} vendor-SKU lines, "
        f"{grouped['vendor_id'].nunique()} vendors, {horizon_weeks} week horizon"
    )

    return grouped


def build_vendor_forecast_summary(
    rolling_forecast: pd.DataFrame,
) -> list[dict]:
    """Summarize rolling forecast per vendor for vendor portal.

    Returns list of vendor summaries with total units, SKU count, etc.
    """
    if rolling_forecast.empty:
        return []

    summary = (
        rolling_forecast.groupby("vendor_id")
        .agg(
            total_forecast_units=("total_forecast_qty", "sum"),
            sku_count=("sku_id", "nunique"),
            category_count=("category", "nunique"),
            avg_per_sku=("total_forecast_qty", "mean"),
        )
        .reset_index()
    )

    result = []
    for _, row in summary.iterrows():
        result.append({
            "vendor_id": row["vendor_id"],
            "total_forecast_units": round(float(row["total_forecast_units"]), 0),
            "sku_count": int(row["sku_count"]),
            "category_count": int(row["category_count"]),
            "avg_forecast_per_sku": round(float(row["avg_per_sku"]), 1),
        })

    return result
