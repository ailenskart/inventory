"""Lifecycle feature engineering.

Computes the feature set needed for lifecycle classification:
- age since launch
- sales velocity trend
- trial trend
- conversion trend
- aging inventory percentage
- markdown history
"""

import logging
from datetime import date

import numpy as np
import pandas as pd

from services.lifecycle.config import LifecycleConfig

logger = logging.getLogger(__name__)


def compute_lifecycle_features(
    sku_sales: pd.DataFrame,
    sku_trials: pd.DataFrame,
    sku_inventory: pd.DataFrame,
    sku_master: pd.DataFrame,
    config: LifecycleConfig,
    as_of_date: date | None = None,
) -> pd.DataFrame:
    """Compute lifecycle features for all SKUs.

    Args:
        sku_sales: Daily sales data with columns [sku_id, sale_date, qty_sold].
        sku_trials: Trial data with columns [sku_id, trial_date, resulted_in_order].
        sku_inventory: Inventory data with columns [sku_id, on_hand_qty, snapshot_date].
        sku_master: SKU master with columns [sku_id, launch_date].
        config: Lifecycle configuration.
        as_of_date: Reference date (defaults to today).

    Returns:
        DataFrame with one row per SKU and all lifecycle features.
    """
    if as_of_date is None:
        as_of_date = date.today()

    if sku_sales.empty:
        logger.warning("No sales data provided for lifecycle features")
        return pd.DataFrame()

    features = []
    sku_ids = sku_master["sku_id"].unique() if not sku_master.empty else sku_sales["sku_id"].unique()

    for sku_id in sku_ids:
        feat = _compute_single_sku_features(
            sku_id, sku_sales, sku_trials, sku_inventory,
            sku_master, config, as_of_date,
        )
        if feat is not None:
            features.append(feat)

    if not features:
        return pd.DataFrame()

    return pd.DataFrame(features)


