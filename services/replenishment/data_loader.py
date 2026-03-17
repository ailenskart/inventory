"""Data loading for the replenishment engine.

Reads from DuckDB:
- Demand forecasts (from ml.demand_forecasts)
- Current inventory positions (from mart_inventory_position)
- Vendor lead times and constraints
- Store capacity constraints

Merges into a single positions DataFrame for the engine.
"""

import logging

import duckdb
import pandas as pd

from services.replenishment.config import ReplenishmentConfig

logger = logging.getLogger(__name__)


def load_inventory_positions(config: ReplenishmentConfig) -> pd.DataFrame:
    """Load current inventory positions from mart_inventory_position."""
    con = duckdb.connect(config.db_path, read_only=True)
    query = f"""
        select
            store_id,
            sku_id,
            on_hand_qty,
            on_display_qty,
            in_storage_qty,
            in_transit_qty,
            available_qty,
            is_stockout,
            avg_weekly_demand,
            total_8wk_demand,
            weeks_of_supply,
            inventory_status,
            last_receipt_date,
            store_cluster,
            store_format,
            region,
            category,
            sku_type,
            fulfillment_type,
            lifecycle_stage,
            is_display_only,
            vendor_id
        from {config.inventory_table}
    """  # noqa: S608
    df = con.execute(query).fetchdf()
    con.close()

    logger.info(f"Loaded {len(df)} inventory positions "
                f"({df['store_id'].nunique()} stores, {df['sku_id'].nunique()} SKUs)")
    return df


def load_forecasts(config: ReplenishmentConfig) -> pd.DataFrame:
    """Load demand forecasts from ml.demand_forecasts.

    Aggregates to a single forecast per store × sku (sum over horizon).
    """
    con = duckdb.connect(config.db_path, read_only=True)

    # Check if forecast table exists
    try:
        con.execute(f"select 1 from {config.forecast_table} limit 1")  # noqa: S608
    except Exception:
        con.close()
        logger.warning(f"Forecast table {config.forecast_table} not found")
        return pd.DataFrame()

    # Get per-week forecasts and aggregate stats
    query = f"""
        select
            store_id,
            sku_id,
            avg(point_forecast) as point_forecast,
            avg(lower_bound) as lower_bound,
            avg(upper_bound) as upper_bound,
            stddev(point_forecast) as demand_std_weekly,
            count(*) as forecast_weeks
        from {config.forecast_table}
        group by store_id, sku_id
    """  # noqa: S608
    df = con.execute(query).fetchdf()
    con.close()

    # Fill missing std
    df["demand_std_weekly"] = df["demand_std_weekly"].fillna(0)

    logger.info(f"Loaded forecasts for {len(df)} store-SKU combinations")
    return df


def load_vendor_constraints(config: ReplenishmentConfig) -> pd.DataFrame:
    """Load vendor lead times and MOQ constraints."""
    con = duckdb.connect(config.db_path, read_only=True)
    query = """
        select
            vendor_id,
            avg_lead_time_days as lead_time_days,
            min_order_qty as moq,
            min_order_value as mov,
            reliability_score
        from main_dimensions.dim_vendor
    """
    df = con.execute(query).fetchdf()
    con.close()

    logger.info(f"Loaded constraints for {len(df)} vendors")
    return df


def load_store_capacities(config: ReplenishmentConfig) -> pd.DataFrame:
    """Load store capacity info."""
    con = duckdb.connect(config.db_path, read_only=True)
    query = """
        select
            store_id,
            store_format,
            store_cluster,
            display_capacity,
            storage_capacity,
            display_capacity + storage_capacity as total_capacity
        from main_dimensions.dim_store
    """
    df = con.execute(query).fetchdf()
    con.close()

    logger.info(f"Loaded capacities for {len(df)} stores")
    return df


