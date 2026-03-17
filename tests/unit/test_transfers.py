"""Unit tests for inter-store transfer optimization service."""

import pytest
import numpy as np
import pandas as pd

from services.transfers.config import (
    REASON_AGING_CLEARANCE,
    REASON_EOL_CLEARANCE,
    REASON_REBALANCE,
    REASON_STOCKOUT_PREVENTION,
    TransferConfig,
)
from services.transfers.engine import (
    TransferResult,
    _greedy_fallback,
    generate_candidates,
    optimize_transfers,
)
from services.transfers.simulation import generate_synthetic_positions, run_simulation


@pytest.fixture
def config():
    return TransferConfig()


def _make_positions(rows: list[dict]) -> pd.DataFrame:
    """Helper to create positions DataFrame with defaults."""
    defaults = {
        "on_hand_qty": 10,
        "available_qty": 10,
        "in_transit_qty": 0,
        "avg_weekly_demand": 2.0,
        "forecast_weekly": 2.0,
        "total_8wk_demand": 16.0,
        "weeks_of_supply": 5.0,
        "inventory_status": "healthy",
        "last_receipt_date": "2026-01-01",
        "store_cluster": "METRO_HIGH",
        "store_format": "standard",
        "region": "north",
        "category": "eyeglasses",
        "sku_type": "physical_sell",
        "fulfillment_type": "direct_sell",
        "lifecycle_stage": "active",
        "is_display_only": 0,
        "total_capacity": 500,
        "current_store_units": 200,
    }
    result = []
    for row in rows:
        full = {**defaults, **row}
        result.append(full)
    return pd.DataFrame(result)


# ─── Candidate Generation Tests ──────────────────────────────────────────────


