"""Unit tests for vendor intelligence and PO recommendation engine."""

import pytest
import pandas as pd
from datetime import date
from dataclasses import asdict

from ml.vendor.scorecard import (
    ScorecardWeights,
    VendorScorecard,
    build_all_scorecards,
    build_vendor_scorecard,
    classify_vendor_tier,
    compute_capacity_accuracy,
    compute_composite_score,
    compute_forecast_adherence,
    compute_lead_time_adherence,
    compute_on_time_delivery_rate,
    compute_quality_pass_rate,
)
from ml.vendor.forecast_sharing import (
    build_vendor_forecast_summary,
    generate_rolling_forecast,
)
from ml.vendor.po_generator import (
    generate_open_po_plan,
    generate_purchase_orders,
)
from ml.vendor.portal import (
    build_vendor_portal_payload,
    VendorPortalPayload,
)
from services.purchase_orders.config import PurchaseOrderConfig
from services.purchase_orders.recommendation_engine import (
    PORecommendation,
    PORecommendationResult,
    generate_po_recommendations,
    select_vendor,
    split_allocation,
)
from services.purchase_orders.manager import PurchaseOrderManager


# ─── Vendor Scorecard Tests ──────────────────────────────────────────────────


class TestScorecardMetrics:
    def test_on_time_delivery_rate(self):
        assert compute_on_time_delivery_rate(9, 10) == 0.9
        assert compute_on_time_delivery_rate(10, 10) == 1.0
        assert compute_on_time_delivery_rate(0, 10) == 0.0
        # No data = benefit of doubt
        assert compute_on_time_delivery_rate(0, 0) == 1.0

    def test_lead_time_adherence(self):
        # 0 delay = perfect
        assert compute_lead_time_adherence(0, 7) == 1.0
        # 3.5 day delay with 7 day LT = 0.5
        assert compute_lead_time_adherence(3.5, 7) == 0.5
        # Delay > LT = clamped to 0
        assert compute_lead_time_adherence(10, 7) == 0.0
        # Negative delay (early) = still 1.0
        assert compute_lead_time_adherence(-2, 7) == 1.0

    def test_quality_pass_rate(self):
        assert compute_quality_pass_rate(95, 100) == 0.95
        assert compute_quality_pass_rate(100, 100) == 1.0
        assert compute_quality_pass_rate(0, 0) == 1.0

    def test_capacity_accuracy(self):
        assert compute_capacity_accuracy(100, 100) == 1.0
        assert compute_capacity_accuracy(80, 100) == 0.8
        # Over-delivery capped at 1.0
        assert compute_capacity_accuracy(120, 100) == 1.0
        assert compute_capacity_accuracy(0, 0) == 1.0

    def test_forecast_adherence(self):
        assert compute_forecast_adherence(100, 100) == 1.0
        assert compute_forecast_adherence(50, 100) == 0.5
        assert compute_forecast_adherence(0, 0) == 1.0

    def test_composite_score(self):
        score = compute_composite_score(1.0, 1.0, 1.0, 1.0, 1.0)
        assert score == 1.0

        score = compute_composite_score(0.5, 0.5, 0.5, 0.5, 0.5)
        assert score == 0.5

    def test_composite_with_custom_weights(self):
        weights = ScorecardWeights(
            on_time_delivery=1.0,
            lead_time_adherence=0.0,
            quality_pass_rate=0.0,
            capacity_accuracy=0.0,
            forecast_adherence=0.0,
        )
        score = compute_composite_score(0.8, 0.0, 0.0, 0.0, 0.0, weights)
        assert score == 0.8

    def test_vendor_tier_classification(self):
        assert classify_vendor_tier(0.95, True) == "preferred"
        assert classify_vendor_tier(0.80, True) == "standard"
        assert classify_vendor_tier(0.50, True) == "probation"
        assert classify_vendor_tier(0.95, False) == "inactive"


