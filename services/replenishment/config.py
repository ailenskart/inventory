"""Replenishment configuration and business rules."""

from dataclasses import dataclass, field


@dataclass
class ReplenishmentConfig:
    """Configuration for the replenishment engine."""

    # Database
    db_path: str = "data/dev.duckdb"
    forecast_table: str = "main_ml.demand_forecasts"
    inventory_table: str = "main_marts.mart_inventory_position"
    output_table: str = "main_ml.replenishment_recommendations"

    # Service level targets by store cluster (higher for premium stores)
    service_levels: dict[str, float] = field(default_factory=lambda: {
        "METRO_HIGH": 0.98,
        "METRO_MID": 0.95,
        "TIER1_HIGH": 0.95,
        "TIER1_MID": 0.93,
        "TIER2": 0.90,
        "KIOSK": 0.90,
    })
    default_service_level: float = 0.95

    # Lead times (days)
    default_lead_time_days: int = 7
    emergency_lead_time_days: int = 2

    # Z-scores for service levels
    z_scores: dict[float, float] = field(default_factory=lambda: {
        0.90: 1.282,
        0.93: 1.476,
        0.95: 1.645,
        0.97: 1.881,
        0.98: 2.054,
        0.99: 2.326,
    })

    # MOQ and case pack defaults
    default_moq: int = 1
    default_case_pack: int = 1

    # Target days of cover after replenishment (order-up-to level)
    target_days_of_cover: int = 28  # 4 weeks

    # Emergency thresholds
    emergency_days_of_cover: float = 3.0  # Below this = emergency
    critical_days_of_cover: float = 7.0   # Below this = urgent
    stockout_risk_threshold: float = 0.7  # Probability threshold

    # Capacity
    max_capacity_utilization: float = 0.90  # Don't fill store beyond 90%

    # Display dummy rules
    display_min_on_hand: int = 1  # Minimum 1 unit for display
    display_max_on_hand: int = 2  # Max 2 units for display-only SKUs

    # Source
    default_source: str = "warehouse"

    # Forecast horizon to consider (weeks)
    planning_horizon_weeks: int = 4


# Urgency levels
URGENCY_EMERGENCY = "emergency"
URGENCY_URGENT = "urgent"
URGENCY_NORMAL = "normal"
URGENCY_LOW = "low"

# Reason codes for recommendations
REASON_CODES = {
    "projected_stockout": "Projected stockout within lead time",
    "below_reorder_point": "Stock below reorder point",
    "below_safety_stock": "Stock below safety stock",
    "display_replenishment": "Display dummy needs replenishment",
    "emergency_stockout": "Currently stocked out — emergency",
    "service_level_risk": "Service level at risk",
    "seasonal_buildup": "Seasonal demand buildup",
    "new_product_launch": "New product initial stock",
}
