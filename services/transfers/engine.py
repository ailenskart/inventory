"""Inter-store transfer engine.

Identifies opportunities to rebalance inventory between stores:
- Excess stock at one store, stockout risk at another
- EOL clearance from slow stores to high-velocity stores
- Seasonal rebalancing between regions
"""

import pandas as pd


def find_transfer_opportunities(
    inventory_health: pd.DataFrame,
    min_excess_weeks: float = 8.0,
    max_receiving_weeks: float = 2.0,
) -> pd.DataFrame:
    """Identify potential transfers by matching excess stores with deficit stores.

    Args:
        inventory_health: DataFrame with store_id, sku_id, weeks_of_supply, inventory_status
        min_excess_weeks: Minimum WoS at source to qualify as donor
        max_receiving_weeks: Maximum WoS at destination to qualify as receiver
    """
    excess = inventory_health[inventory_health["weeks_of_supply"] >= min_excess_weeks].copy()
    deficit = inventory_health[inventory_health["weeks_of_supply"] <= max_receiving_weeks].copy()

    # Match by SKU
    opportunities = excess.merge(
        deficit,
        on="sku_id",
        suffixes=("_from", "_to"),
        how="inner",
    )

    # Don't transfer to same store
    opportunities = opportunities[opportunities["store_id_from"] != opportunities["store_id_to"]]

    # Calculate transfer qty (transfer half of excess, up to deficit need)
    opportunities["transfer_qty"] = opportunities.apply(
        lambda r: min(
            int(r.get("on_hand_qty_from", 0) * 0.3),
            max(0, int(r.get("reorder_qty_to", 5) - r.get("on_hand_qty_to", 0))),
        ),
        axis=1,
    )

    opportunities = opportunities[opportunities["transfer_qty"] > 0]
    return opportunities.sort_values("transfer_qty", ascending=False)
