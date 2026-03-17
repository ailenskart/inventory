"""Transfer optimization simulation.

Compares greedy heuristic vs OR-Tools optimized transfer selection
on synthetic data, demonstrating the value of optimization.
"""

import logging
import time

import numpy as np
import pandas as pd

from services.transfers.config import TransferConfig
from services.transfers.engine import (
    TransferResult,
    _greedy_fallback,
    generate_candidates,
    optimize_transfers,
)

logger = logging.getLogger(__name__)


def generate_synthetic_positions(
    n_stores: int = 20,
    n_skus: int = 50,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic inventory positions for simulation.

    Creates a realistic mix of excess and deficit positions across stores.
    """
    rng = np.random.RandomState(seed)

    regions = ["north", "south", "east", "west"]
    lifecycles = ["active", "mature", "aging", "eol"]
    lifecycle_weights = [0.4, 0.3, 0.2, 0.1]

    rows = []
    for s in range(n_stores):
        store_id = f"STR{s:04d}"
        region = regions[s % len(regions)]
        store_cluster = rng.choice(["METRO_HIGH", "METRO_MID", "TIER2"])
        capacity = rng.choice([300, 500, 800])
        current_units = int(capacity * rng.uniform(0.4, 0.85))

        for k in range(n_skus):
            sku_id = f"SKU{k:05d}"
            lifecycle = rng.choice(lifecycles, p=lifecycle_weights)
            avg_demand = max(0.1, rng.exponential(3.0))

            # Some stores have excess, some have deficit
            if rng.random() < 0.3:
                # Excess stock (high WoS)
                on_hand = int(avg_demand * rng.uniform(10, 25))
                wos = on_hand / max(avg_demand, 0.01)
            elif rng.random() < 0.5:
                # Deficit stock (low WoS)
                on_hand = int(avg_demand * rng.uniform(0, 2))
                wos = on_hand / max(avg_demand, 0.01)
            else:
                # Normal stock
                on_hand = int(avg_demand * rng.uniform(3, 8))
                wos = on_hand / max(avg_demand, 0.01)

            rows.append({
                "store_id": store_id,
                "sku_id": sku_id,
                "on_hand_qty": max(0, on_hand),
                "available_qty": max(0, on_hand),
                "in_transit_qty": 0,
                "avg_weekly_demand": round(avg_demand, 2),
                "forecast_weekly": round(avg_demand * rng.uniform(0.8, 1.2), 2),
                "total_8wk_demand": round(avg_demand * 8, 2),
                "weeks_of_supply": round(wos, 1),
                "inventory_status": (
                    "excess" if wos > 8 else "deficit" if wos < 2 else "healthy"
                ),
                "last_receipt_date": "2026-01-01",
                "store_cluster": store_cluster,
                "store_format": "standard",
                "region": region,
                "category": rng.choice(["eyeglasses", "sunglasses", "contact_lenses"]),
                "sku_type": "physical_sell",
                "fulfillment_type": "direct_sell",
                "lifecycle_stage": lifecycle,
                "is_display_only": 0,
                "total_capacity": capacity,
                "current_store_units": current_units,
            })

    return pd.DataFrame(rows)


def run_simulation(
    n_stores: int = 20,
    n_skus: int = 50,
    seed: int = 42,
    config: TransferConfig | None = None,
) -> dict:
    """Run simulation comparing greedy vs optimized transfer selection.

    Returns:
        Dictionary with greedy results, optimized results, and comparison metrics.
    """
    if config is None:
        config = TransferConfig()

    logger.info(f"Generating synthetic data: {n_stores} stores × {n_skus} SKUs")
    positions = generate_synthetic_positions(n_stores, n_skus, seed)

    logger.info("Generating transfer candidates")
    candidates = generate_candidates(positions, config)

    if candidates.empty:
        return {
            "positions": len(positions),
            "candidates": 0,
            "greedy": {"selected": 0, "net_value": 0},
            "optimized": {"selected": 0, "net_value": 0},
            "improvement_pct": 0,
        }

    # Run greedy
    logger.info("Running greedy heuristic")
    greedy_result = _greedy_fallback(candidates, config)

    # Run optimized
    logger.info("Running OR-Tools optimization")
    optimized_result = optimize_transfers(candidates, config)

    # Compare
    greedy_net = greedy_result.net_value
    opt_net = optimized_result.net_value
    improvement = (
        ((opt_net - greedy_net) / abs(greedy_net) * 100) if greedy_net != 0 else 0
    )

    summary = {
        "positions": len(positions),
        "candidates": len(candidates),
        "greedy": {
            "status": greedy_result.status,
            "selected": greedy_result.selected_transfers,
            "total_units": greedy_result.total_units,
            "recovered_value": greedy_result.total_recovered_value,
            "transfer_cost": greedy_result.total_transfer_cost,
            "net_value": greedy_result.net_value,
            "solve_time_ms": greedy_result.solve_time_ms,
        },
        "optimized": {
            "status": optimized_result.status,
            "selected": optimized_result.selected_transfers,
            "total_units": optimized_result.total_units,
            "recovered_value": optimized_result.total_recovered_value,
            "transfer_cost": optimized_result.total_transfer_cost,
            "net_value": optimized_result.net_value,
            "solve_time_ms": optimized_result.solve_time_ms,
        },
        "improvement_pct": round(improvement, 1),
        "net_value_delta": round(opt_net - greedy_net, 2),
    }

    logger.info(
        f"Simulation: greedy ₹{greedy_net:,.0f} vs optimized ₹{opt_net:,.0f} "
        f"({improvement:+.1f}% improvement)"
    )

    return summary