class TestCandidateGeneration:
    def test_basic_candidate_match(self, config):
        """Excess store matched with deficit store for same SKU."""
        positions = _make_positions([
            # Source: excess stock (WoS=15, 30 units, demand=2/wk)
            {"store_id": "S1", "sku_id": "SKU001", "on_hand_qty": 30,
             "available_qty": 30, "weeks_of_supply": 15.0,
             "avg_weekly_demand": 2.0, "forecast_weekly": 2.0,
             "lifecycle_stage": "active", "region": "north"},
            # Destination: deficit stock (WoS=1, 2 units, demand=5/wk)
            {"store_id": "S2", "sku_id": "SKU001", "on_hand_qty": 2,
             "available_qty": 2, "weeks_of_supply": 0.4,
             "avg_weekly_demand": 5.0, "forecast_weekly": 5.0,
             "lifecycle_stage": "active", "region": "north"},
        ])
        candidates = generate_candidates(positions, config)
        assert len(candidates) >= 1
        assert candidates.iloc[0]["store_id_src"] == "S1"
        assert candidates.iloc[0]["store_id_dst"] == "S2"
        assert candidates.iloc[0]["sku_id"] == "SKU001"

    def test_no_self_transfer(self, config):
        """Store should not transfer to itself."""
        positions = _make_positions([
            {"store_id": "S1", "sku_id": "SKU001", "on_hand_qty": 30,
             "available_qty": 30, "weeks_of_supply": 15.0,
             "avg_weekly_demand": 2.0, "forecast_weekly": 2.0},
        ])
        candidates = generate_candidates(positions, config)
        if not candidates.empty:
            assert not (
                (candidates["store_id_src"] == candidates["store_id_dst"]).any()
            )

    def test_source_must_exceed_min_wos(self, config):
        """Source with WoS below threshold should not be a donor."""
        positions = _make_positions([
            # Below min_source_wos (default 8)
            {"store_id": "S1", "sku_id": "SKU001", "on_hand_qty": 10,
             "available_qty": 10, "weeks_of_supply": 5.0,
             "lifecycle_stage": "active"},
            {"store_id": "S2", "sku_id": "SKU001", "on_hand_qty": 1,
             "available_qty": 1, "weeks_of_supply": 0.2,
             "forecast_weekly": 5.0},
        ])
        candidates = generate_candidates(positions, config)
        assert candidates.empty

    def test_destination_must_be_below_max_wos(self, config):
        """Destination with adequate WoS should not receive transfers."""
        positions = _make_positions([
            {"store_id": "S1", "sku_id": "SKU001", "on_hand_qty": 30,
             "available_qty": 30, "weeks_of_supply": 15.0,
             "lifecycle_stage": "active"},
            # WoS=5.0 > max_destination_wos (default 3.0)
            {"store_id": "S2", "sku_id": "SKU001", "on_hand_qty": 10,
             "available_qty": 10, "weeks_of_supply": 5.0,
             "forecast_weekly": 2.0},
        ])
        candidates = generate_candidates(positions, config)
        assert candidates.empty

    def test_respects_presentation_stock(self, config):
        """Source should retain min_presentation_stock after transfer."""
        config.min_presentation_stock = 5
        positions = _make_positions([
            {"store_id": "S1", "sku_id": "SKU001", "on_hand_qty": 30,
             "available_qty": 30, "weeks_of_supply": 15.0,
             "lifecycle_stage": "active"},
            {"store_id": "S2", "sku_id": "SKU001", "on_hand_qty": 1,
             "available_qty": 1, "weeks_of_supply": 0.2,
             "forecast_weekly": 5.0},
        ])
        candidates = generate_candidates(positions, config)
        if not candidates.empty:
            # Max qty should be on_hand - min_presentation = 30 - 5 = 25
            assert candidates.iloc[0]["max_qty"] <= 25

    def test_ineligible_lifecycle_excluded(self, config):
        """SKUs with ineligible lifecycle stage should not be sources."""
        config.eligible_lifecycle_stages = ["aging", "eol"]
        positions = _make_positions([
            {"store_id": "S1", "sku_id": "SKU001", "on_hand_qty": 30,
             "available_qty": 30, "weeks_of_supply": 15.0,
             "lifecycle_stage": "new"},  # Not in eligible list
            {"store_id": "S2", "sku_id": "SKU001", "on_hand_qty": 1,
             "available_qty": 1, "weeks_of_supply": 0.2,
             "forecast_weekly": 5.0},
        ])
        candidates = generate_candidates(positions, config)
        assert candidates.empty

    def test_cross_sku_not_matched(self, config):
        """Different SKUs should not be matched together."""
        positions = _make_positions([
            {"store_id": "S1", "sku_id": "SKU001", "on_hand_qty": 30,
             "available_qty": 30, "weeks_of_supply": 15.0,
             "lifecycle_stage": "active"},
            {"store_id": "S2", "sku_id": "SKU002", "on_hand_qty": 1,
             "available_qty": 1, "weeks_of_supply": 0.2,
             "forecast_weekly": 5.0},
        ])
        candidates = generate_candidates(positions, config)
        assert candidates.empty

    def test_transfer_lead_time_same_region(self, config):
        """Same-region transfers should get faster lead time."""
        positions = _make_positions([
            {"store_id": "S1", "sku_id": "SKU001", "on_hand_qty": 30,
             "available_qty": 30, "weeks_of_supply": 15.0,
             "lifecycle_stage": "active", "region": "north"},
            {"store_id": "S2", "sku_id": "SKU001", "on_hand_qty": 1,
             "available_qty": 1, "weeks_of_supply": 0.2,
             "forecast_weekly": 5.0, "region": "north"},
        ])
        candidates = generate_candidates(positions, config)
        assert not candidates.empty
        assert candidates.iloc[0]["transfer_lead_time"] == config.same_region_lead_time_days

    def test_transfer_lead_time_cross_region(self, config):
        """Cross-region transfers should get longer lead time."""
        positions = _make_positions([
            {"store_id": "S1", "sku_id": "SKU001", "on_hand_qty": 30,
             "available_qty": 30, "weeks_of_supply": 15.0,
             "lifecycle_stage": "active", "region": "north"},
            {"store_id": "S2", "sku_id": "SKU001", "on_hand_qty": 1,
             "available_qty": 1, "weeks_of_supply": 0.2,
             "forecast_weekly": 5.0, "region": "south"},
        ])
        candidates = generate_candidates(positions, config)
        assert not candidates.empty
        assert candidates.iloc[0]["transfer_lead_time"] == config.cross_region_lead_time_days


# ─── Scoring Tests ────────────────────────────────────────────────────────────