class TestVendorScorecard:
    def _make_vendor_row(self, **overrides):
        defaults = {
            "vendor_id": "VND001",
            "vendor_name": "Test Vendor",
            "is_active": True,
            "received_pos": 20,
            "on_time_deliveries": 18,
            "avg_delivery_delay_days": 1.5,
            "avg_lead_time_days": 10,
            "total_units_ordered": 5000,
            "reliability_score": 0.92,
            "total_pos": 25,
            "total_skus": 50,
            "active_skus": 40,
        }
        defaults.update(overrides)
        return defaults

    def test_build_scorecard(self):
        row = self._make_vendor_row()
        sc = build_vendor_scorecard(row)
        assert sc.vendor_id == "VND001"
        assert 0 <= sc.on_time_delivery_rate <= 1
        assert 0 <= sc.lead_time_adherence <= 1
        assert 0 <= sc.composite_score <= 1
        assert sc.tier in ("preferred", "standard", "probation", "inactive")

    def test_high_performer(self):
        row = self._make_vendor_row(
            on_time_deliveries=20, received_pos=20,
            avg_delivery_delay_days=0, reliability_score=0.99,
        )
        sc = build_vendor_scorecard(row)
        assert sc.on_time_delivery_rate == 1.0
        assert sc.lead_time_adherence == 1.0
        assert sc.composite_score >= 0.9
        assert sc.tier == "preferred"

    def test_low_performer(self):
        row = self._make_vendor_row(
            on_time_deliveries=5, received_pos=20,
            avg_delivery_delay_days=8, avg_lead_time_days=7,
            reliability_score=0.5,
        )
        sc = build_vendor_scorecard(row)
        assert sc.on_time_delivery_rate < 0.5
        assert sc.composite_score < 0.7

    def test_build_all_scorecards(self):
        df = pd.DataFrame([
            self._make_vendor_row(vendor_id="VND001"),
            self._make_vendor_row(vendor_id="VND002", vendor_name="Vendor 2"),
        ])
        scorecards = build_all_scorecards(df)
        assert len(scorecards) == 2
        assert all(isinstance(sc, VendorScorecard) for sc in scorecards)


# ─── Forecast Sharing Tests ──────────────────────────────────────────────────


class TestForecastSharing:
    def test_generate_rolling_forecast(self):
        forecasts = pd.DataFrame([
            {"store_id": "S1", "sku_id": "SKU001", "forecast_week": "2026-W01", "point_forecast": 10},
            {"store_id": "S2", "sku_id": "SKU001", "forecast_week": "2026-W01", "point_forecast": 15},
            {"store_id": "S1", "sku_id": "SKU002", "forecast_week": "2026-W01", "point_forecast": 5},
        ])
        sku_vendor = pd.DataFrame([
            {"sku_id": "SKU001", "vendor_id": "VND001", "category": "eyeglasses"},
            {"sku_id": "SKU002", "vendor_id": "VND001", "category": "sunglasses"},
        ])
        result = generate_rolling_forecast(forecasts, sku_vendor, horizon_weeks=12)
        assert not result.empty
        assert "vendor_id" in result.columns
        assert "total_forecast_qty" in result.columns
        assert result["vendor_id"].iloc[0] == "VND001"

    def test_empty_inputs(self):
        result = generate_rolling_forecast(pd.DataFrame(), pd.DataFrame())
        assert result.empty

    def test_vendor_forecast_summary(self):
        rolling = pd.DataFrame([
            {"vendor_id": "VND001", "sku_id": "SKU001", "category": "eyeglasses", "total_forecast_qty": 100},
            {"vendor_id": "VND001", "sku_id": "SKU002", "category": "sunglasses", "total_forecast_qty": 50},
        ])
        summary = build_vendor_forecast_summary(rolling)
        assert len(summary) == 1
        assert summary[0]["vendor_id"] == "VND001"
        assert summary[0]["total_forecast_units"] == 150
        assert summary[0]["sku_count"] == 2


# ─── PO Generator Tests ──────────────────────────────────────────────────────


