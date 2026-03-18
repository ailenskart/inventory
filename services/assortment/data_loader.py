"""Data loading for assortment optimization.

Loads and merges:
- SKU attributes from dim_sku
- Store attributes from dim_store
- Demand signals from mart_demand_base (recent performance)
- Inventory positions from mart_inventory_position
- Forecast outputs from ml.demand_forecasts (if available)
"""

import logging

import duckdb
import pandas as pd

from services.assortment.config import AssortmentConfig

logger = logging.getLogger(__name__)


def load_sku_catalog(config: AssortmentConfig) -> pd.DataFrame:
    """Load full SKU catalog with attributes."""
    con = duckdb.connect(config.db_path, read_only=True)
    df = con.execute("""
        select
            sku_id, product_name, brand, category, subcategory,
            sku_type, gender, frame_type, frame_shape, frame_material,
            mrp, cost_price, fulfillment_type, sales_channel,
            is_display_only, lifecycle_stage, vendor_id,
            lead_time_days, unit_margin, margin_pct
        from main_dimensions.dim_sku
    """).fetchdf()
    con.close()
    logger.info(f"Loaded {len(df)} SKUs from catalog")
    return df


def load_store_profiles(config: AssortmentConfig) -> pd.DataFrame:
    """Load store profiles with capacity."""
    con = duckdb.connect(config.db_path, read_only=True)
    df = con.execute("""
        select
            store_id, store_name, city, region,
            store_type, store_format, store_cluster,
            display_capacity, storage_capacity, is_active
        from main_dimensions.dim_store
        where is_active = true
    """).fetchdf()
    con.close()
    logger.info(f"Loaded {len(df)} active stores")
    return df


def load_recent_demand(config: AssortmentConfig) -> pd.DataFrame:
    """Load recent demand signals aggregated over planning horizon."""
    con = duckdb.connect(config.db_path, read_only=True)
    weeks = config.planning_horizon_weeks
    df = con.execute(f"""
        with recent as (
            select
                store_id, sku_id,
                avg(total_qty_sold) as avg_weekly_demand,
                sum(display_interest_signal) as display_interest,
                sum(sell_through_signal) as sell_through_total,
                sum(prescription_order_signal) as prescription_total,
                avg(trial_conversion_rate) as trial_conversion_rate,
                avg(avg_daily_footfall) as avg_footfall,
                max(had_stockout) as had_stockout
            from {config.demand_table}
            where week_start >= (
                select max(week_start) - interval '{weeks * 7} days'
                from {config.demand_table}
            )
            group by store_id, sku_id
        )
        select * from recent
    """).fetchdf()  # noqa: S608
    con.close()
    logger.info(f"Loaded demand for {len(df)} store-SKU combinations")
    return df


def load_current_display(config: AssortmentConfig) -> pd.DataFrame:
    """Load current display assignments (SKUs with on_display_qty > 0)."""
    con = duckdb.connect(config.db_path, read_only=True)
    df = con.execute(f"""
        select
            store_id, sku_id,
            on_display_qty, on_hand_qty,
            inventory_status, weeks_of_supply,
            is_display_only, category, sku_type,
            lifecycle_stage
        from {config.inventory_table}
        where on_display_qty > 0
    """).fetchdf()  # noqa: S608
    con.close()
    logger.info(f"Loaded {len(df)} current display positions")
    return df


def load_forecasts(config: AssortmentConfig) -> pd.DataFrame:
    """Load demand forecasts if available."""
    con = duckdb.connect(config.db_path, read_only=True)
    try:
        con.execute(f"select 1 from {config.forecast_table} limit 1")  # noqa: S608
        df = con.execute(f"""
            select
                store_id, sku_id,
                avg(point_forecast) as forecast_demand,
                avg(upper_bound) as forecast_upper
            from {config.forecast_table}
            group by store_id, sku_id
        """).fetchdf()  # noqa: S608
        con.close()
        logger.info(f"Loaded forecasts for {len(df)} store-SKU pairs")
        return df
    except Exception:
        con.close()
        logger.warning("Forecast table not available")
        return pd.DataFrame()


def build_optimization_input(
    config: AssortmentConfig,
    store_id: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build the full optimization input.

    Returns:
        sku_data: DataFrame with one row per SKU × Store candidate
        store_data: DataFrame with store profiles and capacity
    """
    skus = load_sku_catalog(config)
    stores = load_store_profiles(config)
    demand = load_recent_demand(config)
    forecasts = load_forecasts(config)

    if store_id:
        stores = stores[stores["store_id"] == store_id]

    if stores.empty:
        return pd.DataFrame(), stores

    # Cross join: every SKU is a candidate for every store
    # (filtered by demand data availability)
    if not demand.empty:
        sku_data = demand.merge(
            skus, on="sku_id", how="left", suffixes=("", "_sku"),
        )
    else:
        # No demand data — use catalog + stores cross join
        sku_data = skus.assign(key=1).merge(
            stores[["store_id"]].assign(key=1), on="key"
        ).drop(columns=["key"])
        sku_data["avg_weekly_demand"] = 0.0
        sku_data["display_interest"] = 0
        sku_data["trial_conversion_rate"] = 0.0

    # Merge forecasts
    if not forecasts.empty:
        sku_data = sku_data.merge(
            forecasts, on=["store_id", "sku_id"], how="left",
        )
        # Use forecast as demand if higher (forward-looking)
        if "forecast_demand" in sku_data.columns:
            sku_data["avg_weekly_demand"] = sku_data[
                ["avg_weekly_demand", "forecast_demand"]
            ].max(axis=1)

    # Fill missing values
    sku_data["margin_pct"] = sku_data.get(
        "margin_pct", pd.Series(0.3, index=sku_data.index)
    ).fillna(0.3)
    sku_data["display_interest"] = sku_data.get(
        "display_interest", pd.Series(0, index=sku_data.index)
    ).fillna(0)
    sku_data["trial_conversion_rate"] = sku_data.get(
        "trial_conversion_rate", pd.Series(0, index=sku_data.index)
    ).fillna(0)
    sku_data["is_display_only"] = sku_data.get(
        "is_display_only", pd.Series(False, index=sku_data.index)
    ).fillna(False).astype(int)
    sku_data["lifecycle_stage"] = sku_data.get(
        "lifecycle_stage", pd.Series("active", index=sku_data.index)
    ).fillna("active")

    logger.info(
        f"Built optimization input: {len(sku_data)} candidates, "
        f"{stores['store_id'].nunique()} stores"
    )
    return sku_data, stores