class TestCandidateScoring:
    def test_aging_stock_gets_priority_bonus(self, config):
        """Aging stock should get higher priority bonus."""
        positions = _make_positions([
            {"store_id": "S1", "sku_id": "SKU001", "on_hand_qty": 30,
             "available_qty": 30, "weeks_of_supply": 15.0,
             "lifecycle_stage": "aging", "region": "north"},
            {"store_id": "S1", "sku_id": "SKU002", "on_hand_qty": 30,
             "available_qty": 30, "weeks_of_supply": 15.0,
             "lifecycle_stage": "active", "region": "north"},
            {"store_id": "S2", "sku_id": "SKU001", "on_hand_qty": 1,
             "available_qty": 1, "weeks_of_supply": 0.2,
             "forecast_weekly": 5.0, "region": "north"},
            {"store_id": "S2", "sku_id": "SKU002", "on_hand_qty": 1,
             "available_qty": 1, "weeks_of_supply": 0.2,
             "forecast_weekly": 5.0, "region": "north"},
        ])
        candidates = generate_candidates(positions, config)
        aging_row = candidates[candidates["lifecycle_stage_src"] == "aging"]
        active_row = candidates[candidates["lifecycle_stage_src"] == "active"]
        if not aging_row.empty and not active_row.empty:
            assert aging_row.iloc[0]["priority_bonus"] > active_row.iloc[0]["priority_bonus"]

    def test_eol_gets_highest_bonus(self, config):
        """EOL stock should get the highest priority bonus."""
        positions = _make_positions([
            {"store_id": "S1", "sku_id": "SKU001", "on_hand_qty": 30,
             "available_qty": 30, "weeks_of_supply": 15.0,
             "lifecycle_stage": "eol", "region": "north"},
            {"store_id": "S2", "sku_id": "SKU001", "on_hand_qty": 1,
             "available_qty": 1, "weeks_of_supply": 0.2,
             "forecast_weekly": 5.0, "region": "north"},
        ])
        candidates = generate_candidates(positions, config)
        if not candidates.empty:
            assert candidates.iloc[0]["priority_bonus"] == config.eol_bonus_multiplier

    def test_negative_net_value_filtered(self, config):
        """Candidates with net value below threshold should be filtered out."""
        config.min_net_value = 99999  # Impossibly high
        positions = _make_positions([
            {"store_id": "S1", "sku_id": "SKU001", "on_hand_qty": 30,
             "available_qty": 30, "weeks_of_supply": 15.0,
             "lifecycle_stage": "active"},
            {"store_id": "S2", "sku_id": "SKU001", "on_hand_qty": 1,
             "available_qty": 1, "weeks_of_supply": 0.2,
             "forecast_weekly": 5.0},
        ])
        candidates = generate_candidates(positions, config)
        assert candidates.empty

    def test_reason_codes(self, config):
        """Verify correct reason codes are assigned."""
        positions = _make_positions([
            {"store_id": "S1", "sku_id": "SKU001", "on_hand_qty": 30,
             "available_qty": 30, "weeks_of_supply": 15.0,
             "lifecycle_stage": "eol", "region": "north"},
            {"store_id": "S1", "sku_id": "SKU002", "on_hand_qty": 30,
             "available_qty": 30, "weeks_of_supply": 15.0,
             "lifecycle_stage": "aging", "region": "north"},
            {"store_id": "S2", "sku_id": "SKU001", "on_hand_qty": 0,
             "available_qty": 0, "weeks_of_supply": 0.0,
             "forecast_weekly": 5.0, "region": "north"},
            {"store_id": "S2", "sku_id": "SKU002", "on_hand_qty": 1,
             "available_qty": 1, "weeks_of_supply": 0.2,
             "forecast_weekly": 5.0, "region": "north"},
        ])
        candidates = generate_candidates(positions, config)
        if not candidates.empty:
            reasons = set(candidates["reason"].unique())
            # Should contain at least one aging/eol reason
            assert reasons & {REASON_EOL_CLEARANCE, REASON_AGING_CLEARANCE}


# ─── Optimization Tests ──────────────────────────────────────────────────────