class TestPOGenerator:
    def test_generate_purchase_orders(self):
        recs = [
            {"vendor_id": "VND001", "sku_id": "SKU001", "recommended_qty": 50,
             "destination_store": "S1", "urgency": "normal", "lifecycle_stage": "active"},
            {"vendor_id": "VND001", "sku_id": "SKU002", "recommended_qty": 30,
             "destination_store": "S2", "urgency": "urgent", "lifecycle_stage": "active"},
        ]
        vendor_info = {
            "VND001": {"moq": 100, "mov": 10000, "avg_lead_time_days": 10, "unit_costs": {}},
        }
        pos = generate_purchase_orders(recs, vendor_info, order_date=date(2026, 3, 1))
        assert len(pos) == 1
        po = pos[0]
        assert po["vendor_id"] == "VND001"
        assert po["total_qty"] >= 100  # Padded to MOQ
        assert po["status"] == "draft"
        assert len(po["lines"]) == 2

    def test_moq_padding(self):
        recs = [
            {"vendor_id": "VND001", "sku_id": "SKU001", "recommended_qty": 10,
             "destination_store": "S1", "urgency": "normal", "lifecycle_stage": "active"},
        ]
        vendor_info = {"VND001": {"moq": 50, "mov": 0, "avg_lead_time_days": 7, "unit_costs": {}}}
        pos = generate_purchase_orders(recs, vendor_info, pad_to_moq=True)
        assert pos[0]["total_qty"] == 50

    def test_no_moq_padding_when_disabled(self):
        recs = [
            {"vendor_id": "VND001", "sku_id": "SKU001", "recommended_qty": 10,
             "destination_store": "S1", "urgency": "normal", "lifecycle_stage": "active"},
        ]
        vendor_info = {"VND001": {"moq": 50, "mov": 0, "avg_lead_time_days": 7, "unit_costs": {}}}
        pos = generate_purchase_orders(recs, vendor_info, pad_to_moq=False)
        assert pos[0]["total_qty"] == 10

    def test_multiple_vendors(self):
        recs = [
            {"vendor_id": "VND001", "sku_id": "SKU001", "recommended_qty": 20,
             "destination_store": "S1", "urgency": "normal", "lifecycle_stage": "active"},
            {"vendor_id": "VND002", "sku_id": "SKU002", "recommended_qty": 30,
             "destination_store": "S1", "urgency": "normal", "lifecycle_stage": "active"},
        ]
        vendor_info = {
            "VND001": {"moq": 0, "mov": 0, "avg_lead_time_days": 7, "unit_costs": {}},
            "VND002": {"moq": 0, "mov": 0, "avg_lead_time_days": 14, "unit_costs": {}},
        }
        pos = generate_purchase_orders(recs, vendor_info)
        assert len(pos) == 2

    def test_new_sku_flagged(self):
        recs = [
            {"vendor_id": "VND001", "sku_id": "SKU001", "recommended_qty": 20,
             "destination_store": "S1", "urgency": "normal", "lifecycle_stage": "new"},
        ]
        vendor_info = {"VND001": {"moq": 0, "mov": 0, "avg_lead_time_days": 7, "unit_costs": {}}}
        pos = generate_purchase_orders(recs, vendor_info)
        assert pos[0]["has_new_skus"] is True


class TestOpenPOPlan:
    def test_generate_open_po_plan(self):
        forecasts = [
            {"sku_id": "SKU001", "weekly_forecast": 50, "unit_cost": 500},
            {"sku_id": "SKU002", "weekly_forecast": 30, "unit_cost": 700},
        ]
        plan = generate_open_po_plan(
            "VND001", forecasts,
            horizon_weeks=12, release_cadence_weeks=2,
            start_date=date(2026, 3, 1),
        )
        assert plan["vendor_id"] == "VND001"
        assert plan["plan_type"] == "open_po"
        assert plan["num_periods"] == 6  # 12 / 2
        assert plan["periods"][0]["status"] == "confirmed"
        assert plan["periods"][1]["status"] == "forecast"
        assert plan["total_committed_qty"] > 0

    def test_period_quantities(self):
        forecasts = [{"sku_id": "SKU001", "weekly_forecast": 10, "unit_cost": 100}]
        plan = generate_open_po_plan("VND001", forecasts, horizon_weeks=8, release_cadence_weeks=4)
        assert plan["num_periods"] == 2
        # Each period = 10 × 4 = 40
        assert plan["periods"][0]["total_qty"] == 40
        assert plan["total_committed_qty"] == 80


# ─── Vendor Portal Tests ─────────────────────────────────────────────────────


