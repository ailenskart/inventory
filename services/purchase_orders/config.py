"""Purchase order engine configuration.

Controls PO recommendation generation, vendor selection, allocation
constraints, and open PO planning parameters.
"""

from dataclasses import dataclass, field


@dataclass
class PurchaseOrderConfig:
    """Configuration for the PO recommendation engine."""

    # Database
    db_path: str = "data/dev.duckdb"
    inventory_table: str = "main_marts.mart_inventory_position"
    forecast_table: str = "main_ml.demand_forecasts"
    replenishment_table: str = "main_ml.replenishment_recommendations"
    vendor_performance_table: str = "main_marts.mart_vendor_performance"
    vendor_dim_table: str = "main_dimensions.dim_vendor"
    output_table: str = "main_ml.po_recommendations"

    # ─── Planning horizon ─────────────────────────────────────────────
    forecast_horizon_weeks: int = 12  # Rolling forecast shared with vendors
    po_horizon_weeks: int = 4         # Near-term PO generation window
    open_po_release_cadence_weeks: int = 2  # Release frequency for open POs

    # ─── Vendor selection ─────────────────────────────────────────────
    # Minimum composite score to be eligible for new POs
    min_vendor_score: float = 0.50
    # Preferred vendor gets this allocation share (rest split among alternates)
    preferred_vendor_allocation_pct: float = 0.70
    # Maximum allocation to a single vendor (diversification)
    max_single_vendor_allocation_pct: float = 0.85
    # Enable multi-vendor split for large orders
    enable_vendor_split: bool = True
    # Minimum order qty to consider splitting across vendors
    split_threshold_qty: int = 100

    # ─── MOQ / MOV ───────────────────────────────────────────────────
    # Pad orders to meet MOQ
    pad_to_moq: bool = True
    # Default unit cost when vendor cost data unavailable (₹)
    default_unit_cost: float = 500.0

    # ─── New SKU logic ────────────────────────────────────────────────
    # Initial stock multiplier for new SKUs (× weekly forecast)
    new_sku_initial_weeks: int = 6
    # New SKUs always go to preferred vendor
    new_sku_preferred_vendor_only: bool = True

    # ─── Cost optimization ────────────────────────────────────────────
    # Weight: cost vs reliability in vendor selection (0=all cost, 1=all reliability)
    reliability_vs_cost_weight: float = 0.6

    # ─── Service level ────────────────────────────────────────────────
    # Target fill rate for PO recommendations
    target_fill_rate: float = 0.95

    # ─── Urgency bucketing ────────────────────────────────────────────
    emergency_lead_time_buffer_days: int = 2
    urgent_lead_time_buffer_days: int = 5


# PO recommendation status codes
STATUS_RECOMMENDED = "recommended"
STATUS_APPROVED = "approved"
STATUS_RELEASED = "released"
STATUS_SPLIT = "split_across_vendors"
