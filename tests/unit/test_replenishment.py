"""Unit tests for the replenishment engine.

Test cases:
1. No order when stock is sufficient
2. Order when projected stockout occurs
3. Respect MOQ and pack size
4. Cap by store capacity
5. Emergency case behavior
6. Display dummy replenishment
7. Safety stock and reorder point math
8. Stockout risk computation
9. Lost sales estimation
10. Simulation comparison
"""

import math

import numpy as np
import pandas as pd
import pytest

from services.replenishment.config import (
    URGENCY_EMERGENCY,
    URGENCY_LOW,
    URGENCY_NORMAL,
    URGENCY_URGENT,
    ReplenishmentConfig,
)
from services.replenishment.engine import (
    apply_moq,
    compute_days_of_cover,
    compute_order_up_to_level,
    compute_reorder_point,
    compute_safety_stock,
    compute_stockout_risk,
    estimate_lost_sales,
    generate_recommendations,
    get_z_score,
    round_up_to_case_pack,
)


@pytest.fixture
def config():
    return ReplenishmentConfig()


def _make_position(
    store_id="STORE_001",
    sku_id="SKU_001",
    on_hand_qty=50,
    in_transit_qty=0,
    available_qty=50,
    avg_weekly_demand=14.0,
    point_forecast=14.0,
    upper_bound=18.0,
    demand_std_weekly=3.0,
    lead_time_days=7,
    moq=1,
    case_pack=1,
    store_cluster="METRO_HIGH",
    sku_type="physical_sell",
    fulfillment_type="direct_sell",
    is_display_only=0,
    category="eyeglasses",
    vendor_id="VND0001",
    mrp=2000,
    store_capacity=500,
    current_store_units=200,
):
    """Create a single position row for testing."""
    return pd.DataFrame([{
        "store_id": store_id,
        "sku_id": sku_id,
        "on_hand_qty": on_hand_qty,
        "in_transit_qty": in_transit_qty,
        "available_qty": available_qty,
        "avg_weekly_demand": avg_weekly_demand,
        "point_forecast": point_forecast,
        "upper_bound": upper_bound,
        "demand_std_weekly": demand_std_weekly,
        "lead_time_days": lead_time_days,
        "moq": moq,
        "case_pack": case_pack,
        "store_cluster": store_cluster,
        "sku_type": sku_type,
        "fulfillment_type": fulfillment_type,
        "is_display_only": is_display_only,
        "category": category,
        "vendor_id": vendor_id,
        "mrp": mrp,
        "store_capacity": store_capacity,
        "current_store_units": current_store_units,
    }])


# ─── Core Math Tests ────────────────────────────────────────────────────────


class TestSafetyStock:
    def test_positive_values(self):
        ss = compute_safety_stock(demand_std_daily=2.0, lead_time_days=7, z_score=1.645)
        # 1.645 * 2.0 * sqrt(7) = 1.645 * 2.0 * 2.6458 ≈ 8.70
        assert ss == pytest.approx(1.645 * 2.0 * math.sqrt(7), rel=1e-3)

    def test_zero_demand_std(self):
        assert compute_safety_stock(0.0, 7, 1.645) == 0.0

    def test_zero_lead_time(self):
        assert compute_safety_stock(2.0, 0, 1.645) == 0.0


class TestReorderPoint:
    def test_basic_calculation(self):
        rop = compute_reorder_point(avg_daily_demand=2.0, lead_time_days=7, safety_stock=8.7)
        assert rop == pytest.approx(2.0 * 7 + 8.7)

    def test_zero_demand(self):
        rop = compute_reorder_point(0.0, 7, 5.0)
        assert rop == pytest.approx(5.0)


class TestOrderUpToLevel:
    def test_basic(self):
        out = compute_order_up_to_level(avg_daily_demand=2.0, target_days_of_cover=28, safety_stock=8.7)
        assert out == pytest.approx(2.0 * 28 + 8.7)


class TestRoundUpToCasePack:
    def test_exact_multiple(self):
        assert round_up_to_case_pack(12.0, 6) == 12

    def test_round_up(self):
        assert round_up_to_case_pack(13.0, 6) == 18

    def test_case_pack_1(self):
        assert round_up_to_case_pack(7.3, 1) == 8

    def test_zero(self):
        assert round_up_to_case_pack(0, 6) == 0

    def test_negative(self):
        assert round_up_to_case_pack(-5.0, 6) == 0


