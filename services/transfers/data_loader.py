"""Data loading for the inter-store transfer optimizer.

Reads from DuckDB:
- Current inventory positions (mart_inventory_position)
- Demand forecasts (ml.demand_forecasts)
- Store capacities and metadata (dim_store)

Merges into source/destination candidate DataFrames for the engine.
"""

import logging

import duckdb
import pandas as pd

from services.transfers.config import TransferConfig

logger = logging.getLogger(__name__)


def load_inventory_with_demand(config: TransferConfig) -> pd.DataFrame:
    """Load inventory positions enriched with demand data."""
    con = duckdb.connect(config.db_path, read_only=True)
    query = f"""
        select
            store_id,
            sku_id,
            on_hand_qty,
            available_qty,
            in_transit_qty,
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
            is_display_only
        from {config.inventory_table}
        where sku_type in ({','.join(f"'{t}'" for t in config.eligible_sku_types)})
          and is_display_only = 0
    """  # noqa: S608
    df = con.execute(query).fetchdf()
    con.close()

    logger.info(
        f"Loaded {len(df)} eligible positions "
        f"({df['store_id'].nunique()} stores, {df['sku_id'].nunique()} SKUs)"
    )
    return df


def load_forecasts(config: TransferConfig) -> pd.DataFrame:
    """Load demand forecasts aggregated per store x SKU."""
    con = duckdb.connect(config.db_path, read_only=True)
    try:
        con.execute(f"select 1 from {config.forecast_table} limit 1")  # noqa: S608
    except Exception:
        con.close()
        logger.warning(f"Forecast table {config.forecast_table} not found")
        return pd.DataFrame()

    query = f"""
        select
            store_id,
            sku_id,
            avg(point_forecast) as forecast_weekly,
            sum(point_forecast) as forecast_total
        from {config.forecast_table}
        group by store_id, sku_id
    """  # noqa: S608
    df = con.execute(query).fetchdf()
    con.close()
    logger.info(f"Loaded forecasts for {len(df)} store-SKU pairs")
    return df


def load_store_metadata(config: TransferConfig) -> pd.DataFrame:
    """Load store capacity and region info."""
    con = duckdb.connect(config.db_path, read_only=True)
    query = """
        select
            store_id,
            store_format,
            store_cluster,
            region,
            display_capacity,
            storage_capacity,
            display_capacity + storage_capacity as total_capacity
        from main_dimensions.dim_store
    """
    df = con.execute(query).fetchdf()
    con.close()
    logger.info(f"Loaded metadata for {len(df)} stores")
    return df


def load_current_store_units(config: TransferConfig) -> pd.DataFrame:
    """Load total units per store for capacity checks."""
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


def build_transfer_inputs(config: TransferConfig) -> pd.DataFrame:
    """Build the enriched positions DataFrame for transfer optimization.

    Merges inventory, forecasts, and store metadata into a single frame.
    """
    inventory = load_inventory_with_demand(config)
    if inventory.empty:
        logger.warning("No eligible inventory positions found")
        return pd.DataFrame()

    forecasts = load_forecasts(config)
    stores = load_store_metadata(config)
    store_units = load_current_store_units(config)

    positions = inventory.copy()

    # Merge forecasts
    if not forecasts.empty:
        positions = positions.merge(
            forecasts[["store_id", "sku_id", "forecast_weekly"]],
            on=["store_id", "sku_id"],
            how="left",
        )
    else:
        positions["forecast_weekly"] = positions["avg_weekly_demand"]

    positions["forecast_weekly"] = positions["forecast_weekly"].fillna(
        positions["avg_weekly_demand"]
    )

    # Merge store metadata (capacity, region)
    if not stores.empty:
        # Only merge columns not already in positions
        store_cols = ["store_id", "total_capacity"]
        if "region" not in positions.columns:
            store_cols.append("region")
        positions = positions.merge(
            stores[store_cols],
            on="store_id",
            how="left",
        )
    else:
        if "total_capacity" not in positions.columns:
            positions["total_capacity"] = float("inf")

    positions["total_capacity"] = positions["total_capacity"].fillna(float("inf"))

    # Merge current store units
    if not store_units.empty:
        positions = positions.merge(store_units, on="store_id", how="left")
    else:
        positions["current_store_units"] = positions["on_hand_qty"]

    positions["current_store_units"] = positions["current_store_units"].fillna(0)

    logger.info(f"Built {len(positions)} transfer input positions")
    return positions


def write_transfer_recommendations(
    recommendations: pd.DataFrame,
    config: TransferConfig,
):
    """Write transfer recommendations to DuckDB."""
    if recommendations.empty:
        logger.info("No transfer recommendations to write")
        return

    con = duckdb.connect(config.db_path)
    con.execute("CREATE SCHEMA IF NOT EXISTS main_ml")
    con.execute(f"DROP TABLE IF EXISTS {config.output_table}")  # noqa: S608
    con.execute(f"""
        CREATE TABLE {config.output_table} AS
        SELECT * FROM recommendations
    """)  # noqa: S608

    count = con.execute(
        f"SELECT count(*) FROM {config.output_table}"  # noqa: S608
    ).fetchone()[0]
    con.close()

    logger.info(f"Written {count} transfer recommendations to {config.output_table}")
