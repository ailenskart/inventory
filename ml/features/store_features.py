"""Store-level feature engineering."""

import pandas as pd


def compute_store_features(daily_sales: pd.DataFrame, daily_inventory: pd.DataFrame) -> pd.DataFrame:
    """Compute store-level features for clustering and forecasting.

    Features:
    - avg_daily_sales, sales_volatility
    - avg_inventory_days, stockout_rate
    - category_mix (share of eyeglasses vs sunglasses)
    - trial_conversion_rate (if trial data available)
    """
    store_sales = (
        daily_sales.groupby("store_id")
        .agg(
            avg_daily_qty=("qty_sold", "mean"),
            total_revenue=("revenue", "sum"),
            sales_volatility=("qty_sold", "std"),
            sale_days=("sale_date", "nunique"),
        )
        .reset_index()
    )

    store_inventory = (
        daily_inventory.groupby("store_id")
        .agg(
            avg_on_hand=("on_hand_qty", "mean"),
            stockout_days=("on_hand_qty", lambda x: (x == 0).sum()),
            snapshot_days=("snapshot_date", "nunique"),
        )
        .reset_index()
    )

    store_inventory["stockout_rate"] = store_inventory["stockout_days"] / store_inventory["snapshot_days"].clip(lower=1)

    features = store_sales.merge(store_inventory, on="store_id", how="outer")
    return features