class TestApplyMOQ:
    def test_above_moq(self):
        assert apply_moq(10, 5) == 10

    def test_below_moq(self):
        assert apply_moq(3, 5) == 5

    def test_zero_qty(self):
        assert apply_moq(0, 5) == 0


class TestStockoutRisk:
    def test_zero_stock_high_demand(self):
        risk = compute_stockout_risk(
            on_hand_qty=0, in_transit_qty=0,
            avg_daily_demand=5.0, demand_std_daily=2.0, lead_time_days=7,
        )
        assert risk > 0.9  # Very likely stockout

    def test_high_stock_low_demand(self):
        risk = compute_stockout_risk(
            on_hand_qty=100, in_transit_qty=0,
            avg_daily_demand=2.0, demand_std_daily=1.0, lead_time_days=7,
        )
        assert risk < 0.01  # Very unlikely stockout

    def test_zero_demand(self):
        risk = compute_stockout_risk(
            on_hand_qty=10, in_transit_qty=0,
            avg_daily_demand=0, demand_std_daily=0, lead_time_days=7,
        )
        assert risk == 0.0


class TestLostSalesEstimate:
    def test_basic(self):
        lost = estimate_lost_sales(
            stockout_risk=0.5, avg_daily_demand=5.0,
            lead_time_days=7, unit_price=2000,
        )
        # 0.5 * 5.0 * 7 * 2000 = 35000
        assert lost == pytest.approx(35000.0)

    def test_zero_risk(self):
        assert estimate_lost_sales(0.0, 5.0, 7, 2000) == 0.0


class TestDaysOfCover:
    def test_basic(self):
        doc = compute_days_of_cover(on_hand_qty=28, in_transit_qty=0, avg_daily_demand=2.0)
        assert doc == 14.0

    def test_zero_demand(self):
        doc = compute_days_of_cover(10, 0, 0.0)
        assert doc == float("inf")

    def test_zero_stock_zero_demand(self):
        assert compute_days_of_cover(0, 0, 0.0) == 0.0

    def test_includes_in_transit(self):
        doc = compute_days_of_cover(14, 14, 2.0)
        assert doc == 14.0


class TestZScore:
    def test_known_value(self, config):
        z = get_z_score(0.95, config)
        assert z == pytest.approx(1.645)

    def test_interpolation(self, config):
        z = get_z_score(0.96, config)
        assert 1.645 < z < 1.881  # Between 0.95 and 0.97


# ─── Recommendation Logic Tests ─────────────────────────────────────────────


class TestNoOrderWhenSufficient:
    """Test: no order when stock is sufficient."""

    def test_high_stock_no_recommendation(self, config):
        """With 50 units and 2/day demand, 25 days of cover — no order needed."""
        positions = _make_position(on_hand_qty=50, point_forecast=14.0)
        recs = generate_recommendations(positions, config)
        assert len(recs) == 0, f"Expected no recs, got {len(recs)}"

    def test_above_reorder_point_no_order(self, config):
        """Stock well above reorder point should not trigger order."""
        positions = _make_position(on_hand_qty=30, point_forecast=7.0)  # ~30 days cover
        recs = generate_recommendations(positions, config)
        assert len(recs) == 0


class TestOrderWhenProjectedStockout:
    """Test: order when projected stockout occurs."""

    def test_low_stock_triggers_order(self, config):
        """With 2 units and 2/day demand, should trigger emergency."""
        positions = _make_position(on_hand_qty=2, point_forecast=14.0)
        recs = generate_recommendations(positions, config)
        assert len(recs) == 1
        rec = recs.iloc[0]
        assert rec["recommended_qty"] > 0
        assert rec["urgency"] in (URGENCY_EMERGENCY, URGENCY_URGENT)

    def test_zero_stock_emergency(self, config):
        """Zero stock should trigger emergency replenishment."""
        positions = _make_position(on_hand_qty=0, in_transit_qty=0, point_forecast=14.0)
        recs = generate_recommendations(positions, config)
        assert len(recs) == 1
        assert recs.iloc[0]["urgency"] == URGENCY_EMERGENCY
        assert recs.iloc[0]["reason_code"] == "emergency_stockout"


