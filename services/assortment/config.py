"""Assortment optimization configuration and scenario profiles.

Each store cluster gets a scenario profile that controls:
- Objective weights (demand, margin, freshness, trial, new-launch)
- Constraint parameters (category coverage, depth limits, freshness floor)
- Width vs depth preference
"""

from dataclasses import dataclass, field


@dataclass
class AssortmentScenario:
    """Scenario profile for a store cluster."""

    name: str
    description: str

    # ─── Objective weights (must sum to ~1.0) ────────────────────────────
    w_demand: float = 0.30          # Expected demand / conversion
    w_trial: float = 0.20           # Trial propensity (display interest)
    w_margin: float = 0.20          # Gross margin contribution
    w_freshness: float = 0.15       # Lifecycle freshness
    w_new_launch: float = 0.10      # Strategic new-launch exposure
    w_category_balance: float = 0.05  # Category diversity bonus

    # ─── Penalty weights ─────────────────────────────────────────────────
    p_duplication: float = 0.05     # Penalty for over-similar SKUs
    p_stale: float = 0.10          # Penalty for stale / aging inventory
    p_poor_fit: float = 0.05       # Penalty for poor cluster fit

    # ─── Constraints ─────────────────────────────────────────────────────
    # Category coverage: minimum fraction of display per category
    min_eyeglasses_pct: float = 0.40
    min_sunglasses_pct: float = 0.15
    min_contact_lenses_pct: float = 0.05

    # Depth limits
    max_depth_per_subcategory: int = 15  # Max SKUs from one subcategory
    max_per_brand: int = 20              # Max SKUs from one brand

    # Freshness
    min_new_launch_pct: float = 0.10     # At least 10% new launches
    new_launch_lifecycle: str = "new"     # Lifecycle stage considered "new"

    # Core assortment floor: min SKUs that must always be in assortment
    core_assortment_floor: int = 0       # 0 = no forced includes

    # Price tier mix (optional)
    min_budget_pct: float = 0.10
    min_premium_pct: float = 0.10

    # Width vs depth preference (1.0 = maximum width, 0.0 = maximum depth)
    width_preference: float = 0.6

    # Display-only vs sell-through split target
    display_dummy_target_pct: float = 0.70  # 70% display dummies for try-on


@dataclass
class AssortmentConfig:
    """Global assortment optimization configuration."""

    # Database
    db_path: str = "data/dev.duckdb"
    demand_table: str = "main_marts.mart_demand_base"
    inventory_table: str = "main_marts.mart_inventory_position"
    forecast_table: str = "main_ml.demand_forecasts"
    output_table: str = "main_ml.assortment_recommendations"

    # Planning
    planning_horizon_weeks: int = 4

    # Solver
    solver_time_limit_seconds: int = 30
    solver_num_workers: int = 4

    # Score normalization
    score_scale: int = 1000  # Scale float scores to int for CP-SAT

    # Lifecycle freshness scores
    freshness_scores: dict[str, float] = field(default_factory=lambda: {
        "new": 1.0,
        "growth": 0.8,
        "active": 0.6,
        "mature": 0.4,
        "aging": 0.2,
        "eol": 0.0,
    })

    # Price tier boundaries
    price_tiers: dict[str, tuple[float, float]] = field(default_factory=lambda: {
        "budget": (0, 1500),
        "mid": (1500, 3000),
        "premium": (3000, 6000),
        "luxury": (6000, float("inf")),
    })


# ─── Pre-built scenario profiles ─────────────────────────────────────────────

SCENARIOS: dict[str, AssortmentScenario] = {
    "metro_premium": AssortmentScenario(
        name="Metro Premium",
        description="High-end metro stores: margin-focused, premium brands, wide assortment",
        w_demand=0.25,
        w_trial=0.15,
        w_margin=0.30,
        w_freshness=0.15,
        w_new_launch=0.10,
        w_category_balance=0.05,
        min_eyeglasses_pct=0.45,
        min_sunglasses_pct=0.20,
        min_contact_lenses_pct=0.05,
        max_depth_per_subcategory=12,
        max_per_brand=15,
        min_new_launch_pct=0.15,
        min_premium_pct=0.25,
        width_preference=0.7,
        display_dummy_target_pct=0.65,
    ),
    "metro_mass": AssortmentScenario(
        name="Metro Mass",
        description="High-volume metro stores: demand-driven, balanced price mix",
        w_demand=0.35,
        w_trial=0.20,
        w_margin=0.15,
        w_freshness=0.15,
        w_new_launch=0.10,
        w_category_balance=0.05,
        min_eyeglasses_pct=0.40,
        min_sunglasses_pct=0.20,
        min_contact_lenses_pct=0.05,
        max_depth_per_subcategory=18,
        max_per_brand=25,
        min_new_launch_pct=0.10,
        min_budget_pct=0.20,
        width_preference=0.5,
        display_dummy_target_pct=0.70,
    ),
    "tier2_urban": AssortmentScenario(
        name="Tier-2 Urban",
        description="Tier-2 city stores: value-oriented, higher budget mix",
        w_demand=0.35,
        w_trial=0.15,
        w_margin=0.20,
        w_freshness=0.10,
        w_new_launch=0.10,
        w_category_balance=0.10,
        min_eyeglasses_pct=0.50,
        min_sunglasses_pct=0.10,
        min_contact_lenses_pct=0.05,
        max_depth_per_subcategory=20,
        max_per_brand=30,
        min_new_launch_pct=0.08,
        min_budget_pct=0.30,
        width_preference=0.4,
        display_dummy_target_pct=0.75,
    ),
    "mall_destination": AssortmentScenario(
        name="Mall Destination",
        description="Mall flagship stores: wide assortment, high trial, new-launch showcase",
        w_demand=0.20,
        w_trial=0.25,
        w_margin=0.15,
        w_freshness=0.20,
        w_new_launch=0.15,
        w_category_balance=0.05,
        min_eyeglasses_pct=0.35,
        min_sunglasses_pct=0.25,
        min_contact_lenses_pct=0.05,
        max_depth_per_subcategory=10,
        max_per_brand=12,
        min_new_launch_pct=0.20,
        min_premium_pct=0.20,
        width_preference=0.8,
        display_dummy_target_pct=0.60,
    ),
    "suburban_satellite": AssortmentScenario(
        name="Suburban / Satellite",
        description="Small-format stores: narrow but deep, core essentials",
        w_demand=0.40,
        w_trial=0.10,
        w_margin=0.25,
        w_freshness=0.05,
        w_new_launch=0.05,
        w_category_balance=0.15,
        min_eyeglasses_pct=0.55,
        min_sunglasses_pct=0.10,
        min_contact_lenses_pct=0.05,
        max_depth_per_subcategory=25,
        max_per_brand=35,
        min_new_launch_pct=0.05,
        min_budget_pct=0.35,
        width_preference=0.3,
        display_dummy_target_pct=0.80,
    ),
}


# Map store clusters to scenarios
CLUSTER_SCENARIO_MAP: dict[str, str] = {
    "METRO_HIGH": "metro_premium",
    "METRO_MID": "metro_mass",
    "TIER1_HIGH": "mall_destination",
    "TIER1_MID": "metro_mass",
    "TIER2": "tier2_urban",
    "KIOSK": "suburban_satellite",
}


def get_scenario_for_cluster(store_cluster: str) -> AssortmentScenario:
    """Get the scenario profile for a store cluster."""
    scenario_key = CLUSTER_SCENARIO_MAP.get(store_cluster, "metro_mass")
    return SCENARIOS[scenario_key]
