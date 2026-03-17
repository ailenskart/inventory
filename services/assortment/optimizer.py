"""Assortment optimizer for store display walls.

Determines which SKUs to display at each store, given:
- Limited display slots
- Trial/demand data per SKU
- Store cluster profiles
- Product lifecycle stage
"""

import pandas as pd


def score_skus_for_store(
    store_id: str,
    sku_performance: pd.DataFrame,
    display_capacity: int,
) -> pd.DataFrame:
    """Score and rank SKUs for a store's display wall.

    Scoring factors:
    - Trial frequency (display demand)
    - Conversion rate (trial -> order)
    - Revenue per display slot
    - Lifecycle freshness
    - Category diversity requirement
    """
    df = sku_performance[sku_performance["store_id"] == store_id].copy()

    if df.empty:
        return df

    # Composite score (weights can be tuned)
    df["display_score"] = (
        0.3 * df.get("trial_frequency_norm", 0)
        + 0.25 * df.get("conversion_rate_norm", 0)
        + 0.25 * df.get("revenue_per_slot_norm", 0)
        + 0.2 * df.get("freshness_score", 0)
    )

    df = df.sort_values("display_score", ascending=False)

    # Top N by display capacity
    df["action"] = "remove"
    df.iloc[:display_capacity, df.columns.get_loc("action")] = "display"

    return df


def generate_assortment_changes(
    current_display: pd.DataFrame,
    recommended_display: pd.DataFrame,
) -> pd.DataFrame:
    """Diff current vs recommended display to produce actionable changes."""
    current_set = set(zip(current_display["store_id"], current_display["sku_id"]))
    recommended_set = set(zip(recommended_display["store_id"], recommended_display["sku_id"]))

    to_add = recommended_set - current_set
    to_remove = current_set - recommended_set

    changes = []
    for store_id, sku_id in to_add:
        changes.append({"store_id": store_id, "sku_id": sku_id, "action": "add_to_display"})
    for store_id, sku_id in to_remove:
        changes.append({"store_id": store_id, "sku_id": sku_id, "action": "remove_from_display"})

    return pd.DataFrame(changes)