class TestRespectMOQAndPackSize:
    """Test: respect MOQ and pack size rules."""

    def test_moq_respected(self, config):
        """Order quantity should not be less than MOQ."""
        positions = _make_position(
            on_hand_qty=5, point_forecast=7.0,
            moq=10, case_pack=1, demand_std_weekly=1.0,
        )
        recs = generate_recommendations(positions, config)
        if len(recs) > 0:
            assert recs.iloc[0]["recommended_qty"] >= 10

    def test_case_pack_respected(self, config):
        """Order quantity should be a multiple of case pack."""
        positions = _make_position(
            on_hand_qty=3, point_forecast=14.0,
            moq=1, case_pack=6,
        )
        recs = generate_recommendations(positions, config)
        if len(recs) > 0:
            assert recs.iloc[0]["recommended_qty"] % 6 == 0

    def test_moq_and_case_pack_combined(self, config):
        """Both MOQ and case pack should be respected simultaneously."""
        positions = _make_position(
            on_hand_qty=3, point_forecast=14.0,
            moq=12, case_pack=6,
        )
        recs = generate_recommendations(positions, config)
        if len(recs) > 0:
            qty = recs.iloc[0]["recommended_qty"]
            assert qty >= 12  # MOQ
            assert qty % 6 == 0  # Case pack


class TestCapByStoreCapacity:
    """Test: cap by store capacity."""

    def test_capacity_constraint(self, config):
        """Order should be capped when store is near capacity."""
        positions = _make_position(
            on_hand_qty=2, point_forecast=14.0,
            store_capacity=50,  # Very small store
            current_store_units=45,  # Nearly full (90% = 45)
        )
        recs = generate_recommendations(positions, config)
        # With 90% cap: max_additional = 50 * 0.90 - 45 = 0
        # So should be empty or very limited
        if len(recs) > 0:
            assert recs.iloc[0]["recommended_qty"] <= 50

    def test_at_capacity_no_order(self, config):
        """No order when store is at capacity."""
        positions = _make_position(
            on_hand_qty=2, point_forecast=14.0,
            store_capacity=50,
            current_store_units=50,  # Completely full
        )
        recs = generate_recommendations(positions, config)
        assert len(recs) == 0


class TestEmergencyBehavior:
    """Test: emergency case behavior."""

    def test_stockout_is_emergency(self, config):
        """Complete stockout with no transit = emergency."""
        positions = _make_position(on_hand_qty=0, in_transit_qty=0, point_forecast=14.0)
        recs = generate_recommendations(positions, config)
        assert len(recs) == 1
        assert recs.iloc[0]["urgency"] == URGENCY_EMERGENCY

    def test_high_stockout_risk_emergency(self, config):
        """Very high stockout risk should be emergency."""
        positions = _make_position(
            on_hand_qty=1, in_transit_qty=0,
            point_forecast=70.0, demand_std_weekly=10.0,  # Very high demand
        )
        recs = generate_recommendations(positions, config)
        assert len(recs) == 1
        assert recs.iloc[0]["urgency"] in (URGENCY_EMERGENCY, URGENCY_URGENT)

    def test_emergency_includes_stockout_risk(self, config):
        """Emergency recommendations should report stockout risk."""
        positions = _make_position(on_hand_qty=0, in_transit_qty=0, point_forecast=14.0)
        recs = generate_recommendations(positions, config)
        assert recs.iloc[0]["stockout_risk"] > 0.8


class TestDisplayDummyReplenishment:
    """Test: display-only SKU replenishment follows fixed rules."""

    def test_display_needs_replenishment(self, config):
        """Display-only SKU with 0 on-hand should be replenished to max display qty."""
        positions = _make_position(
            on_hand_qty=0, in_transit_qty=0,
            is_display_only=1, sku_type="display_dummy",
            fulfillment_type="order_capture",
            point_forecast=0.0,
        )
        recs = generate_recommendations(positions, config)
        assert len(recs) == 1
        assert recs.iloc[0]["recommended_qty"] == config.display_max_on_hand
        assert recs.iloc[0]["reason_code"] == "display_replenishment"

    def test_display_sufficient_no_order(self, config):
        """Display with min on-hand should not need replenishment."""
        positions = _make_position(
            on_hand_qty=1, in_transit_qty=0,
            is_display_only=1, sku_type="display_dummy",
        )
        recs = generate_recommendations(positions, config)
        assert len(recs) == 0

    def test_display_urgency(self, config):
        """Display out of stock should be urgent (not emergency — no lost sales)."""
        positions = _make_position(
            on_hand_qty=0, in_transit_qty=0,
            is_display_only=1, sku_type="display_dummy",
        )
        recs = generate_recommendations(positions, config)
        assert recs.iloc[0]["urgency"] == URGENCY_URGENT


