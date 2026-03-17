"""Replenishment decision engine.

Takes forecasts + current inventory and produces replenishment recommendations.
"""

import pandas as pd


def compute_reorder_points(
    forecasts: pd.DataFrame,
    lead_times: pd.DataFrame,
    service_level: float = 0.95,
) -> pd.DataFrame:
    """Compute reorder points for each SKU x Store.

    Reorder Point = (avg_daily_demand * lead_time_days) + safety_stock
    Safety Stock = z_score * std_daily_demand * sqrt(lead_time_days)
    """
    z_scores = {0.90: 1.28, 0.95: 1.65, 0.98: 2.05, 0.99: 2.33}
    z = z_scores.get(service_level, 1.65)

    df = forecasts.merge(lead_times, on=["sku_id"], how="left")
    df["lead_time_days"] = df["lead_time_days"].fillna(7)
    df["avg_daily_demand"] = df["forecast_qty"] / 7  # Weekly to daily
    df["safety_stock"] = z * df.get("demand_std", pd.Series(0, index=df.index)) * (df["lead_time_days"] ** 0.5)
    df["reorder_point"] = (df["avg_daily_demand"] * df["lead_time_days"]) + df["safety_stock"]
    df["reorder_qty"] = df["forecast_qty"]  # EOQ can be added later

    return df[["store_id", "sku_id", "reorder_point", "reorder_qty", "safety_stock"]]


def identify_replenishment_needs(
    reorder_points: pd.DataFrame,
    current_inventory: pd.DataFrame,
) -> pd.DataFrame:
    """Compare current inventory against reorder points."""
    df = current_inventory.merge(reorder_points, on=["store_id", "sku_id"], how="inner")
    df["needs_replenishment"] = df["on_hand_qty"] <= df["reorder_point"]
    df["deficit"] = (df["reorder_qty"] - df["on_hand_qty"]).clip(lower=0)

    return df[df["needs_replenishment"]].sort_values("deficit", ascending=False)
