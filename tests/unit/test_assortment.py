"""Unit tests for assortment optimization engine.

Covers: config, scoring, optimizer, simulation, pipeline helpers.
"""

import numpy as np
import pandas as pd
import pytest

from services.assortment.config import (
    CLUSTER_SCENARIO_MAP,
    SCENARIOS,
    AssortmentConfig,
    AssortmentScenario,
    get_scenario_for_cluster,
)
from services.assortment.scoring import (
    _normalize_column,
    compute_sku_scores,
    get_price_tier,
)
from services.assortment.simulation import (
    SimulationMetrics,
    compute_metrics,
    generate_synthetic_skus,
    heuristic_assortment,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def config():
    return AssortmentConfig()


@pytest.fixture
def scenario():
    return SCENARIOS["metro_mass"]


@pytest.fixture
def sample_skus():
    """Small SKU DataFrame for testing."""
    np.random.seed(42)
    n = 30
    return pd.DataFrame({
        "sku_id": [f"SKU_{i:03d}" for i in range(n)],
        "store_id": ["STORE_001"] * n,
        "category": (["eyeglasses"] * 15 + ["sunglasses"] * 10 + ["contact_lenses"] * 5),
        "subcategory": np.random.choice(
            ["full_rim", "half_rim", "rimless", "aviator", "round"], n
        ),
        "brand": np.random.choice(["BrandA", "BrandB", "BrandC"], n),
        "sku_type": np.random.choice(["display_dummy", "physical_sell"], n, p=[0.7, 0.3]),
        "is_display_only": np.random.choice([1, 0], n, p=[0.7, 0.3]),
        "fulfillment_type": np.random.choice(["order_capture", "direct_sell"], n),
        "lifecycle_stage": np.random.choice(
            ["new", "growth", "active", "mature", "aging", "eol"],
            n, p=[0.15, 0.2, 0.3, 0.2, 0.1, 0.05],
        ),
        "mrp": np.random.choice([999, 1499, 2499, 3499, 4999, 6999], n),
        "margin_pct": np.random.uniform(0.2, 0.6, n).round(2),
        "avg_weekly_demand": np.random.exponential(3, n).round(1),
        "display_interest": np.random.poisson(5, n),
        "trial_conversion_rate": np.random.uniform(0.0, 0.3, n).round(3),
    })


@pytest.fixture
def scored_skus(sample_skus, scenario, config):
    """Scored SKU DataFrame."""
    return compute_sku_scores(sample_skus, scenario, config)


# ─── Config Tests ────────────────────────────────────────────────────────────


class TestAssortmentConfig:
    def test_default_config(self, config):
        assert config.score_scale == 1000
        assert config.solver_time_limit_seconds == 30
        assert config.planning_horizon_weeks == 4

    def test_freshness_scores_all_stages(self, config):
        assert config.freshness_scores["new"] == 1.0
        assert config.freshness_scores["eol"] == 0.0
        assert len(config.freshness_scores) == 6

    def test_price_tiers_cover_range(self, config):
        tiers = config.price_tiers
        assert tiers["budget"][0] == 0
        assert tiers["luxury"][1] == float("inf")
        assert tiers["budget"][1] == tiers["mid"][0]  # No gap

    def test_custom_db_path(self):
        c = AssortmentConfig(db_path="/tmp/test.duckdb")
        assert c.db_path == "/tmp/test.duckdb"


class TestAssortmentScenarios:
    def test_all_scenarios_exist(self):
        expected = {"metro_premium", "metro_mass", "tier2_urban", "mall_destination", "suburban_satellite"}
        assert set(SCENARIOS.keys()) == expected

    def test_scenario_weights_sum_to_one(self):
        for name, s in SCENARIOS.items():
            total = s.w_demand + s.w_trial + s.w_margin + s.w_freshness + s.w_new_launch + s.w_category_balance
            assert abs(total - 1.0) < 0.01, f"{name} weights sum to {total}"

    def test_metro_premium_is_margin_heavy(self):
        s = SCENARIOS["metro_premium"]
        assert s.w_margin >= s.w_demand
        assert s.min_premium_pct >= 0.20

    def test_suburban_is_demand_heavy(self):
        s = SCENARIOS["suburban_satellite"]
        assert s.w_demand >= 0.40
        assert s.width_preference < 0.5  # Prefers depth

    def test_mall_has_high_new_launch(self):
        s = SCENARIOS["mall_destination"]
        assert s.min_new_launch_pct >= 0.20
        assert s.w_trial >= 0.20

    def test_category_pcts_are_feasible(self):
        for name, s in SCENARIOS.items():
            total = s.min_eyeglasses_pct + s.min_sunglasses_pct + s.min_contact_lenses_pct
            assert total <= 1.0, f"{name}: category minimums sum to {total} > 1"


class TestClusterMapping:
    def test_all_clusters_mapped(self):
        expected_clusters = {"METRO_HIGH", "METRO_MID", "TIER1_HIGH", "TIER1_MID", "TIER2", "KIOSK"}
        assert set(CLUSTER_SCENARIO_MAP.keys()) == expected_clusters

    def test_all_mapped_scenarios_exist(self):
        for cluster, scenario_key in CLUSTER_SCENARIO_MAP.items():
            assert scenario_key in SCENARIOS, f"Cluster {cluster} maps to unknown scenario {scenario_key}"

    def test_get_scenario_for_known_cluster(self):
        s = get_scenario_for_cluster("METRO_HIGH")
        assert s.name == "Metro Premium"

    def test_get_scenario_for_unknown_cluster_defaults(self):
        s = get_scenario_for_cluster("UNKNOWN_CLUSTER")
        assert s.name == "Metro Mass"  # Default fallback


# ─── Scoring Tests ───────────────────────────────────────────────────────────


class TestNormalization:
    def test_normalize_basic(self):
        df = pd.DataFrame({"x": [0, 5, 10]})
        result = _normalize_column(df, "x")
        assert result.iloc[0] == 0.0
        assert result.iloc[1] == 0.5
        assert result.iloc[2] == 1.0

    def test_normalize_constant_column(self):
        df = pd.DataFrame({"x": [5, 5, 5]})
        result = _normalize_column(df, "x")
        assert (result == 0.5).all()

    def test_normalize_missing_column(self):
        df = pd.DataFrame({"x": [1, 2, 3]})
        result = _normalize_column(df, "missing_col")
        assert (result == 0.0).all()

    def test_normalize_with_nulls(self):
        df = pd.DataFrame({"x": [0, None, 10]})
        result = _normalize_column(df, "x")
        assert result.iloc[0] == 0.0
        assert result.iloc[2] == 1.0


class TestSKUScoring:
    def test_scores_computed(self, scored_skus):
        required = ["demand_score", "trial_score", "margin_score",
                     "freshness_score", "new_launch_score", "category_balance_score",
                     "composite_score", "score_int"]
        for col in required:
            assert col in scored_skus.columns, f"Missing column: {col}"

    def test_composite_score_nonnegative(self, scored_skus):
        assert (scored_skus["composite_score"] >= 0).all()

    def test_score_int_is_integer(self, scored_skus):
        assert scored_skus["score_int"].dtype in (np.int64, np.int32, int)

    def test_demand_score_normalized(self, scored_skus):
        assert scored_skus["demand_score"].min() >= 0.0
        assert scored_skus["demand_score"].max() <= 1.0

    def test_freshness_score_maps_lifecycle(self, scored_skus, config):
        new_rows = scored_skus[scored_skus["lifecycle_stage"] == "new"]
        if not new_rows.empty:
            assert (new_rows["freshness_score"] == config.freshness_scores["new"]).all()

    def test_new_launch_score_binary(self, scored_skus):
        assert set(scored_skus["new_launch_score"].unique()).issubset({0.0, 1.0})

    def test_stale_penalty_applied(self, scored_skus):
        eol_rows = scored_skus[scored_skus["lifecycle_stage"] == "eol"]
        if not eol_rows.empty:
            assert (eol_rows["stale_penalty"] == 1.0).all()

    def test_poor_fit_penalty(self, sample_skus, scenario, config):
        """SKUs with zero demand and not display-only should get penalized."""
        df = sample_skus.copy()
        df.loc[0, "avg_weekly_demand"] = 0
        df.loc[0, "is_display_only"] = 0
        scored = compute_sku_scores(df, scenario, config)
        assert scored.loc[0, "poor_fit_penalty"] == 1.0

    def test_score_scale_applied(self, scored_skus, config):
        # score_int should be approximately composite_score * scale
        for _, row in scored_skus.head(5).iterrows():
            expected = int(row["composite_score"] * config.score_scale)
            assert row["score_int"] == expected


class TestPriceTier:
    def test_budget_tier(self, config):
        assert get_price_tier(999, config) == "budget"

    def test_mid_tier(self, config):
        assert get_price_tier(2499, config) == "mid"

    def test_premium_tier(self, config):
        assert get_price_tier(4999, config) == "premium"

    def test_luxury_tier(self, config):
        assert get_price_tier(7999, config) == "luxury"

    def test_boundary_value(self, config):
        assert get_price_tier(1500, config) == "mid"  # 1500 is start of mid

    def test_zero_price(self, config):
        assert get_price_tier(0, config) == "budget"


# ─── Optimizer Tests ─────────────────────────────────────────────────────────


class TestOptimizer:
    def test_empty_sku_data(self, scenario, config):
        from services.assortment.optimizer import optimize_store_assortment
        result = optimize_store_assortment(
            store_id="STORE_001",
            sku_data=pd.DataFrame(),
            display_capacity=50,
            scenario=scenario,
            config=config,
        )
        assert result.status == "infeasible"
        assert result.used_capacity == 0

    def test_zero_capacity(self, scored_skus, scenario, config):
        from services.assortment.optimizer import optimize_store_assortment
        result = optimize_store_assortment(
            store_id="STORE_001",
            sku_data=scored_skus,
            display_capacity=0,
            scenario=scenario,
            config=config,
        )
        assert result.status == "infeasible"

    def test_optimizer_respects_capacity(self, scored_skus, scenario, config):
        from services.assortment.optimizer import optimize_store_assortment
        capacity = 15
        result = optimize_store_assortment(
            store_id="STORE_001",
            sku_data=scored_skus,
            display_capacity=capacity,
            scenario=scenario,
            config=config,
        )
        assert result.used_capacity <= capacity
        assert len(result.selected_skus) <= capacity

    def test_optimizer_returns_valid_status(self, scored_skus, scenario, config):
        from services.assortment.optimizer import optimize_store_assortment
        result = optimize_store_assortment(
            store_id="STORE_001",
            sku_data=scored_skus,
            display_capacity=20,
            scenario=scenario,
            config=config,
        )
        assert result.status in ("optimal", "feasible", "infeasible", "greedy_fallback", "error", "unknown")

    def test_selected_skus_have_required_fields(self, scored_skus, scenario, config):
        from services.assortment.optimizer import optimize_store_assortment
        result = optimize_store_assortment(
            store_id="STORE_001",
            sku_data=scored_skus,
            display_capacity=20,
            scenario=scenario,
            config=config,
        )
        if result.selected_skus:
            sku = result.selected_skus[0]
            assert "sku_id" in sku
            assert "store_id" in sku
            assert "action" in sku
            assert sku["action"] == "include"

    def test_excluded_skus_have_reason(self, scored_skus, scenario, config):
        from services.assortment.optimizer import optimize_store_assortment
        result = optimize_store_assortment(
            store_id="STORE_001",
            sku_data=scored_skus,
            display_capacity=10,
            scenario=scenario,
            config=config,
        )
        if result.excluded_skus:
            sku = result.excluded_skus[0]
            assert "exclusion_reason" in sku

    def test_objective_value_nonnegative(self, scored_skus, scenario, config):
        from services.assortment.optimizer import optimize_store_assortment
        result = optimize_store_assortment(
            store_id="STORE_001",
            sku_data=scored_skus,
            display_capacity=20,
            scenario=scenario,
            config=config,
        )
        assert result.objective_value >= 0

    def test_diagnostics_present(self, scored_skus, scenario, config):
        from services.assortment.optimizer import optimize_store_assortment
        result = optimize_store_assortment(
            store_id="STORE_001",
            sku_data=scored_skus,
            display_capacity=20,
            scenario=scenario,
            config=config,
        )
        if result.status in ("optimal", "feasible"):
            assert "capacity_utilization" in result.diagnostics
            assert "category_mix" in result.diagnostics


class TestGreedyFallback:
    def test_greedy_fallback_selects_top_scores(self, scored_skus, scenario):
        from services.assortment.optimizer import _greedy_fallback
        result = _greedy_fallback("STORE_001", scored_skus, 10, scenario)
        assert result.status == "greedy_fallback"
        assert len(result.selected_skus) == 10
        # Should be sorted by composite_score descending
        scores = [s["composite_score"] for s in result.selected_skus]
        assert scores == sorted(scores, reverse=True)

    def test_greedy_when_capacity_exceeds_skus(self, scored_skus, scenario):
        from services.assortment.optimizer import _greedy_fallback
        result = _greedy_fallback("STORE_001", scored_skus, 100, scenario)
        assert len(result.selected_skus) == len(scored_skus)
        assert len(result.excluded_skus) == 0


class TestAssortmentChanges:
    def test_generate_changes(self):
        from services.assortment.optimizer import generate_assortment_changes
        current = pd.DataFrame({
            "store_id": ["S1", "S1", "S1"],
            "sku_id": ["A", "B", "C"],
        })
        recommended = [
            {"store_id": "S1", "sku_id": "B"},
            {"store_id": "S1", "sku_id": "C"},
            {"store_id": "S1", "sku_id": "D"},
        ]
        changes = generate_assortment_changes(current, recommended)
        actions = changes.set_index("sku_id")["action"].to_dict()
        assert actions["A"] == "remove_from_display"
        assert actions["D"] == "add_to_display"
        assert "B" not in actions  # Unchanged
        assert "C" not in actions

    def test_empty_recommended(self):
        from services.assortment.optimizer import generate_assortment_changes
        current = pd.DataFrame({"store_id": ["S1"], "sku_id": ["A"]})
        changes = generate_assortment_changes(current, [])
        assert changes.empty


# ─── Simulation Tests ────────────────────────────────────────────────────────


class TestSyntheticDataGeneration:
    def test_generates_correct_count(self):
        df = generate_synthetic_skus(100)
        assert len(df) == 100

    def test_has_required_columns(self):
        df = generate_synthetic_skus(50)
        required = ["sku_id", "store_id", "category", "subcategory", "brand",
                     "lifecycle_stage", "mrp", "avg_weekly_demand", "is_display_only"]
        for col in required:
            assert col in df.columns

    def test_category_distribution(self):
        df = generate_synthetic_skus(200)
        cats = df["category"].value_counts()
        assert cats["eyeglasses"] == 100  # 50%
        assert cats["sunglasses"] == 60   # 30%

    def test_deterministic_with_seed(self):
        df1 = generate_synthetic_skus(50, seed=123)
        df2 = generate_synthetic_skus(50, seed=123)
        pd.testing.assert_frame_equal(df1, df2)


class TestHeuristicAssortment:
    def test_selects_top_by_demand(self, scored_skus):
        result = heuristic_assortment(scored_skus, 10)
        assert len(result) == 10
        # Should be top 10 by avg_weekly_demand
        top10 = scored_skus.nlargest(10, "avg_weekly_demand")
        assert set(result["sku_id"]) == set(top10["sku_id"])

    def test_handles_capacity_larger_than_skus(self, scored_skus):
        result = heuristic_assortment(scored_skus, 1000)
        assert len(result) == len(scored_skus)


class TestComputeMetrics:
    def test_empty_selection(self):
        m = compute_metrics(pd.DataFrame(), 50, "test")
        assert m.total_score == 0
        assert m.skus_selected == 0
        assert m.width == 0
        assert m.depth == 0

    def test_metrics_computed(self, scored_skus):
        selected = scored_skus.head(20)
        m = compute_metrics(selected, 50, "test")
        assert m.strategy == "test"
        assert m.skus_selected == 20
        assert m.capacity_utilization == round(20 / 50, 3)
        assert m.brand_count > 0
        assert m.subcategory_count > 0

    def test_capacity_utilization(self, scored_skus):
        selected = scored_skus.head(10)
        m = compute_metrics(selected, 20, "test")
        assert m.capacity_utilization == 0.5

    def test_new_launch_pct(self, scored_skus):
        m = compute_metrics(scored_skus, 100, "test")
        new_count = (scored_skus["lifecycle_stage"] == "new").sum()
        expected = round(new_count / len(scored_skus), 3)
        assert m.new_launch_pct == expected


class TestRunComparison:
    def test_comparison_returns_both_strategies(self, scored_skus, scenario, config):
        from services.assortment.simulation import run_comparison
        results = run_comparison(scored_skus, 15, scenario, config)
        assert "heuristic" in results
        assert "optimized" in results
        assert results["heuristic"].strategy == "heuristic"
        assert results["optimized"].strategy == "optimized"

    def test_both_respect_capacity(self, scored_skus, scenario, config):
        from services.assortment.simulation import run_comparison
        capacity = 15
        results = run_comparison(scored_skus, capacity, scenario, config)
        assert results["heuristic"].skus_selected <= capacity
        assert results["optimized"].skus_selected <= capacity


# ─── Integration: end-to-end optimization ────────────────────────────────────


class TestEndToEnd:
    def test_synthetic_to_optimization(self):
        """Generate data → score → optimize → validate output."""
        from services.assortment.optimizer import optimize_store_assortment

        config = AssortmentConfig()
        scenario = SCENARIOS["metro_mass"]
        skus = generate_synthetic_skus(100)
        scored = compute_sku_scores(skus, scenario, config)

        result = optimize_store_assortment(
            store_id="TEST_STORE",
            sku_data=scored,
            display_capacity=40,
            scenario=scenario,
            config=config,
        )

        assert result.status in ("optimal", "feasible", "greedy_fallback")
        assert result.used_capacity > 0
        assert result.used_capacity <= 40
        assert len(result.selected_skus) > 0
        assert result.objective_value > 0

    def test_all_scenarios_produce_results(self):
        """Each scenario should produce a valid result."""
        config = AssortmentConfig()
        skus = generate_synthetic_skus(80, seed=99)

        for name, scenario in SCENARIOS.items():
            scored = compute_sku_scores(skus, scenario, config)
            from services.assortment.optimizer import optimize_store_assortment
            result = optimize_store_assortment(
                store_id="TEST",
                sku_data=scored,
                display_capacity=30,
                scenario=scenario,
                config=config,
            )
            assert result.status in ("optimal", "feasible", "greedy_fallback"), \
                f"Scenario {name} returned {result.status}"
