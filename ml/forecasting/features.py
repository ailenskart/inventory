"""Feature generation for demand forecasting.

Creates lagged, rolling, and contextual features from mart_demand_base.
Features are designed for both statistical models (which use internal lags)
and future ML models (LightGBM, TFT) that need explicit feature columns.
"""

import logging

import numpy as np
import pandas as pd

from ml.forecasting.config import ForecastConfig

logger = logging.getLogger(__name__)


def generate_lag_features(df: pd.DataFrame, config: ForecastConfig) -> pd.DataFrame:
    """Create lagged demand features per series."""
    df = df.sort_values(["store_id", "sku_id", "week_start"]).copy()
    group = df.groupby(["store_id", "sku_id"])

    for lag in config.lag_weeks:
        df[f"lag_{lag}w"] = group["y"].shift(lag)

    logger.info(f"Generated {len(config.lag_weeks)} lag features")
    return df


def generate_rolling_features(df: pd.DataFrame, config: ForecastConfig) -> pd.DataFrame:
    """Create rolling window statistics per series."""
    df = df.sort_values(["store_id", "sku_id", "week_start"]).copy()
    group = df.groupby(["store_id", "sku_id"])["y"]

    for window in config.rolling_windows:
        df[f"rolling_mean_{window}w"] = group.transform(
            lambda x: x.shift(1).rolling(window, min_periods=1).mean()
        )
        df[f"rolling_std_{window}w"] = group.transform(
            lambda x: x.shift(1).rolling(window, min_periods=1).std()
        )
        df[f"rolling_max_{window}w"] = group.transform(
            lambda x: x.shift(1).rolling(window, min_periods=1).max()
        )
        df[f"rolling_min_{window}w"] = group.transform(
            lambda x: x.shift(1).rolling(window, min_periods=1).min()
        )

    logger.info(f"Generated rolling features for windows {config.rolling_windows}")
    return df


def generate_demand_signal_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create features from the three demand signal types."""
    df = df.copy()
    group = df.groupby(["store_id", "sku_id"])

    # Lagged signal features
    for signal in ["sell_through_signal", "prescription_order_signal", "display_interest_signal"]:
        if signal in df.columns:
            df[f"{signal}_lag1"] = group[signal].shift(1)
            df[f"{signal}_lag4"] = group[signal].shift(4)
            df[f"{signal}_rolling4w"] = group[signal].transform(
                lambda x: x.shift(1).rolling(4, min_periods=1).mean()
            )

    # Trial conversion rate trend
    if "display_interest_signal" in df.columns and "prescription_order_signal" in df.columns:
        df["trial_conversion_rate"] = np.where(
            df["display_interest_signal"] > 0,
            df["prescription_order_signal"] / df["display_interest_signal"],
            0,
        )

    return df


def generate_stockout_features(df: pd.DataFrame) -> pd.DataFrame:
    """Features related to stockout history."""
    df = df.copy()
    group = df.groupby(["store_id", "sku_id"])

    if "had_stockout" in df.columns:
        df["stockout_lag1"] = group["had_stockout"].shift(1)
        df["stockout_rolling4w"] = group["had_stockout"].transform(
            lambda x: x.shift(1).rolling(4, min_periods=1).mean()
        )
        df["stockout_rolling12w"] = group["had_stockout"].transform(
            lambda x: x.shift(1).rolling(12, min_periods=1).mean()
        )

    return df


def generate_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Calendar and seasonality features."""
    df = df.copy()

    if "week_start" in df.columns:
        df["week_of_year"] = df["week_start"].dt.isocalendar().week.astype(int)
        df["month"] = df["week_start"].dt.month
        df["quarter"] = df["week_start"].dt.quarter

    # Encode cyclical features
    if "week_of_year" in df.columns:
        df["week_sin"] = np.sin(2 * np.pi * df["week_of_year"] / 52)
        df["week_cos"] = np.cos(2 * np.pi * df["week_of_year"] / 52)
        df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
        df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

    # Festive flag (already in mart)
    if "is_festive" in df.columns:
        df["is_festive"] = df["is_festive"].fillna(0).astype(int)

    return df


def generate_product_features(df: pd.DataFrame) -> pd.DataFrame:
    """Static product attribute features."""
    df = df.copy()

    # One-hot encode key categorical features
    categorical_cols = ["sku_type", "fulfillment_type", "category", "lifecycle_stage"]
    for col in categorical_cols:
        if col in df.columns:
            dummies = pd.get_dummies(df[col], prefix=col, drop_first=True)
            df = pd.concat([df, dummies], axis=1)

    # Store cluster encoding
    if "store_cluster" in df.columns:
        cluster_order = ["KIOSK", "TIER2", "TIER1_MID", "TIER1_HIGH", "METRO_MID", "METRO_HIGH"]
        df["store_cluster_ordinal"] = df["store_cluster"].map(
            {c: i for i, c in enumerate(cluster_order)}
        ).fillna(-1).astype(int)

    # Price tier
    if "mrp" in df.columns:
        try:
            df["price_tier"] = pd.qcut(df["mrp"], q=4, labels=False, duplicates="drop")
        except ValueError:
            df["price_tier"] = 0

    return df


def generate_all_features(df: pd.DataFrame, config: ForecastConfig) -> pd.DataFrame:
    """Run the full feature generation pipeline.

    Args:
        df: Raw demand data from mart_demand_base
        config: Forecast configuration

    Returns:
        DataFrame with all features added
    """
    df = df.copy()

    # Rename target
    if config.target_column in df.columns and "y" not in df.columns:
        df = df.rename(columns={config.target_column: "y"})

    df = generate_lag_features(df, config)
    df = generate_rolling_features(df, config)
    df = generate_demand_signal_features(df)
    df = generate_stockout_features(df)
    df = generate_calendar_features(df)
    df = generate_product_features(df)

    # Fill NaN from lags with 0 (beginning of series)
    lag_cols = [c for c in df.columns if c.startswith("lag_") or c.startswith("rolling_")]
    df[lag_cols] = df[lag_cols].fillna(0)

    logger.info(f"Generated {len(df.columns)} total columns")
    return df