class TestVendorPortal:
    def test_build_portal_payload(self):
        payload = build_vendor_portal_payload(
            vendor_id="VND001",
            vendor_name="Test Vendor",
            forecast_data=[
                {"sku_id": "SKU001", "category": "eyeglasses",
                 "total_forecast_qty": 100, "store_count": 5, "avg_forecast_per_store": 20},
            ],
            open_po_data=[
                {"po_id": "PO001", "status": "approved", "total_qty": 200,
                 "order_date": "2026-01-01", "expected_delivery_date": "2026-01-15"},
            ],
            capacity_data=[
                {"period_start": "2026-03-01", "period_end": "2026-03-15",
                 "status": "confirmed", "total_qty": 100, "total_value": 50000},
            ],
            as_of_date=date(2026, 3, 17),
        )
        assert isinstance(payload, VendorPortalPayload)
        assert payload.vendor_id == "VND001"
        assert len(payload.forecast_lines) == 1
        assert payload.total_forecast_units == 100
        assert len(payload.open_pos) == 1
        assert payload.total_open_qty == 200
        assert len(payload.capacity_commitments) == 1

    def test_overdue_detection(self):
        payload = build_vendor_portal_payload(
            vendor_id="VND001",
            vendor_name="Test",
            open_po_data=[
                {"po_id": "PO001", "status": "in_transit", "total_qty": 50,
                 "order_date": "2026-01-01", "expected_delivery_date": "2026-02-01"},
            ],
            as_of_date=date(2026, 3, 17),
        )
        assert payload.overdue_count == 1
        assert payload.open_pos[0].is_overdue is True

    def test_empty_portal(self):
        payload = build_vendor_portal_payload("VND001", "Test")
        assert payload.total_forecast_units == 0
        assert payload.total_open_qty == 0
        assert payload.total_committed_qty == 0


# ─── PO Recommendation Engine Tests ──────────────────────────────────────────


class TestPORecommendationEngine:
    def _make_replenishment_df(self, rows: list[dict]) -> pd.DataFrame:
        defaults = {
            "sku_id": "SKU001",
            "destination_store": "STR001",
            "source_location": "warehouse",
            "recommended_qty": 20,
            "urgency": "normal",
            "reason_code": "below_reorder_point",
            "category": "eyeglasses",
            "sku_type": "physical_sell",
            "vendor_id": "VND001",
            "lead_time_days": 7,
            "lost_sales_estimate": 1000.0,
        }
        result = []
        for row in rows:
            result.append({**defaults, **row})
        return pd.DataFrame(result)

    def _make_vendor_df(self, rows: list[dict]) -> pd.DataFrame:
        defaults = {
            "vendor_id": "VND001",
            "vendor_name": "Test Vendor",
            "vendor_type": "manufacturer",
            "avg_lead_time_days": 7,
            "min_order_value": 5000,
            "min_order_qty": 10,
            "reliability_score": 0.92,
            "is_active": True,
            "total_pos": 20,
            "received_pos": 18,
            "total_units_ordered": 5000,
            "total_po_value": 2500000,
            "avg_delivery_delay_days": 1.5,
            "late_deliveries": 3,
            "on_time_deliveries": 15,
            "total_skus": 50,
            "active_skus": 40,
        }
        result = []
        for row in rows:
            result.append({**defaults, **row})
        return pd.DataFrame(result)

    def test_generate_recommendations(self):
        config = PurchaseOrderConfig()
        recs = self._make_replenishment_df([
            {"sku_id": "SKU001", "vendor_id": "VND001", "recommended_qty": 50},
            {"sku_id": "SKU002", "vendor_id": "VND001", "recommended_qty": 30},
        ])
        vendors = self._make_vendor_df([{"vendor_id": "VND001"}])

        result = generate_po_recommendations(recs, vendors, config, date(2026, 3, 1))
        assert isinstance(result, PORecommendationResult)
        assert result.total_pos >= 1
        assert result.total_units > 0
        assert result.skus_covered == 2

    def test_multiple_vendors(self):
        config = PurchaseOrderConfig()
        recs = self._make_replenishment_df([
            {"sku_id": "SKU001", "vendor_id": "VND001", "recommended_qty": 50},
            {"sku_id": "SKU002", "vendor_id": "VND002", "recommended_qty": 30},
        ])
        vendors = self._make_vendor_df([
            {"vendor_id": "VND001"},
            {"vendor_id": "VND002", "vendor_name": "Vendor 2"},
        ])

        result = generate_po_recommendations(recs, vendors, config)
        assert result.vendors_used == 2

    def test_empty_replenishment(self):
        config = PurchaseOrderConfig()
        result = generate_po_recommendations(pd.DataFrame(), pd.DataFrame(), config)
        assert result.total_pos == 0

    def test_moq_padding(self):
        config = PurchaseOrderConfig(pad_to_moq=True)
        recs = self._make_replenishment_df([
            {"sku_id": "SKU001", "vendor_id": "VND001", "recommended_qty": 5},
        ])
        vendors = self._make_vendor_df([
            {"vendor_id": "VND001", "min_order_qty": 50},
        ])

        result = generate_po_recommendations(recs, vendors, config)
        if result.recommendations:
            # Total qty should be padded to at least MOQ
            assert result.recommendations[0].total_qty >= 50

    def test_vendor_tier_in_output(self):
        config = PurchaseOrderConfig()
        recs = self._make_replenishment_df([
            {"sku_id": "SKU001", "vendor_id": "VND001", "recommended_qty": 50},
        ])
        vendors = self._make_vendor_df([{"vendor_id": "VND001"}])

        result = generate_po_recommendations(recs, vendors, config)
        if result.recommendations:
            assert result.recommendations[0].vendor_tier in ("preferred", "standard", "probation")

    def test_urgency_propagated(self):
        config = PurchaseOrderConfig()
        recs = self._make_replenishment_df([
            {"sku_id": "SKU001", "vendor_id": "VND001", "recommended_qty": 50, "urgency": "emergency"},
        ])
        vendors = self._make_vendor_df([{"vendor_id": "VND001"}])

        result = generate_po_recommendations(recs, vendors, config)
        if result.recommendations:
            assert result.recommendations[0].urgency == "emergency"