def load_current_store_units(config: ReplenishmentConfig) -> pd.DataFrame:
    """Load total units currently held per store (for capacity check)."""
    con = duckdb.connect(config.db_path, read_only=True)
    query = f"""
        select
            store_id,
            sum(on_hand_qty) as current_store_units
        from {config.inventory_table}
        group by store_id
    """  # noqa: S608
    df = con.execute(query).fetchdf()
    con.close()
    return df


def build_replenishment_positions(config: ReplenishmentConfig) -> pd.DataFrame:
    """Build the full positions DataFrame by merging all data sources.

    Returns a single DataFrame with all inputs needed by the engine.
    """
    # Load all sources
    inventory = load_inventory_positions(config)
    forecasts = load_forecasts(config)
    vendors = load_vendor_constraints(config)
    capacities = load_store_capacities(config)
    store_units = load_current_store_units(config)

    if inventory.empty:
        logger.warning("No inventory positions found")
        return pd.DataFrame()

    # Start with inventory
    positions = inventory.copy()

    # Merge forecasts (left join — not all items may have forecasts)
    if not forecasts.empty:
        positions = positions.merge(
            forecasts[["store_id", "sku_id", "point_forecast", "upper_bound", "demand_std_weekly"]],
            on=["store_id", "sku_id"],
            how="left",
        )
    else:
        positions["point_forecast"] = positions["avg_weekly_demand"]
        positions["upper_bound"] = positions["avg_weekly_demand"] * 1.3
        positions["demand_std_weekly"] = 0.0

    # Fill missing forecasts with historical avg
    positions["point_forecast"] = positions["point_forecast"].fillna(positions["avg_weekly_demand"])
    positions["upper_bound"] = positions["upper_bound"].fillna(positions["point_forecast"] * 1.3)
    positions["demand_std_weekly"] = positions["demand_std_weekly"].fillna(0)

    # Merge vendor constraints
    if not vendors.empty:
        positions = positions.merge(
            vendors[["vendor_id", "lead_time_days", "moq"]],
            on="vendor_id",
            how="left",
        )
    else:
        positions["lead_time_days"] = config.default_lead_time_days
        positions["moq"] = config.default_moq

    positions["lead_time_days"] = positions["lead_time_days"].fillna(config.default_lead_time_days)
    positions["moq"] = positions["moq"].fillna(config.default_moq).astype(int)
    positions["case_pack"] = config.default_case_pack

    # Merge store capacities
    if not capacities.empty:
        positions = positions.merge(
            capacities[["store_id", "total_capacity"]].rename(columns={"total_capacity": "store_capacity"}),
            on="store_id",
            how="left",
        )
    else:
        positions["store_capacity"] = float("inf")

    positions["store_capacity"] = positions["store_capacity"].fillna(float("inf"))

    # Merge current store units
    if not store_units.empty:
        positions = positions.merge(store_units, on="store_id", how="left")
    else:
        positions["current_store_units"] = positions["on_hand_qty"]

    positions["current_store_units"] = positions["current_store_units"].fillna(0)

    # Add MRP for lost-sales calculation
    positions["mrp"] = positions.get("mrp", pd.Series(0, index=positions.index))

    logger.info(f"Built {len(positions)} replenishment positions")
    return positions


def write_recommendations_to_db(
    recommendations: pd.DataFrame,
    config: ReplenishmentConfig,
):
    """Write replenishment recommendations to DuckDB."""
    if recommendations.empty:
        logger.info("No recommendations to write")
        return

    con = duckdb.connect(config.db_path)
    con.execute("CREATE SCHEMA IF NOT EXISTS main_ml")
    con.execute(f"DROP TABLE IF EXISTS {config.output_table}")  # noqa: S608
    con.execute(f"""
        CREATE TABLE {config.output_table} AS
        SELECT * FROM recommendations
    """)  # noqa: S608

    count = con.execute(f"SELECT count(*) FROM {config.output_table}").fetchone()[0]  # noqa: S608
    con.close()

    logger.info(f"Written {count} recommendations to {config.output_table}")