class TestOptimization:
    def _make_candidates(self, config):
        """Create a set of candidates for optimization tests."""
        positions = _make_positions([
            # Three source stores with excess
            {"store_id": "S1", "sku_id": "SKU001", "on_hand_qty": 40,
             "available_qty": 40, "weeks_of_supply": 20.0,
             "lifecycle_stage": "aging", "region": "north"},
            {"store_id": "S1", "sku_id": "SKU002", "on_hand_qty": 25,
             "available_qty": 25, "weeks_of_supply": 12.5,
             "lifecycle_stage": "active", "region": "north"},
            {"store_id": "S3", "sku_id": "SKU001", "on_hand_qty": 35,
             "available_qty": 35, "weeks_of_supply": 17.5,
             "lifecycle_stage": "mature", "region": "south"},
            # Two destinations with deficit
            {"store_id": "S2", "sku_id": "SKU001", "on_hand_qty": 2,
             "available_qty": 2, "weeks_of_supply": 0.4,
             "forecast_weekly": 5.0, "region": "north"},
            {"store_id": "S2", "sku_id": "SKU002", "on_hand_qty": 1,
             "available_qty": 1, "weeks_of_supply": 0.2,
             "forecast_weekly": 5.0, "region": "north"},
            {"store_id": "S4", "sku_id": "SKU001", "on_hand_qty": 3,
             "available_qty": 3, "weeks_of_supply": 1.0,
             "forecast_weekly": 3.0, "region": "south"},
        ])
        return generate_candidates(positions, config)

    def test_optimizer_produces_result(self, config):
        """Optimizer should return a valid TransferResult."""
        candidates = self._make_candidates(config)
        if candidates.empty:
            pytest.skip("No candidates generated")
        result = optimize_transfers(candidates, config)
        assert isinstance(result, TransferResult)
        assert result.status in ("optimal", "feasible", "greedy_fallback")
        assert result.selected_transfers >= 0
        assert result.total_units >= 0

    def test_optimizer_positive_net_value(self, config):
        """Optimal solution should have positive net value."""
        candidates = self._make_candidates(config)
        if candidates.empty:
            pytest.skip("No candidates generated")
        result = optimize_transfers(candidates, config)
        if result.selected_transfers > 0:
            assert result.net_value > 0

    def test_optimizer_respects_source_limits(self, config):
        """Total outbound from a source should not exceed limits."""
        config.max_units_per_source = 10
        candidates = self._make_candidates(config)
        if candidates.empty:
            pytest.skip("No candidates generated")
        result = optimize_transfers(candidates, config)
        # Check each source
        source_units = {}
        for t in result.transfers:
            src = t["from_store_id"]
            source_units[src] = source_units.get(src, 0) + t["qty"]
        for src, units in source_units.items():
            assert units <= config.max_units_per_source

    def test_optimizer_respects_max_transfers_per_destination(self, config):
        """Number of inbound transfers per destination should not exceed limit."""
        config.max_transfers_per_destination = 1
        candidates = self._make_candidates(config)
        if candidates.empty:
            pytest.skip("No candidates generated")
        result = optimize_transfers(candidates, config)
        dest_counts = {}
        for t in result.transfers:
            dst = t["to_store_id"]
            dest_counts[dst] = dest_counts.get(dst, 0) + 1
        for dst, count in dest_counts.items():
            assert count <= config.max_transfers_per_destination

    def test_empty_candidates(self, config):
        """Optimizer should handle empty candidates gracefully."""
        result = optimize_transfers(pd.DataFrame(), config)
        assert result.status == "no_candidates"
        assert result.selected_transfers == 0

    def test_transfer_ids_unique(self, config):
        """All transfer IDs in result should be unique."""
        candidates = self._make_candidates(config)
        if candidates.empty:
            pytest.skip("No candidates generated")
        result = optimize_transfers(candidates, config)
        ids = [t["transfer_id"] for t in result.transfers]
        assert len(ids) == len(set(ids))


# ─── Greedy Fallback Tests ────────────────────────────────────────────────────


