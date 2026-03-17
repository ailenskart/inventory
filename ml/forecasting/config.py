"""Forecasting configuration and constants."""

from dataclasses import dataclass, field


@dataclass
class ForecastConfig:
    """Configuration for the demand forecasting pipeline."""

    # Data
    db_path: str = "data/dev.duckdb"
    demand_table: str = "main_marts.mart_demand_base"
    inventory_table: str = "main_marts.mart_inventory_position"

    # Forecast parameters
    horizon_weeks: int = 4
    min_history_weeks: int = 12
    season_length: int = 52
    frequency: str = "W"

    # Demand signal to forecast (primary target)
    target_column: str = "total_qty_sold"

    # Quantile levels for prediction intervals
    quantiles: list[float] = field(default_factory=lambda: [0.1, 0.25, 0.5, 0.75, 0.9])

    # Hierarchical reconciliation
    reconciliation_method: str = "MinTrace"  # MinTrace, BottomUp, TopDown

    # MLflow
    mlflow_tracking_uri: str = "sqlite:///data/mlflow.db"
    mlflow_experiment_name: str = "demand_forecasting_v1"

    # Training
    cv_n_windows: int = 3
    cv_step_size: int = 4
    cv_h: int = 4

    # Stockout treatment
    censor_stockout_demand: bool = True
    stockout_imputation_method: str = "mean"  # mean, median, max

    # Feature engineering
    lag_weeks: list[int] = field(default_factory=lambda: [1, 2, 3, 4, 8, 12, 26, 52])
    rolling_windows: list[int] = field(default_factory=lambda: [4, 8, 12, 26])


# Hierarchy levels for HierarchicalForecast
HIERARCHY_SPEC = [
    ["region"],
    ["region", "store_cluster"],
    ["region", "store_cluster", "store_id"],
    ["region", "store_cluster", "store_id", "category"],
    ["region", "store_cluster", "store_id", "category", "sku_id"],
]

# Lifecycle-aware forecast adjustments
# SKUs in different lifecycle stages may need different model selection
# or forecast dampening/boosting
LIFECYCLE_FORECAST_ADJUSTMENTS: dict[str, dict[str, float]] = {
    "launch": {"min_forecast_floor": 1.0, "uncertainty_multiplier": 1.5},
    "growth": {"min_forecast_floor": 0.5, "uncertainty_multiplier": 1.2},
    "core": {"min_forecast_floor": 0.0, "uncertainty_multiplier": 1.0},
    "maturity": {"min_forecast_floor": 0.0, "uncertainty_multiplier": 1.0},
    "decline": {"min_forecast_floor": 0.0, "uncertainty_multiplier": 1.3},
    "exit": {"min_forecast_floor": 0.0, "uncertainty_multiplier": 1.5},
}

# Inventory status thresholds (weeks of supply)
INVENTORY_THRESHOLDS = {
    "stockout": 0,
    "critical": 1,
    "low": 2,
    "healthy_min": 3,
    "healthy_max": 8,
    "excess": 12,
}