class TestVendorSelection:
    def _make_scorecards(self):
        return {
            "VND001": VendorScorecard(
                vendor_id="VND001", vendor_name="Best", composite_score=0.95,
                on_time_delivery_rate=0.95, lead_time_adherence=0.9,
                quality_pass_rate=0.95, capacity_accuracy=0.95, forecast_adherence=0.95,
                tier="preferred", is_active=True,
            ),
            "VND002": VendorScorecard(
                vendor_id="VND002", vendor_name="Good", composite_score=0.80,
                on_time_delivery_rate=0.80, lead_time_adherence=0.8,
                quality_pass_rate=0.80, capacity_accuracy=0.80, forecast_adherence=0.80,
                tier="standard", is_active=True,
            ),
            "VND003": VendorScorecard(
                vendor_id="VND003", vendor_name="Low", composite_score=0.40,
                on_time_delivery_rate=0.40, lead_time_adherence=0.4,
                quality_pass_rate=0.40, capacity_accuracy=0.40, forecast_adherence=0.40,
                tier="probation", is_active=True,
            ),
        }

    def test_selects_highest_scorer(self):
        config = PurchaseOrderConfig(min_vendor_score=0.5)
        scorecards = self._make_scorecards()
        sku_map = {"SKU001": ["VND001", "VND002", "VND003"]}

        allocations = select_vendor("SKU001", scorecards, sku_map, config)
        assert len(allocations) >= 1
        assert allocations[0][0] == "VND001"  # Highest scorer

    def test_filters_below_min_score(self):
        config = PurchaseOrderConfig(min_vendor_score=0.85)
        scorecards = self._make_scorecards()
        sku_map = {"SKU001": ["VND001", "VND002", "VND003"]}

        allocations = select_vendor("SKU001", scorecards, sku_map, config)
        assert len(allocations) >= 1
        # Only VND001 should qualify (score 0.95)
        assert allocations[0][0] == "VND001"

    def test_new_sku_preferred_only(self):
        config = PurchaseOrderConfig(new_sku_preferred_vendor_only=True)
        scorecards = self._make_scorecards()
        sku_map = {"SKU001": ["VND001", "VND002"]}

        allocations = select_vendor("SKU001", scorecards, sku_map, config, is_new_sku=True)
        assert len(allocations) == 1
        assert allocations[0][0] == "VND001"
        assert allocations[0][1] == 1.0

    def test_no_vendors_available(self):
        config = PurchaseOrderConfig()
        allocations = select_vendor("SKU_NONE", {}, {}, config)
        assert allocations == []