def _compute_single_sku_features(
    sku_id: str,
    sku_sales: pd.DataFrame,
    sku_trials: pd.DataFrame,
    sku_inventory: pd.DataFrame,
    sku_master: pd.DataFrame,
    config: LifecycleConfig,
    as_of_date: date,
) -> dict | None:
    """Compute lifecycle features for a single SKU."""
    # ── Age since launch ────────────────────────────────────────────────
    sku_row = sku_master[sku_master["sku_id"] == sku_id]
    if not sku_row.empty and "launch_date" in sku_row.columns:
        launch_date = pd.to_datetime(sku_row.iloc[0]["launch_date"]).date()
    else:
        # Estimate from first sale
        sku_s = sku_sales[sku_sales["sku_id"] == sku_id]
        if sku_s.empty:
            return None
        launch_date = pd.to_datetime(sku_s["sale_date"]).min().date()

    age_days = max((as_of_date - launch_date).days, 0)

    # ── Weekly sales aggregation ────────────────────────────────────────
    sku_s = sku_sales[sku_sales["sku_id"] == sku_id].copy()
    if sku_s.empty:
        return _empty_features(sku_id, age_days)

    sku_s["sale_date"] = pd.to_datetime(sku_s["sale_date"])
    sku_s["week"] = sku_s["sale_date"].dt.isocalendar().week.astype(int)
    sku_s["year_week"] = (
        sku_s["sale_date"].dt.year * 100 + sku_s["week"]
    )

    weekly_sales = (
        sku_s.groupby("year_week")["qty_sold"]
        .sum()
        .sort_index()
        .reset_index()
    )
    weeks_of_history = len(weekly_sales)
    avg_weekly_sales = float(weekly_sales["qty_sold"].mean()) if weeks_of_history > 0 else 0.0
    peak_weekly_sales = float(weekly_sales["qty_sold"].max()) if weeks_of_history > 0 else 0.0

    # Current vs peak ratio
    recent_weeks = min(config.trend_window_weeks, len(weekly_sales))
    recent_avg = float(weekly_sales["qty_sold"].tail(recent_weeks).mean()) if recent_weeks > 0 else 0.0
    current_vs_peak = (recent_avg / peak_weekly_sales) if peak_weekly_sales > 0 else 0.0
    current_vs_peak = min(current_vs_peak, 1.0)

    # ── Sales velocity trend ────────────────────────────────────────────
    sales_velocity_trend = _compute_trend(
        weekly_sales["qty_sold"].values, config.trend_window_weeks
    )

    # ── Trial trend ─────────────────────────────────────────────────────
    trial_trend = 0.0
    conversion_trend = 0.0
    if not sku_trials.empty:
        sku_t = sku_trials[sku_trials["sku_id"] == sku_id].copy()
        if not sku_t.empty:
            sku_t["trial_date"] = pd.to_datetime(sku_t["trial_date"])
            sku_t["week"] = sku_t["trial_date"].dt.isocalendar().week.astype(int)
            sku_t["year_week"] = sku_t["trial_date"].dt.year * 100 + sku_t["week"]

            weekly_trials = (
                sku_t.groupby("year_week")
                .agg(trial_count=("sku_id", "count"),
                     conversions=("resulted_in_order", "sum"))
                .sort_index()
                .reset_index()
            )
            trial_trend = _compute_trend(
                weekly_trials["trial_count"].values, config.trend_window_weeks
            )

            # Conversion trend
            weekly_trials["conv_rate"] = (
                weekly_trials["conversions"] / weekly_trials["trial_count"].clip(lower=1)
            )
            conversion_trend = _compute_trend(
                weekly_trials["conv_rate"].values, config.trend_window_weeks
            )

    # ── Aging inventory ─────────────────────────────────────────────────
    aging_pct = 0.0
    if not sku_inventory.empty:
        sku_inv = sku_inventory[sku_inventory["sku_id"] == sku_id]
        if not sku_inv.empty and "snapshot_date" in sku_inv.columns:
            sku_inv = sku_inv.copy()
            sku_inv["snapshot_date"] = pd.to_datetime(sku_inv["snapshot_date"])
            latest = sku_inv.sort_values("snapshot_date").iloc[-1]
            days_on_hand = (pd.Timestamp(as_of_date) - latest["snapshot_date"]).days
            total_on_hand = float(latest.get("on_hand_qty", 0))
            if total_on_hand > 0 and days_on_hand > config.aging_threshold_days:
                aging_pct = 1.0
            elif total_on_hand > 0:
                aging_pct = max(0.0, min(1.0, days_on_hand / config.aging_threshold_days))

    # ── Markdown count ──────────────────────────────────────────────────
    # Approximated from pricing/promotion data if available
    markdown_count = 0

    return {
        "sku_id": sku_id,
        "age_days": age_days,
        "sales_velocity_trend": round(float(sales_velocity_trend), 4),
        "trial_trend": round(float(trial_trend), 4),
        "conversion_trend": round(float(conversion_trend), 4),
        "aging_inventory_pct": round(float(aging_pct), 4),
        "markdown_count": markdown_count,
        "avg_weekly_sales": round(float(avg_weekly_sales), 2),
        "weeks_of_history": weeks_of_history,
        "peak_weekly_sales": round(float(peak_weekly_sales), 2),
        "current_vs_peak_ratio": round(float(current_vs_peak), 4),
    }


def _empty_features(sku_id: str, age_days: int) -> dict:
    """Return zeroed features for a SKU with no sales."""
    return {
        "sku_id": sku_id,
        "age_days": age_days,
        "sales_velocity_trend": 0.0,
        "trial_trend": 0.0,
        "conversion_trend": 0.0,
        "aging_inventory_pct": 0.0,
        "markdown_count": 0,
        "avg_weekly_sales": 0.0,
        "weeks_of_history": 0,
        "peak_weekly_sales": 0.0,
        "current_vs_peak_ratio": 0.0,
    }


def _compute_trend(values: np.ndarray, window: int) -> float:
    """Compute normalized linear trend over the last `window` observations.

    Returns slope normalized by mean so the trend is scale-independent.
    Positive = increasing, negative = decreasing.
    """
    if len(values) < 2:
        return 0.0

    recent = values[-window:] if len(values) >= window else values
    n = len(recent)
    if n < 2:
        return 0.0

    x = np.arange(n, dtype=float)
    y = np.array(recent, dtype=float)

    mean_y = np.mean(y)
    if mean_y == 0:
        return 0.0

    # Simple linear regression slope
    x_mean = np.mean(x)
    numerator = np.sum((x - x_mean) * (y - mean_y))
    denominator = np.sum((x - x_mean) ** 2)
    if denominator == 0:
        return 0.0

    slope = numerator / denominator
    # Normalize by mean to get relative trend
    return slope / mean_y
