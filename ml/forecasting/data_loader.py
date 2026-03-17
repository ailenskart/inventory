"""Data loaders for the forecasting pipeline.

Reads from DuckDB mart tables and prepares data for StatsForecast.
Handles stockout censoring and display-dummy vs physical-sell split.
"""

import logging

import duckdb
import pandas as pd

from ml.forecasting.config import ForecastConfig

logger = logging.getLogger(__name__)


def load_demand_data(config: ForecastConfig) -> pd.DataFrame:
    """Load weekly demand data from mart_demand_base.

    Returns DataFrame with columns needed for forecasting:
    store_id, sku_id, week_start, target, and dimensional attributes.
    """
    con = duckdb.connect(config.db_path, read_only=True)
    query = f"""
        select
            store_id,
            sku_id,
            week_start,
            {config.target_column} as y,
            sell_through_signal,
            prescription_order_signal,
            display_interest_signal,
            total_revenue,
            had_stockout,
            avg_daily_footfall,
            active_days,
            -- Dimensions
            region,
            store_cluster,
            store_type,
            store_format,
            category,
            subcategory,
            sku_type,
            fulfillment_type,
            brand,
            lifecycle_stage,
            is_display_only,
            mrp,
            -- Calendar
            month,
            quarter,
            is_festive,
            season
        from {config.demand_table}
        order by store_id, sku_id, week_start
    """  # noqa: S608
    df = con.execute(query).fetchdf()
    con.close()

    df["week_start"] = pd.to_datetime(df["week_start"])
    logger.info(f"Loaded {len(df)} rows from {config.demand_table} "
                f"({df['store_id'].nunique()} stores, {df['sku_id'].nunique()} SKUs)")
    return df


def load_inventory_data(config: ForecastConfig) -> pd.DataFrame:
    """Load current inventory position for context."""
    con = duckdb.connect(config.db_path, read_only=True)
    query = f"""
        select
            store_id, sku_id,
            on_hand_qty, available_qty,
            avg_weekly_demand, weeks_of_supply,
            inventory_status, is_stockout,
            category, sku_type, vendor_id
        from {config.inventory_table}
    """  # noqa: S608
    df = con.execute(query).fetchdf()
    con.close()
    logger.info(f"Loaded {len(df)} inventory positions")
    return df


def apply_stockout_censoring(df: pd.DataFrame, config: ForecastConfig) -> pd.DataFrame:
    """Impute demand during stockout periods.

    When had_stockout=1, actual sales understate true demand.
    We impute using the non-stockout mean/median for each series.
    """
    if not config.censor_stockout_demand:
        return df

    df = df.copy()
    stockout_mask = df["had_stockout"] == 1
    n_censored = stockout_mask.sum()

    if n_censored == 0:
        return df

    # Compute replacement values per series
    non_stockout = df[~stockout_mask].groupby(["store_id", "sku_id"])["y"]

    if config.stockout_imputation_method == "mean":
        fill_values = non_stockout.mean()
    elif config.stockout_imputation_method == "median":
        fill_values = non_stockout.median()
    elif config.stockout_imputation_method == "max":
        fill_values = non_stockout.max()
    else:
        fill_values = non_stockout.mean()

    fill_values = fill_values.rename("y_fill")

    # Merge and replace
    df = df.merge(fill_values, on=["store_id", "sku_id"], how="left")
    df.loc[stockout_mask & df["y_fill"].notna(), "y"] = df.loc[
        stockout_mask & df["y_fill"].notna(), "y_fill"
    ]
    df = df.drop(columns=["y_fill"])

    logger.info(f"Censored {n_censored} stockout weeks "
                f"using {config.stockout_imputation_method} imputation")
    return df


def prepare_statsforecast_df(
    df: pd.DataFrame,
    config: ForecastConfig,
) -> pd.DataFrame:
    """Prepare data in StatsForecast format: unique_id, ds, y.

    Filters to series with enough history.
    """
    df = df.copy()
    df["unique_id"] = df["store_id"] + "__" + df["sku_id"]
    df = df.rename(columns={"week_start": "ds"})

    # Filter series with minimum history
    series_lengths = df.groupby("unique_id")["ds"].count()
    valid_series = series_lengths[series_lengths >= config.min_history_weeks].index
    df = df[df["unique_id"].isin(valid_series)]

    logger.info(f"Prepared {df['unique_id'].nunique()} series "
                f"(filtered from {series_lengths.shape[0]}, "
                f"min history={config.min_history_weeks} weeks)")

    return df[["unique_id", "ds", "y"]].sort_values(["unique_id", "ds"]).reset_index(drop=True)


def prepare_hierarchy_df(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """Prepare hierarchical structure for HierarchicalForecast.

    Returns:
        tags: dict mapping each hierarchy level to unique_id components
        S: summing matrix specification
    """
    df = df.copy()

    # Build hierarchy tags from the dimensional attributes
    # Bottom level: store_id / sku_id
    # Aggregation levels: region, store_cluster, category
    tags = {}

    # Bottom-level unique_id
    df["unique_id"] = df["store_id"] + "__" + df["sku_id"]

    # Build tags for each level
    bottom = df[["unique_id", "region", "store_cluster", "store_id", "category", "sku_id"]].drop_duplicates()
    tags["region"] = bottom.groupby("region")["unique_id"].apply(list).to_dict()
    tags["store_cluster"] = bottom.groupby(["region", "store_cluster"])["unique_id"].apply(list).to_dict()
    tags["category"] = bottom.groupby(["region", "store_cluster", "store_id", "category"])[
        "unique_id"
    ].apply(list).to_dict()

    return df, tags