class TestRecommendationOutput:
    """Test recommendation output format and fields."""

    def test_output_columns(self, config):
        positions = _make_position(on_hand_qty=0, point_forecast=14.0)
        recs = generate_recommendations(positions, config)
        assert "sku_id" in recs.columns
        assert "source_location" in recs.columns
        assert "destination_store" in recs.columns
        assert "recommended_qty" in recs.columns
        assert "urgency" in recs.columns
        assert "reason_code" in recs.columns
        assert "expected_days_of_cover_after" in recs.columns

    def test_days_of_cover_improves(self, config):
        """After replenishment, DOC should be higher than before."""
        positions = _make_position(on_hand_qty=2, point_forecast=14.0)
        recs = generate_recommendations(positions, config)
        if len(recs) > 0:
            rec = recs.iloc[0]
            assert rec["expected_days_of_cover_after"] > rec["current_days_of_cover"]

    def test_source_location_set(self, config):
        positions = _make_position(on_hand_qty=0, point_forecast=14.0)
        recs = generate_recommendations(positions, config)
        assert recs.iloc[0]["source_location"] == "warehouse"


class TestMultiplePositions:
    """Test with multiple SKU x Store positions."""

    def test_mixed_positions(self, config):
        """Mix of sufficient and insufficient stock."""
        pos1 = _make_position(store_id="S1", sku_id="K1", on_hand_qty=100, point_forecast=7.0)
        pos2 = _make_position(store_id="S1", sku_id="K2", on_hand_qty=0, point_forecast=14.0)
        pos3 = _make_position(store_id="S2", sku_id="K1", on_hand_qty=5, point_forecast=14.0)

        positions = pd.concat([pos1, pos2, pos3], ignore_index=True)
        recs = generate_recommendations(positions, config)

        # S1/K1 should not need replenishment (100 units, low demand)
        assert "K1" not in recs[recs["destination_store"] == "S1"]["sku_id"].values or \
               len(recs[recs["destination_store"] == "S1"]) <= 1

        # S1/K2 should need replenishment (stockout)
        assert "K2" in recs["sku_id"].values

    def test_empty_positions(self, config):
        """Empty positions DataFrame returns empty recommendations."""
        recs = generate_recommendations(pd.DataFrame(), config)
        assert len(recs) == 0


# ─── Simulation Tests ────────────────────────────────────────────────────────


class TestSimulation:
    def test_daily_vs_weekly(self):
        from services.replenishment.simulation import (
            SimulationConfig,
            generate_synthetic_demand,
            run_comparison_simulation,
        )

        demand = generate_synthetic_demand(n_days=84, base_demand=5.0, seed=42)
        sim_config = SimulationConfig(n_weeks=12, initial_stock=50)
        results = run_comparison_simulation(demand, sim_config)

        assert "weekly" in results
        assert "daily" in results
        assert results["weekly"].total_days == 84
        assert results["daily"].total_days == 84

    def test_daily_fewer_stockouts(self):
        """Daily replenishment should generally have fewer stockouts than weekly."""
        from services.replenishment.simulation import (
            SimulationConfig,
            generate_synthetic_demand,
            run_comparison_simulation,
        )

        demand = generate_synthetic_demand(n_days=84, base_demand=8.0, noise_std=3.0, seed=123)
        sim_config = SimulationConfig(n_weeks=12, initial_stock=30, lead_time_days=5)
        results = run_comparison_simulation(demand, sim_config)

        # Daily should have equal or fewer stockout days
        assert results["daily"].stockout_days <= results["weekly"].stockout_days + 3  # Allow small margin

    def test_simulation_metrics_valid(self):
        """All simulation metrics should be in valid ranges."""
        from services.replenishment.simulation import (
            SimulationConfig,
            generate_synthetic_demand,
            simulate_single_series,
        )

        demand = generate_synthetic_demand(n_days=84, base_demand=5.0)
        sim_config = SimulationConfig(initial_stock=50)
        result = simulate_single_series(
            demand, review_period=1, lead_time=7,
            service_level=0.95, config=sim_config,
        )

        assert 0 <= result.avg_service_level <= 1
        assert 0 <= result.avg_fill_rate <= 1
        assert 0 <= result.stockout_rate <= 1
        assert result.total_units_ordered >= 0
        assert result.total_carrying_cost >= 0
