"""Inter-store transfer optimization configuration.

Controls transfer candidate generation, optimization constraints,
cost parameters, and eligibility rules.
"""

from dataclasses import dataclass, field


@dataclass
class TransferConfig:
    """Configuration for the inter-store transfer optimizer."""

    # Database
    db_path: str = "data/dev.duckdb"
    inventory_table: str = "main_marts.mart_inventory_position"
    forecast_table: str = "main_ml.demand_forecasts"
    output_table: str = "main_ml.transfer_recommendations"

    # ─── Source eligibility ────────────────────────────────────────────
    # Minimum weeks-of-supply at source to qualify as donor
    min_source_wos: float = 8.0
    # Minimum presentation stock that must remain at source after transfer
    min_presentation_stock: int = 1
    # Prioritize items aging beyond this many weeks
    aging_threshold_weeks: float = 12.0
    # Lifecycle stages eligible for transfer (stranded / aging stock)
    eligible_lifecycle_stages: list[str] = field(
        default_factory=lambda: ["active", "mature", "aging", "eol"]
    )
    # SKU types eligible for transfer
    eligible_sku_types: list[str] = field(
        default_factory=lambda: ["physical_sell"]
    )

    # ─── Destination eligibility ──────────────────────────────────────
    # Maximum weeks-of-supply at destination to qualify as receiver
    max_destination_wos: float = 3.0
    # Destination must have at least this much demand (weekly units)
    min_destination_demand: float = 0.5

    # ─── Transfer costs & economics ──────────────────────────────────
    # Cost per unit transferred (₹) — covers logistics + handling
    cost_per_unit: float = 50.0
    # Additional fixed cost per transfer order (₹)
    fixed_cost_per_transfer: float = 200.0
    # Minimum net value (recovered sales - cost) for a transfer to be viable
    min_net_value: float = 100.0
    # Average selling price assumption when MRP unavailable
    default_unit_price: float = 1500.0

    # ─── Transfer lanes & lead times ──────────────────────────────────
    # Default transfer lead time (days) between stores
    default_transfer_lead_time_days: int = 3
    # Same-region transfers get faster lead time
    same_region_lead_time_days: int = 2
    # Cross-region lead time
    cross_region_lead_time_days: int = 5
    # Maximum acceptable transfer lead time (days)
    max_transfer_lead_time_days: int = 7
    # Planning horizon for demand recovery (weeks)
    planning_horizon_weeks: int = 4

    # ─── Optimization constraints ─────────────────────────────────────
    # Maximum transfers per source store per run
    max_transfers_per_source: int = 20
    # Maximum transfers per destination store per run
    max_transfers_per_destination: int = 15
    # Maximum total transfer units per source store
    max_units_per_source: int = 200
    # Destination capacity utilization ceiling (don't overfill)
    max_destination_capacity_pct: float = 0.90
    # Minimum transfer quantity per line
    min_transfer_qty: int = 1
    # Maximum transfer quantity per line
    max_transfer_qty: int = 50

    # ─── Aging stock priority ─────────────────────────────────────────
    # Bonus multiplier for aging/stranded inventory (increases priority)
    aging_bonus_multiplier: float = 1.5
    # EOL items get even higher priority
    eol_bonus_multiplier: float = 2.0

    # ─── Solver ───────────────────────────────────────────────────────
    solver_time_limit_seconds: int = 30
    solver_num_workers: int = 4

    # ─── Run schedule ─────────────────────────────────────────────────
    run_frequency: str = "weekly"  # "daily" or "weekly"


# Transfer reason codes
REASON_REBALANCE = "rebalance"
REASON_STOCKOUT_PREVENTION = "stockout_prevention"
REASON_AGING_CLEARANCE = "aging_clearance"
REASON_EOL_CLEARANCE = "eol_clearance"

REASON_DESCRIPTIONS = {
    REASON_REBALANCE: "Rebalance excess inventory to high-demand location",
    REASON_STOCKOUT_PREVENTION: "Prevent stockout at destination store",
    REASON_AGING_CLEARANCE: "Clear aging stock to higher-velocity location",
    REASON_EOL_CLEARANCE: "Clear end-of-life stock before write-off",
}