class TestGreedyFallback:
    def test_greedy_produces_result(self, config):
        """Greedy fallback should return a valid TransferResult."""
        positions = _make_positions([
            {"store_id": "S1", "sku_id": "SKU001", "on_hand_qty": 30,
             "available_qty": 30, "weeks_of_supply": 15.0,
             "lifecycle_stage": "active", "region": "north"},
            {"store_id": "S2", "sku_id": "SKU001", "on_hand_qty": 1,
             "available_qty": 1, "weeks_of_supply": 0.2,
             "forecast_weekly": 5.0, "region": "north"},
        ])
        candidates = generate_candidates(positions, config)
        if candidates.empty:
            pytest.skip("No candidates")
        result = _greedy_fallback(candidates, config)
        assert result.status == "greedy_fallback"
        assert result.selected_transfers >= 0

    def test_greedy_respects_source_limits(self, config):
        """Greedy should respect max_units_per_source."""
        config.max_units_per_source = 5
        positions = _make_positions([
            {"store_id": "S1", "sku_id": "SKU001", "on_hand_qty": 50,
             "available_qty": 50, "weeks_of_supply": 25.0,
             "lifecycle_stage": "active", "region": "north"},
            {"store_id": "S2", "sku_id": "SKU001", "on_hand_qty": 1,
             "available_qty": 1, "weeks_of_supply": 0.2,
             "forecast_weekly": 5.0, "region": "north"},
        ])
        candidates = generate_candidates(positions, config)
        if candidates.empty:
            pytest.skip("No candidates")
        result = _greedy_fallback(candidates, config)
        source_units = {}
        for t in result.transfers:
            src = t["from_store_id"]
            source_units[src] = source_units.get(src, 0) + t["qty"]
        for src, units in source_units.items():
            assert units <= config.max_units_per_source


# ─── Simulation Tests ────────────────────────────────────────────────────────


class TestSimulation:
    def test_synthetic_positions_shape(self):
        """Synthetic position generator should produce expected shape."""
        df = generate_synthetic_positions(n_stores=5, n_skus=10)
        assert len(df) == 50  # 5 * 10
        assert "store_id" in df.columns
        assert "sku_id" in df.columns
        assert "weeks_of_supply" in df.columns
        assert df["store_id"].nunique() == 5
        assert df["sku_id"].nunique() == 10

    def test_synthetic_has_excess_and_deficit(self):
        """Synthetic data should contain both excess and deficit positions."""
        df = generate_synthetic_positions(n_stores=20, n_skus=50)
        excess = df[df["weeks_of_supply"] >= 8.0]
        deficit = df[df["weeks_of_supply"] <= 3.0]
        assert len(excess) > 0, "Should have excess positions"
        assert len(deficit) > 0, "Should have deficit positions"

    def test_simulation_runs(self):
        """Simulation should run end-to-end and return comparison metrics."""
        result = run_simulation(n_stores=5, n_skus=10, seed=42)
        assert "greedy" in result
        assert "optimized" in result
        assert "improvement_pct" in result
        assert "candidates" in result

    def test_simulation_deterministic(self):
        """Same seed should produce identical results."""
        r1 = run_simulation(n_stores=5, n_skus=10, seed=123)
        r2 = run_simulation(n_stores=5, n_skus=10, seed=123)
        assert r1["candidates"] == r2["candidates"]
        assert r1["greedy"]["net_value"] == r2["greedy"]["net_value"]


# ─── Config Tests ─────────────────────────────────────────────────────────────


class TestTransferConfig:
    def test_default_config(self):
        """Default config should have sensible values."""
        config = TransferConfig()
        assert config.min_source_wos > 0
        assert config.max_destination_wos > 0
        assert config.min_source_wos > config.max_destination_wos
        assert config.cost_per_unit > 0
        assert config.min_net_value > 0
        assert config.max_transfer_qty >= config.min_transfer_qty
        assert config.max_destination_capacity_pct <= 1.0

    def test_custom_config(self):
        """Custom config overrides should work."""
        config = TransferConfig(
            min_source_wos=12.0,
            max_destination_wos=1.0,
            cost_per_unit=100.0,
        )
        assert config.min_source_wos == 12.0
        assert config.max_destination_wos == 1.0
        assert config.cost_per_unit == 100.0


# ─── Transfer Result Tests ────────────────────────────────────────────────────


class TestTransferResult:
    def test_result_dataclass(self):
        """TransferResult should be constructable with defaults."""
        result = TransferResult(
            status="optimal",
            solve_time_ms=100.0,
            total_candidates=50,
            selected_transfers=10,
            total_units=100,
            total_recovered_value=50000.0,
            total_transfer_cost=5000.0,
            net_value=45000.0,
        )
        assert result.status == "optimal"
        assert result.selected_transfers == 10
        assert result.net_value == 45000.0
        assert result.transfers == []
        assert result.source_relief == {}