class TestSplitAllocation:
    def test_split_two_vendors(self):
        config = PurchaseOrderConfig(preferred_vendor_allocation_pct=0.7)
        vendors = [
            ("VND001", VendorScorecard(
                vendor_id="VND001", vendor_name="A", composite_score=0.95,
                on_time_delivery_rate=0.95, lead_time_adherence=0.9,
                quality_pass_rate=0.95, capacity_accuracy=0.95, forecast_adherence=0.95,
                tier="preferred", is_active=True)),
            ("VND002", VendorScorecard(
                vendor_id="VND002", vendor_name="B", composite_score=0.80,
                on_time_delivery_rate=0.80, lead_time_adherence=0.8,
                quality_pass_rate=0.80, capacity_accuracy=0.80, forecast_adherence=0.80,
                tier="standard", is_active=True)),
        ]
        allocs = split_allocation(vendors, 200, config)
        assert len(allocs) == 2
        assert allocs[0][0] == "VND001"
        assert allocs[0][1] == 0.7
        assert abs(sum(a[1] for a in allocs) - 1.0) < 0.01


# ─── PO Manager Tests ────────────────────────────────────────────────────────


class TestPurchaseOrderManager:
    def setup_method(self):
        self.manager = PurchaseOrderManager()

    def test_create_draft(self):
        po = self.manager.create_draft(
            vendor_id="VND001",
            lines=[
                {"sku_id": "SKU001", "qty_ordered": 50, "unit_cost": 500.0},
                {"sku_id": "SKU002", "qty_ordered": 30, "unit_cost": 700.0},
            ],
        )
        assert po["status"] == "draft"
        assert po["total_qty"] == 80

    def test_submit_po(self):
        po = self.manager.create_draft("VND001", [{"sku_id": "SKU001", "qty_ordered": 10, "unit_cost": 100}])
        submitted = self.manager.submit(po["po_id"])
        assert submitted["status"] == "submitted"

    def test_approve_po(self):
        po = self.manager.create_draft("VND001", [{"sku_id": "SKU001", "qty_ordered": 10, "unit_cost": 100}])
        self.manager.submit(po["po_id"])
        approved = self.manager.approve(po["po_id"])
        assert approved["status"] == "approved"

    def test_cannot_approve_draft(self):
        po = self.manager.create_draft("VND001", [{"sku_id": "SKU001", "qty_ordered": 10, "unit_cost": 100}])
        with pytest.raises(ValueError, match="not in submitted status"):
            self.manager.approve(po["po_id"])

    def test_record_receipt(self):
        po = self.manager.create_draft("VND001", [{"sku_id": "SKU001", "qty_ordered": 10, "unit_cost": 100}])
        self.manager.submit(po["po_id"])
        self.manager.approve(po["po_id"])
        result = self.manager.record_receipt(po["po_id"], [{"sku_id": "SKU001", "qty_received": 10}])
        assert result["status"] == "received"
        assert result["total_received"] == 10


# ─── Config Tests ─────────────────────────────────────────────────────────────


class TestPurchaseOrderConfig:
    def test_defaults(self):
        config = PurchaseOrderConfig()
        assert config.forecast_horizon_weeks == 12
        assert config.po_horizon_weeks == 4
        assert config.min_vendor_score > 0
        assert config.preferred_vendor_allocation_pct > 0
        assert config.preferred_vendor_allocation_pct <= 1.0
        assert config.max_single_vendor_allocation_pct <= 1.0

    def test_custom_config(self):
        config = PurchaseOrderConfig(
            forecast_horizon_weeks=8,
            min_vendor_score=0.7,
        )
        assert config.forecast_horizon_weeks == 8
        assert config.min_vendor_score == 0.7
