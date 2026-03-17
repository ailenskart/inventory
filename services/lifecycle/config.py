"""Lifecycle Intelligence configuration and business rules.

Defines thresholds for rule-based lifecycle classification (v1)
and parameters for survival-analysis-inspired scoring (v2).
"""

from dataclasses import dataclass, field


@dataclass
class LifecycleConfig:
    """Configuration for the Product Lifecycle Intelligence engine."""

    # Database
    db_path: str = "data/dev.duckdb"
    sales_table: str = "main_staging.stg_sales_daily"
    inventory_table: str = "main_marts.mart_inventory_position"
    trials_table: str = "main_staging.stg_trials_daily"
    sku_table: str = "main_dimensions.dim_sku"
    promotions_table: str = "main_staging.stg_purchase_orders"
    output_table: str = "main_ml.lifecycle_classifications"

    # ─── Feature engineering ────────────────────────────────────────────────
    # Trend window: number of recent weeks used for slope calculation
    trend_window_weeks: int = 8
    # Minimum weeks of history required for classification
    min_history_weeks: int = 4
    # Aging inventory threshold: days on shelf before considered "aging"
    aging_threshold_days: int = 90

    # ─── Rule-based classifier v1 thresholds ────────────────────────────────

    # LAUNCH stage: young SKU with limited history
    launch_max_age_days: int = 60
    launch_max_history_weeks: int = 8

    # GROWTH stage: positive velocity trend, not yet at peak maturity
    growth_min_velocity_trend: float = 0.05
    growth_min_trial_trend: float = 0.0
    growth_max_age_days: int = 365

    # CORE stage: stable high performer
    core_min_current_vs_peak: float = 0.7
    core_min_avg_weekly_sales: float = 1.0
    core_max_aging_pct: float = 0.3

    # MATURITY stage: stable but flattening
    maturity_min_age_days: int = 180
    maturity_velocity_range: tuple[float, float] = (-0.05, 0.05)
    maturity_min_current_vs_peak: float = 0.4

    # DECLINE stage: falling metrics
    decline_max_velocity_trend: float = -0.05
    decline_max_current_vs_peak: float = 0.5
    decline_min_age_days: int = 120

    # EXIT stage: very low performance
    exit_max_current_vs_peak: float = 0.2
    exit_min_aging_pct: float = 0.5
    exit_min_age_days: int = 180

    # ─── Action thresholds ──────────────────────────────────────────────────
    # Markdown is recommended when aging inventory is high
    markdown_aging_threshold: float = 0.6
    # Transfer threshold: moderate aging, still some demand elsewhere
    transfer_aging_threshold: float = 0.4

    # ─── Survival scoring v2 parameters ─────────────────────────────────────
    # Weibull-inspired shape parameter (controls hazard shape)
    survival_shape: float = 1.5
    # Scale parameter (median lifecycle in days)
    survival_scale: float = 365.0
    # Feature weights for composite survival score
    survival_weights: dict[str, float] = field(default_factory=lambda: {
        "age_factor": 0.25,
        "velocity_factor": 0.25,
        "trial_factor": 0.15,
        "conversion_factor": 0.15,
        "aging_factor": 0.10,
        "markdown_factor": 0.10,
    })

    # ─── Confidence calibration ─────────────────────────────────────────────
    # Base confidence for rule-based classification
    base_confidence: float = 0.7
    # Bonus confidence when multiple signals agree
    agreement_bonus: float = 0.15
    # Penalty when few data points available
    low_data_penalty: float = 0.2
    # Minimum weeks of data for full confidence
    full_confidence_weeks: int = 12


# ─── Stage-to-action mapping defaults ─────────────────────────────────────────

STAGE_DEFAULT_ACTIONS: dict[str, str] = {
    "launch": "expand_distribution",
    "growth": "expand_distribution",
    "core": "protect_placement",
    "maturity": "protect_placement",
    "decline": "reduce_depth",
    "exit": "discontinue",
}

# ─── Lifecycle freshness scores (used by assortment) ──────────────────────────

LIFECYCLE_FRESHNESS_SCORES: dict[str, float] = {
    "launch": 1.0,
    "growth": 0.85,
    "core": 0.7,
    "maturity": 0.5,
    "decline": 0.25,
    "exit": 0.0,
}
